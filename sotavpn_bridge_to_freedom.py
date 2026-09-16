"""Sotavpn subscription bridge to freedom.

What it is
    A small program that asks the Sota Connect vendor API for the server list
    of your paid account and hands that list out as an ordinary subscription
    URL, so any client works: v2rayN, NekoBox, Hiddify, Clash, Mihomo, Stash,
    sing-box, Xray and the 3x-ui panel.

What it does not do
    It does not bring up a tunnel, it does not touch routes or DNS, it does
    not check whether a node is alive, and it does not store your vendor
    application. Bringing up a tunnel is the client job, and choosing a live
    node is the client test group job.

How it works
    A client asks for a subscription. The program answers from the list it
    already has, and when that list is older than SNAPSHOT_FRESH_SECONDS it
    asks the vendor for a fresh one first. The vendor hands out an address
    together with its camouflage name, and that pair goes stale within
    minutes, so the list is collected again on request, not on a timer.

How to run it
    python3 sotavpn_bridge_to_freedom.py

Where the values live
    Every value is in settings.py next to this file. That file is imported
    below, and the import itself is execution: nothing else is configured.

Addresses
    http://127.0.0.1:25080/sub/<your access key>
    https://127.0.0.1:25443/sub/<your access key>
    http://127.0.0.1:25080/ shows every answer this program can give.
"""

import base64
import html
import json
import os
import secrets
import ssl
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

import settings

PROGRAM_DIRECTORY = os.path.dirname(os.path.abspath(__file__))


def path_next_to_the_program(path):
    """A path from settings.py, counted from the program, not from the caller."""
    if os.path.isabs(path):
        return path
    return os.path.join(PROGRAM_DIRECTORY, path)


def tell(message):
    """Write one line into the journal, with the time in front of it."""
    if not settings.VERBOSE:
        return
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"{stamp} {settings.PROGRAM_NAME}: {message}", flush=True)


def shorten(access_key):
    """Show the beginning of an access key and never the whole secret."""
    if len(access_key) <= 8:
        return access_key
    return f"{access_key[:8]}..."


def vendor_request(path, access_key, hardware_id, query=""):
    """Ask the vendor API once and give back the parsed answer."""
    address = f"https://{settings.VENDOR_HOST}{settings.VENDOR_BASE_PATH}{path}{query}"
    request = urllib.request.Request(address)
    request.add_header("X-Access-Key", access_key)
    request.add_header("X-HwID", hardware_id)
    request.add_header("User-Agent", settings.VENDOR_USER_AGENT)
    request.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(request, timeout=settings.VENDOR_TIME_OUT_SECONDS) as answer:
        return json.loads(answer.read().decode("utf-8"))


def vendor_request_with_retries(path, access_key, hardware_id, query="", what=""):
    """Ask the vendor API, repeat a failed call, and explain every failure."""
    complaint = ""
    for attempt in range(1, settings.VENDOR_ATTEMPTS + 1):
        try:
            return vendor_request(path, access_key, hardware_id, query)
        except urllib.error.HTTPError as error:
            complaint = error.read().decode("utf-8", "replace").strip() or str(error)
            tell(f"vendor refused {what or path} with code {error.code}: {complaint}")
            if error.code in (401, 403, 404):
                raise RuntimeError(f"the vendor refused the request: {complaint}") from error
        except (urllib.error.URLError, TimeoutError, ValueError) as error:
            complaint = str(error)
            tell(f"vendor call {what or path} failed on attempt {attempt} of {settings.VENDOR_ATTEMPTS}: {error}")
        if attempt < settings.VENDOR_ATTEMPTS:
            time.sleep(settings.VENDOR_RETRY_PAUSE_SECONDS)
    raise RuntimeError(f"the vendor did not answer the request {what or path}: {complaint}")


