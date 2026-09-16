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

What it keeps
    Every answer the vendor gives is written to logs/<access key>.json as
    readable JSON with tab indentation, one account in one file and an empty
    line between two answers, and the answers of the previous pass move into
    a directory named after the moment that file was created. The bodies the
    vendor sends with a refusal go to logs/<access key>.errors.txt and move
    the same way. The journal of the run goes to logs/log.log and moves the
    same way on the next start.
    The logs directory is listed in .gitignore, because a raw vendor answer
    carries the addresses and the keys of the account.

Where the values live
    Every value is in settings.py next to this file. That file is imported
    below, and the import itself is execution: nothing else is configured.

Addresses
    http://127.0.0.1:25080/sub/<your access key>
    https://127.0.0.1:25443/sub/<your access key>
    http://127.0.0.1:25080/ shows every answer this program can give.
"""

import base64
import csv
import datetime
import html
import io
import json
import os
import secrets
import signal
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
STOP_REQUESTED = threading.Event()


def note_the_stop_request(signal_number, stack_frame):
    """A polite stop: the program closes its ports itself and says so."""
    tell(f"a stop request arrived, signal {signal_number}, the ports are closing")
    STOP_REQUESTED.set()


def path_next_to_the_program(path):
    """A path from settings.py, counted from the program, not from the caller."""
    if os.path.isabs(path):
        return path
    return os.path.join(PROGRAM_DIRECTORY, path)


def tell(message):
    """Write one line into the journal of this run and, when asked, onto the screen."""
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}"
    write_journal_line(line)
    if settings.VERBOSE:
        print(line, flush=True)


LOGS_LOCK = threading.RLock()
JOURNAL_FILE = None
JOURNAL_PROBLEM_REPORTED = False


def logs_directory():
    """The directory that keeps the raw vendor answers and the journal."""
    return path_next_to_the_program(settings.LOGS_DIRECTORY)


def make_logs_directory():
    """Create the log directory when it is not there yet."""
    try:
        os.makedirs(logs_directory(), exist_ok=True)
    except OSError as error:
        report_a_log_problem(f"the log directory {settings.LOGS_DIRECTORY} is not usable: {error}")
        return False
    return True


def report_a_log_problem(message):
    """Tell about a broken log once, so one failure does not flood the journal."""
    global JOURNAL_PROBLEM_REPORTED
    if JOURNAL_PROBLEM_REPORTED:
        return
    JOURNAL_PROBLEM_REPORTED = True
    tell(f"{message}, the program keeps running without that log")


def dated_directory_for(moment):
    """A directory named by a moment, counted up when that very moment repeats."""
    base = os.path.join(logs_directory(), moment)
    candidate = base
    number = 2
    while os.path.exists(candidate):
        candidate = f"{base}-{number}"
        number += 1
    os.makedirs(candidate, exist_ok=True)
    return candidate


def move_into_a_dated_directory(path):
    """Move one log file into a directory named by the moment that file was created."""
    if not os.path.exists(path):
        return ""
    try:
        created = os.path.getmtime(path)
        moment = time.strftime(settings.ARCHIVE_MOMENT_FORMAT, time.localtime(created))
        target = os.path.join(dated_directory_for(moment), os.path.basename(path))
        os.replace(path, target)
        return target
    except OSError as error:
        report_a_log_problem(f"the log file {os.path.basename(path)} could not be moved away: {error}")
        return ""


def name_of_the_directory_that_holds(target):
    """The dated directory of a moved file, as a path a reader can follow."""
    return f"{settings.LOGS_DIRECTORY}/{os.path.basename(os.path.dirname(target))}"


def answer_file_name(access_key):
    """The file of one account, named after its access key."""
    return f"{access_key}{settings.ANSWER_FILE_SUFFIX}"


def answer_file_path(access_key):
    """Where the answers of one account of this pass live."""
    return os.path.join(logs_directory(), answer_file_name(access_key))


def error_file_name(access_key):
    """The file of one account that keeps the bodies the vendor sent with a refusal."""
    return f"{access_key}{settings.ERROR_FILE_SUFFIX}"


def error_file_path(access_key):
    """Where the refusals of one account of this pass live."""
    return os.path.join(logs_directory(), error_file_name(access_key))


def start_a_fresh_log_pass(access_key):
    """Move the logs of the previous pass of this account away."""
    with LOGS_LOCK:
        if not make_logs_directory():
            return
        for path in (answer_file_path(access_key), error_file_path(access_key)):
            moved = move_into_a_dated_directory(path)
            if moved:
                tell(
                    f"the log of the previous pass moved to "
                    f"{name_of_the_directory_that_holds(moved)}/{os.path.basename(moved)}"
                )


def pretty_answer(raw_answer):
    """One vendor answer as readable JSON, with tabs as the indentation."""
    try:
        return json.dumps(json.loads(raw_answer), ensure_ascii=False, indent="\t")
    except ValueError:
        # An answer that is not JSON is kept as it came: a reader of the log
        # is better served by the text than by nothing.
        return raw_answer.strip()


def keep_vendor_answer(access_key, raw_answer):
    """Write one vendor answer as readable JSON, an empty line after it."""
    with LOGS_LOCK:
        if not make_logs_directory():
            return
        try:
            with open(answer_file_path(access_key), "a", encoding="utf-8") as handle:
                handle.write(pretty_answer(raw_answer) + "\n\n")
        except OSError as error:
            report_a_log_problem(f"a vendor answer could not be written: {error}")


def keep_vendor_error(access_key, error_code, body):
    """Write one refusal of the vendor with its code and the moment it arrived."""
    with LOGS_LOCK:
        if not make_logs_directory():
            return
        try:
            with open(error_file_path(access_key), "a", encoding="utf-8") as handle:
                handle.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} the vendor refused with code {error_code}\n")
                handle.write(pretty_answer(body) + "\n\n")
        except OSError as error:
            report_a_log_problem(f"a vendor refusal could not be written: {error}")


def start_journal():
    """Open the journal of this run, after moving the journal of the previous run away."""
    global JOURNAL_FILE
    moved = ""
    with LOGS_LOCK:
        if not make_logs_directory():
            return
        path = os.path.join(logs_directory(), settings.JOURNAL_FILE_NAME)
        moved = move_into_a_dated_directory(path)
        try:
            JOURNAL_FILE = open(path, "a", encoding="utf-8")
        except OSError as error:
            JOURNAL_FILE = None
            print(f"the journal file is not writable: {error}", flush=True)
    if moved:
        tell(
            f"the journal of the previous run moved to "
            f"{name_of_the_directory_that_holds(moved)}/{os.path.basename(moved)}"
        )


def write_journal_line(line):
    """Keep one line in the journal of this run, when the journal is open."""
    if JOURNAL_FILE is None:
        return
    with LOGS_LOCK:
        try:
            JOURNAL_FILE.write(line + "\n")
            JOURNAL_FILE.flush()
        except OSError as error:
            report_a_log_problem(f"a journal line could not be written: {error}")


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
        raw_answer = answer.read().decode("utf-8")
    # The answer is kept exactly as it arrived, before anything is taken out
    # of it: the raw shape is what shows how the vendor rotates addresses
    # and camouflage names from one pass to the next.
    keep_vendor_answer(access_key, raw_answer)
    return json.loads(raw_answer)


def vendor_request_with_retries(path, access_key, hardware_id, query="", what=""):
    """Ask the vendor API, repeat a failed call, and explain every failure."""
    complaint = ""
    for attempt in range(1, settings.VENDOR_ATTEMPTS + 1):
        try:
            return vendor_request(path, access_key, hardware_id, query)
        except urllib.error.HTTPError as error:
            complaint = error.read().decode("utf-8", "replace").strip() or str(error)
            keep_vendor_error(access_key, error.code, complaint)
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
    skipped = 0
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
            if node is None:
                continue
            if not node["address"] or not node["uuid"]:
                # A node without an address or without a key is a broken entry
                # in every client, so it is better left out here.
                skipped += 1
                continue
            nodes.append(node)
    if skipped:
        tell(f"{skipped} entries were left out: they came without an address or without a key")
    tell(f"collected {len(nodes)} nodes for key {shorten(access_key)}")
    return nodes


def moment_to_epoch(moment):
    """Turn the vendor moment into a unix time, keeping its own time zone."""
    cleaned = (moment or "").strip()
    if cleaned.endswith("Z"):
        cleaned = cleaned[:-1] + "+0000"
    for pattern in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            # The moment carries its own offset, and timestamp() respects it.
            # A local time call here would move the date by the machine offset.
            return int(datetime.datetime.strptime(cleaned, pattern).timestamp())
        except ValueError:
            continue
    tell(f"the moment {moment} was not understood")
    return 0


def read_subscription_expiry(access_key, hardware_id):
    """Read the subscription end date, so clients can show it."""
    try:
        profile = vendor_request_with_retries(
            "/subscription/profile", access_key, hardware_id, what="the subscription profile"
        )
    except RuntimeError as error:
        tell(f"the subscription end date is unknown: {error}")
        return 0
    return moment_to_epoch(profile.get("expiration_at"))


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
        start_a_fresh_log_pass(self.access_key)
        try:
            nodes = collect_nodes(self.access_key, self.hardware_id)
        except Exception as error:  # noqa: BLE001 - a failed pass keeps the previous list
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


def looks_like_a_device_id(value):
    """A device id travels in a header, so it must hold plain printable text."""
    return 0 < len(value) <= 128 and value.isascii() and value.isprintable()


def hardware_id_for(access_key, requested):
    """Pick the device id: the asked one, the configured one, or a random one."""
    asked = (requested or "").strip()
    if asked and not looks_like_a_device_id(asked):
        # A value with control characters would make every vendor call fail.
        tell("the device id in the address holds characters the vendor does not expect, it is left out")
        asked = ""
    if asked:
        return asked
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


def answer_raw(nodes):
    """The open list of links, one per line."""
    return "\n".join(node_to_link(node) for node in nodes) + "\n"


def answer_base64(nodes):
    """The same list in base64, the format almost every client expects."""
    return base64.b64encode(answer_raw(nodes).encode("utf-8")).decode("ascii")


def yaml_text(value):
    """A YAML double quoted text: the escaping of JSON is valid YAML as well."""
    return json.dumps(str(value), ensure_ascii=False)


def answer_clash(nodes):
    """YAML for Clash, Mihomo and Stash, with one automatic test group."""
    names = ", ".join(yaml_text(node["name"]) for node in nodes)
    lines = ["proxies:"]
    for node in nodes:
        lines.append(f"  - name: {yaml_text(node['name'])}")
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


def answer_singbox(nodes):
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


def answer_singbox_full(nodes):
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
        "outbounds": json.loads(answer_singbox(nodes))["outbounds"],
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


def answer_xray(nodes):
    """JSON outbounds for Xray and for the 3x-ui panel."""
    return json.dumps([xray_outbound(node) for node in nodes], ensure_ascii=False, indent=2)


def answer_xray_full(nodes):
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


def answer_html(nodes):
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


def answer_csv(nodes):
    """A table for manual entry on a router or in any client that asks by hand."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(
        [
            "name",
            "address",
            "port",
            "camouflage_name",
            "fingerprint",
            "public_key",
            "short_id",
            "uuid",
            "flow",
            "link",
        ]
    )
    for node in nodes:
        writer.writerow(
            [
                node["name"],
                node["address"],
                node["port"],
                node["sni"],
                node["fingerprint"],
                node["public_key"],
                node["short_id"],
                node["uuid"],
                node["flow"],
                node_to_link(node),
            ]
        )
    return buffer.getvalue()


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


def subscription_headers(snapshot, node_count, age_seconds):
    """The headers every client reads, and the end date only when it is known."""
    headers = [
        ("Profile-Title", settings.PROFILE_TITLE),
        ("Profile-Update-Interval", str(settings.PROFILE_UPDATE_INTERVAL_HOURS)),
        ("Profile-web-page-url", settings.PROFILE_HOME_PAGE),
    ]
    if snapshot.expiry:
        headers.append(
            ("Subscription-Userinfo", f"upload=0; download=0; total=0; expire={snapshot.expiry}")
        )
    else:
        # Some clients read a zero in this header as an expired subscription,
        # so without a known date it stays away completely.
        tell("the subscription end date is unknown, the header about it is left out")
    headers.append(("X-Bridge-Nodes", str(node_count)))
    headers.append(("X-Bridge-Age-Seconds", str(int(age_seconds or 0))))
    return headers


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
        body = render_function(nodes).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        for name, value in subscription_headers(snapshot, len(nodes), age):
            self.send_header(name, value)
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

    def answer_scheme(self):
        """The scheme of the listener this request arrived on, read from the socket."""
        return "https" if isinstance(self.connection, ssl.SSLSocket) else "http"

    def root_page(self):
        scheme = self.answer_scheme()
        own_port = settings.HTTPS_PORT if scheme == "https" else settings.HTTP_PORT
        host = self.headers.get("Host") or f"{settings.LISTEN_ADDRESS}:{own_port}"
        lines = [
            f"{settings.PROFILE_TITLE} subscription bridge to freedom, version {settings.PROGRAM_VERSION}.",
            "",
            f"Put your access key into the address, and you get {len(ANSWERS)} answers:",
            "",
        ]
        for suffix, description in settings.ANSWER_FORMATS:
            lines.append(f"{scheme}://{host}/sub/<access key>/{suffix}")
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