def node_from_gateway(location, gateway, configuration):
    """Build one node out of a location, one gateway address and a configuration."""
    outbound = None
    for candidate in configuration.get("outbounds", []):
        if candidate.get("type") == "vless":
            outbound = candidate
            break
    if outbound is None:
        return None
    tls = outbound.get("tls", {})
    reality = tls.get("reality", {})
    country = location.get("shortname") or str(location.get("id"))
    name = " ".join(
        part
        for part in (
            settings.NODE_NAME_PREFIX,
            country,
            location.get("name", ""),
            gateway.get("name", ""),
        )
        if part
    )
    return {
        "name": name,
        "address": gateway.get("address", ""),
        "port": outbound.get("server_port", 443),
        "uuid": outbound.get("uuid", ""),
        "flow": outbound.get("flow", ""),
        "sni": tls.get("server_name", ""),
        "fingerprint": tls.get("utls", {}).get("fingerprint", "chrome"),
        "public_key": reality.get("public_key", ""),
        "short_id": reality.get("short_id", ""),
    }


def collect_nodes(access_key, hardware_id):
    """Walk the vendor API and give back every usable node of the account."""
    locations = vendor_request_with_retries(
        "/connection/list", access_key, hardware_id, what="the location list"
    )
    tell(f"the vendor listed {len(locations)} locations for key {shorten(access_key)}")
    nodes = []
    for location in locations:
        time.sleep(settings.VENDOR_PAUSE_BETWEEN_REQUESTS_SECONDS)
        what = f"the configuration of {location.get('name')}"
        try:
            document = vendor_request_with_retries(
                "/connection/connect",
                access_key,
                hardware_id,
                query="?" + urllib.parse.urlencode({"gate_id": location.get("id")}),
                what=what,
            )
        except RuntimeError as error:
            tell(f"{what} is skipped: {error}")
            continue
        configuration = document.get("configuration") or document
        for gateway in location.get("gateways") or []:
            node = node_from_gateway(location, gateway, configuration)
            if node is not None:
                nodes.append(node)
    tell(f"collected {len(nodes)} nodes for key {shorten(access_key)}")
    return nodes


def read_subscription_expiry(access_key, hardware_id):
    """Read the subscription end date, so clients can show it."""
    try:
        profile = vendor_request_with_retries(
            "/subscription/profile", access_key, hardware_id, what="the subscription profile"
        )
    except RuntimeError as error:
        tell(f"the subscription end date is unknown: {error}")
        return 0
    moment = profile.get("expiration_at")
    if not moment:
        return 0
    cleaned = moment.replace("Z", "+0000")
    for pattern in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            return int(time.mktime(time.strptime(cleaned, pattern)))
        except ValueError:
            continue
    return 0


class AccountSnapshot:
    """The node list of one access key, collected on request."""

    def __init__(self, access_key, hardware_id):
        self.access_key = access_key
        self.hardware_id = hardware_id
        self.nodes = []
        self.expiry = 0
        self.collected_at = 0.0
        self.complaint = ""
        self.lock = threading.Lock()

    def age_seconds(self):
        if not self.collected_at:
            return None
        return time.monotonic() - self.collected_at

    def collect_locked(self):
        try:
            nodes = collect_nodes(self.access_key, self.hardware_id)
        except RuntimeError as error:
            self.complaint = str(error)
            tell(f"the collection for key {shorten(self.access_key)} failed: {error}")
            return
        if not nodes:
            self.complaint = "the vendor answered, but handed out no usable server"
            tell(self.complaint)
            return
        self.nodes = nodes
        self.expiry = read_subscription_expiry(self.access_key, self.hardware_id)
        self.collected_at = time.monotonic()
        self.complaint = ""

    def nodes_for_request(self):
        """Give the freshest list this request deserves, and its age."""
        age = self.age_seconds()
        if age is not None and age < settings.SNAPSHOT_FRESH_SECONDS:
            return self.nodes, age, self.complaint
        with self.lock:
            age = self.age_seconds()
            if age is None or age >= settings.SNAPSHOT_FRESH_SECONDS:
                self.collect_locked()
        return self.nodes, self.age_seconds(), self.complaint


SNAPSHOTS = {}
SNAPSHOTS_LOCK = threading.Lock()
INVENTED_HARDWARE_IDS = {}


def hardware_id_for(access_key, requested):
    """Pick the device id: the asked one, the configured one, or a random one."""
    if requested:
        return requested
    if settings.DEFAULT_HARDWARE_ID:
        return settings.DEFAULT_HARDWARE_ID
    with SNAPSHOTS_LOCK:
        if access_key not in INVENTED_HARDWARE_IDS:
            INVENTED_HARDWARE_IDS[access_key] = secrets.token_hex(32)
            tell(f"invented a device id for key {shorten(access_key)}")
        return INVENTED_HARDWARE_IDS[access_key]