def explain_busy_port(port, value_name):
    """Tell the user who holds the port and how to look at it."""
    tell(f"the port {port} is not free, another program holds it")
    tell(f"look at the holder with: ss -tlnp | grep {port}")
    tell(f"on macOS use: lsof -i :{port}, on Windows use: netstat -ano | findstr {port}")
    tell(f"stop the holder, or take another number in settings.py: {value_name}")


def start_plain_server():
    """Serve plain HTTP, which works with every client."""
    try:
        server = HTTPServer((settings.LISTEN_ADDRESS, settings.HTTP_PORT), BridgeAnswerHandler)
    except OSError as error:
        tell(f"the plain port {settings.HTTP_PORT} is not free: {error}")
        explain_busy_port(settings.HTTP_PORT, "HTTP_PORT")
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
        explain_busy_port(settings.HTTPS_PORT, "HTTPS_PORT")
        return None
    except ssl.SSLError as error:
        tell(f"the certificate is not usable: {error}")
        return None
    tell(f"HTTPS is listening on https://{settings.LISTEN_ADDRESS}:{settings.HTTPS_PORT}")
    tell("the certificate is self signed, so a client needs permission to accept it")
    return server


def main():
    start_journal()
    for signal_name in ("SIGINT", "SIGTERM"):
        if hasattr(signal, signal_name):
            signal.signal(getattr(signal, signal_name), note_the_stop_request)
    tell(f"{settings.PROGRAM_NAME} version {settings.PROGRAM_VERSION} starts")
    tell(f"values were taken from settings.py next to the program, the vendor is {settings.VENDOR_HOST}")
    servers = [server for server in (start_plain_server(), start_https_server()) if server is not None]
    if not servers:
        tell("no port could be opened, nothing to do, stopping")
        return 1
    for server in servers:
        threading.Thread(target=server.serve_forever, daemon=True).start()
    tell("the bridge is ready, put an address from the page above into your client")
    STOP_REQUESTED.wait()
    for server in servers:
        server.shutdown()
        server.server_close()
    tell("the ports are closed, the program stops")
    return 0


if __name__ == "__main__":
    sys.exit(main())