def snapshot_for(access_key, hardware_id):
    """Give the snapshot of one account, creating it on the first request."""
    with SNAPSHOTS_LOCK:
        if access_key not in SNAPSHOTS:
            SNAPSHOTS[access_key] = AccountSnapshot(access_key, hardware_id)
            tell(f"opened a snapshot for key {shorten(access_key)}")
        return SNAPSHOTS[access_key]


def node_to_link(node):
    """One node as a vless link with reality settings."""
    query = urllib.parse.urlencode(
        {
            "encryption": "none",
            "flow": node["flow"],
            "security": "reality",
            "sni": node["sni"],
            "fp": node["fingerprint"],
            "pbk": node["public_key"],
            "sid": node["short_id"],
            "type": "tcp",
        }
    )
    return f"vless://{node['uuid']}@{node['address']}:{node['port']}?{query}#{urllib.parse.quote(node['name'])}"


def answer_raw(nodes, access_key):
    """The open list of links, one per line."""
    return "\n".join(node_to_link(node) for node in nodes) + "\n"


def answer_base64(nodes, access_key):
    """The same list in base64, the format almost every client expects."""
    return base64.b64encode(answer_raw(nodes, access_key).encode("utf-8")).decode("ascii")


def answer_clash(nodes, access_key):
    """YAML for Clash, Mihomo and Stash, with one automatic test group."""
    names = ", ".join(f'"{node["name"]}"' for node in nodes)
    lines = ["proxies:"]
    for node in nodes:
        lines.append(f'  - name: "{node["name"]}"')
        lines.append("    type: vless")
        lines.append(f'    server: {node["address"]}')
        lines.append(f'    port: {node["port"]}')
        lines.append(f'    uuid: {node["uuid"]}')
        lines.append(f'    flow: {node["flow"]}')
        lines.append("    network: tcp")
        lines.append("    tls: true")
        lines.append("    udp: true")
        lines.append(f'    servername: {node["sni"]}')
        lines.append(f'    client-fingerprint: {node["fingerprint"]}')
        lines.append("    reality-opts:")
        lines.append(f'      public-key: {node["public_key"]}')
        lines.append(f'      short-id: {node["short_id"]}')
    lines.append("proxy-groups:")
    lines.append('  - name: "Sota automatic"')
    lines.append("    type: url-test")
    lines.append(f"    url: {settings.CLASH_TEST_URL}")
    lines.append(f"    interval: {settings.CLASH_TEST_INTERVAL_SECONDS}")
    lines.append(f"    tolerance: {settings.CLASH_TEST_TOLERANCE_MILLISECONDS}")
    lines.append(f"    proxies: [{names}]")
    lines.append('  - name: "Sota manual"')
    lines.append("    type: select")
    lines.append('    proxies: ["Sota automatic"]')
    lines.append("rules:")
    lines.append('  - MATCH,"Sota manual"')
    return "\n".join(lines) + "\n"


def sing_box_outbound(node, tag=None):
    """One node as a sing-box outbound."""
    return {
        "type": "vless",
        "tag": tag or node["name"],
        "server": node["address"],
        "server_port": node["port"],
        "uuid": node["uuid"],
        "flow": node["flow"],
        "tls": {
            "enabled": True,
            "server_name": node["sni"],
            "utls": {"enabled": True, "fingerprint": node["fingerprint"]},
            "reality": {
                "enabled": True,
                "public_key": node["public_key"],
                "short_id": node["short_id"],
            },
        },
    }


def answer_singbox(nodes, access_key):
    """JSON outbounds for sing-box and Hiddify, with one automatic test group."""
    outbounds = [sing_box_outbound(node) for node in nodes]
    outbounds.append(
        {
            "type": "urltest",
            "tag": "Sota automatic",
            "outbounds": [node["name"] for node in nodes],
            "url": settings.SING_BOX_TEST_URL,
            "interval": settings.SING_BOX_TEST_INTERVAL,
            "tolerance": settings.SING_BOX_TEST_TOLERANCE,
        }
    )
    outbounds.append({"type": "direct", "tag": "direct"})
    return json.dumps({"outbounds": outbounds}, ensure_ascii=False, indent=2)


def answer_singbox_full(nodes, access_key):
    """A complete sing-box configuration that a user can start as it is."""
    document = {
        "log": {"level": "info", "timestamp": True},
        "inbounds": [
            {
                "type": "tun",
                "tag": "tun-in",
                "address": [settings.SING_BOX_LOCAL_TUN_ADDRESS],
                "auto_route": True,
                "strict_route": True,
                "stack": "gvisor",
            }
        ],
        "outbounds": json.loads(answer_singbox(nodes, access_key))["outbounds"],
        "route": {"final": "Sota automatic"},
    }
    return json.dumps(document, ensure_ascii=False, indent=2)


def xray_outbound(node):
    """One node as an Xray outbound."""
    return {
        "tag": node["name"],
        "protocol": "vless",
        "settings": {
            "vnext": [
                {
                    "address": node["address"],
                    "port": node["port"],
                    "users": [
                        {"id": node["uuid"], "encryption": "none", "flow": node["flow"]}
                    ],
                }
            ]
        },
        "streamSettings": {
            "network": "tcp",
            "security": "reality",
            "realitySettings": {
                "serverName": node["sni"],
                "fingerprint": node["fingerprint"],
                "publicKey": node["public_key"],
                "shortId": node["short_id"],
            },
        },
    }


def answer_xray(nodes, access_key):
    """JSON outbounds for Xray and for the 3x-ui panel."""
    return json.dumps([xray_outbound(node) for node in nodes], ensure_ascii=False, indent=2)


def answer_xray_full(nodes, access_key):
    """A complete Xray configuration with a local socks port."""
    document = {
        "log": {"loglevel": "info"},
        "inbounds": [
            {
                "tag": "socks-in",
                "listen": "127.0.0.1",
                "port": settings.XRAY_LOCAL_SOCKS_PORT,
                "protocol": "socks",
                "settings": {"udp": True},
            }
        ],
        "outbounds": [xray_outbound(node) for node in nodes],
    }
    return json.dumps(document, ensure_ascii=False, indent=2)


def answer_html(nodes, access_key):
    """A page for a human being: every node with its link and its settings."""
    rows = [
        "<!DOCTYPE html>",
        "<html lang='en'><head><meta charset='utf-8'>",
        f"<title>{settings.PROFILE_TITLE}: {len(nodes)} nodes</title></head><body>",
        f"<h1>{settings.PROFILE_TITLE}: {len(nodes)} nodes</h1>",
        "<p>Every line below is one server. Copy a link into your client, or "
        "take the address, port, camouflage name and keys from the details.</p>",
    ]
    for node in nodes:
        link = node_to_link(node)
        rows.append(f"<h3>{html.escape(node['name'])}</h3>")
        rows.append(f"<p><a href='{html.escape(link)}'>{html.escape(node['address'])}</a></p>")
        rows.append(
            "<p>port {port}, camouflage name {sni}, fingerprint {fingerprint}, "
            "public key {key}, short id {short}</p>".format(
                port=html.escape(str(node["port"])),
                sni=html.escape(node["sni"]),
                fingerprint=html.escape(node["fingerprint"]),
                key=html.escape(node["public_key"]),
                short=html.escape(node["short_id"]),
            )
        )
    rows.append("</body></html>")
    return "\n".join(rows) + "\n"


def answer_csv(nodes, access_key):
    """A table for manual entry on a router or in any client that asks by hand."""
    lines = ["name,address,port,camouflage_name,fingerprint,public_key,short_id,uuid,flow,link"]
    for node in nodes:
        fields = [
            node["name"],
            node["address"],
            str(node["port"]),
            node["sni"],
            node["fingerprint"],
            node["public_key"],
            node["short_id"],
            node["uuid"],
            node["flow"],
            node_to_link(node),
        ]
        lines.append(",".join('"' + field.replace('"', '""') + '"' for field in fields))
    return "\n".join(lines) + "\n"


ANSWERS = {
    "base64": (answer_base64, "text/plain; charset=utf-8"),
    "raw": (answer_raw, "text/plain; charset=utf-8"),
    "clash": (answer_clash, "text/yaml; charset=utf-8"),
    "singbox": (answer_singbox, "application/json; charset=utf-8"),
    "singbox-full": (answer_singbox_full, "application/json; charset=utf-8"),
    "xray": (answer_xray, "application/json; charset=utf-8"),
    "xray-full": (answer_xray_full, "application/json; charset=utf-8"),
    "html": (answer_html, "text/html; charset=utf-8"),
    "csv": (answer_csv, "text/csv; charset=utf-8"),
}


def guess_answer_from_client_name(client_name):
    """Guess the wanted answer from the name the client calls itself."""
    agent = (client_name or "").lower()
    for word in ("clash", "mihomo", "stash"):
        if word in agent:
            return "clash"
    for word in ("sing-box", "singbox", "hiddify", "karing", "sfa", "sfi"):
        if word in agent:
            return "singbox"
    return "base64"


class BridgeAnswerHandler(BaseHTTPRequestHandler):
    """Answers every request: from the ready list, or after collecting a new one."""

    server_version = f"{settings.PROGRAM_NAME}/{settings.PROGRAM_VERSION}"

    def do_GET(self):
        self.answer(with_body=True)

    def do_HEAD(self):
        self.answer(with_body=False)

    def address_parts(self):
        parsed = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed.query)
        parts = [part for part in parsed.path.split("/") if part]
        return parts, query

    def answer(self, with_body):
        try:
            self.answer_or_complain(with_body)
        except BrokenPipeError:
            tell("the client closed the connection before the answer was sent")
        except Exception as error:  # noqa: BLE001 - one bad request never stops the program
            tell(f"the request {self.masked_path()} broke: {error}")
            self.send_text(f"the bridge hit an unexpected problem: {error}\n", with_body, 500)

    def answer_or_complain(self, with_body):
        parts, query = self.address_parts()
        if not parts:
            self.send_text(self.root_page(), with_body)
            return
        if parts[0] != "sub" or len(parts) < 2:
            self.send_text(self.help_page("use /sub/<access key>[/<answer format>]"), with_body, 404)
            return
        access_key = urllib.parse.unquote(parts[1])
        suffix = urllib.parse.unquote(parts[2]).lower() if len(parts) > 2 else ""
        if not suffix:
            suffix = guess_answer_from_client_name(self.headers.get("User-Agent"))
        render = ANSWERS.get(suffix)
        if render is None:
            self.send_text(
                self.help_page(f"there is no answer called {suffix}, here is what exists"),
                with_body,
                404,
            )
            return
        hardware_id = hardware_id_for(access_key, query.get("hwid", [""])[0])
        snapshot = snapshot_for(access_key, hardware_id)
        nodes, age, complaint = snapshot.nodes_for_request()
        if not nodes:
            self.send_text(
                "the bridge has no server list for this access key yet.\n"
                f"reason: {complaint or 'the vendor did not answer'}\n"
                "check the key, check the network, then ask again: the bridge "
                "collects the list on the first request.\n",
                with_body,
                503,
            )
            return
        render_function, content_type = render
        body = render_function(nodes, access_key).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Profile-Title", settings.PROFILE_TITLE)
        self.send_header("Profile-Update-Interval", str(settings.PROFILE_UPDATE_INTERVAL_HOURS))
        self.send_header("Profile-web-page-url", "https://sotavpn.org")
        self.send_header(
            "Subscription-Userinfo",
            f"upload=0; download=0; total=0; expire={snapshot.expiry}",
        )
        self.send_header("X-Bridge-Nodes", str(len(nodes)))
        self.send_header("X-Bridge-Age-Seconds", str(int(age or 0)))
        self.end_headers()
        if with_body:
            self.wfile.write(body)
        tell(f"sent {suffix} with {len(nodes)} nodes, the list is {int(age or 0)} seconds old")

    def masked_path(self):
        """The request path with the access key hidden."""
        parts = [part for part in urllib.parse.urlparse(self.path).path.split("/") if part]
        if len(parts) >= 2 and parts[0] == "sub":
            parts[1] = shorten(parts[1])
            return "/" + "/".join(parts)
        return urllib.parse.urlparse(self.path).path or "/"

    def root_page(self):
        host = self.headers.get("Host") or f"{settings.LISTEN_ADDRESS}:{settings.HTTP_PORT}"
        lines = [
            f"{settings.PROFILE_TITLE} subscription bridge to freedom, version {settings.PROGRAM_VERSION}.",
            "",
            f"Put your access key into the address, and you get {len(ANSWERS)} answers:",
            "",
        ]
        for suffix, description in settings.ANSWER_FORMATS:
            lines.append(f"http://{host}/sub/<access key>/{suffix}")
            lines.append(f"    {description}")
        lines.append("")
        lines.append("Without a suffix the bridge guesses by the client name, and base64 wins.")
        lines.append("")
        lines.append("Formats this bridge does not write by itself, such as Surge, Loon,")
        lines.append("Quantumult and Surfboard, are made by the converter subconverter:")
        lines.append(f"{settings.SUBCONVERTER_SUBSCRIBE_URL}?target=surge&url=<this address in URL encoding>")
        lines.append("")
        lines.append(f"Settings live in settings.py, the list is refreshed when it is older than {settings.SNAPSHOT_FRESH_SECONDS} seconds.")
        return "\n".join(lines) + "\n"

    def help_page(self, message):
        lines = [
            message,
            "",
            "the address of one answer looks like /sub/<access key>/<answer format>",
            "the answer formats are:",
        ]
        for suffix, description in settings.ANSWER_FORMATS:
            lines.append(f"    {suffix}: {description}")
        return "\n".join(lines) + "\n"

    def send_text(self, text, with_body, status=200):
        body = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if with_body:
            self.wfile.write(body)

    def log_message(self, format, *args):
        tell(f"request from {self.address_string()} for {self.masked_path()}")


def start_plain_server():
    """Serve plain HTTP, which works with every client."""
    try:
        server = HTTPServer((settings.LISTEN_ADDRESS, settings.HTTP_PORT), BridgeAnswerHandler)
    except OSError as error:
        tell(f"the plain port {settings.HTTP_PORT} is not free: {error}")
        tell("another program holds it, change HTTP_PORT in settings.py")
        return None
    tell(f"plain HTTP is listening on http://{settings.LISTEN_ADDRESS}:{settings.HTTP_PORT}")
    return server


def start_https_server():
    """Serve HTTPS with the certificate that lies in the certs directory."""
    if not settings.ENABLE_HTTPS:
        tell("HTTPS is switched off in settings.py, only the plain port is used")
        return None
    for path in (settings.CERTIFICATE_FILE, settings.PRIVATE_KEY_FILE):
        try:
            with open(path_next_to_the_program(path), "rb"):
                pass
        except OSError as error:
            tell(f"the certificate file {path} is not readable: {error}")
            tell("HTTPS is skipped, the plain port still works, regenerate the certificate with the command from the README")
            return None
    try:
        server = HTTPServer((settings.LISTEN_ADDRESS, settings.HTTPS_PORT), BridgeAnswerHandler)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(
            path_next_to_the_program(settings.CERTIFICATE_FILE),
            path_next_to_the_program(settings.PRIVATE_KEY_FILE),
        )
        server.socket = context.wrap_socket(server.socket, server_side=True)
    except OSError as error:
        tell(f"the HTTPS port {settings.HTTPS_PORT} is not usable: {error}")
        tell("another program holds it, change HTTPS_PORT in settings.py")
        return None
    except ssl.SSLError as error:
        tell(f"the certificate is not usable: {error}")
        return None
    tell(f"HTTPS is listening on https://{settings.LISTEN_ADDRESS}:{settings.HTTPS_PORT}")
    tell("the certificate is self signed, so a client needs permission to accept it")
    return server


def main():
    tell(f"{settings.PROGRAM_NAME} version {settings.PROGRAM_VERSION} starts")
    tell(f"values were taken from settings.py next to the program, the vendor is {settings.VENDOR_HOST}")
    servers = [server for server in (start_plain_server(), start_https_server()) if server is not None]
    if not servers:
        tell("no port could be opened, nothing to do, stopping")
        return 1
    threads = []
    for server in servers:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        threads.append(thread)
    tell("the bridge is ready, put an address from the page above into your client")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        tell("stop was asked for, closing the ports")
        for server in servers:
            server.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
