"""Checks for the sotavpn bridge to freedom.

Run them with:
    python3 -m unittest test_sotavpn_bridge_to_freedom

The checks cover the answers the program builds and the behaviour when the
vendor stops answering. They do not touch the network and they do not start
the servers, so they are safe to run anywhere.
"""

import base64
import io
import json
import os
import shutil
import signal
import ssl
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from unittest import mock

import settings
import sotavpn_bridge_to_freedom as bridge

# While the checks run the program stays quiet, and the runner prints no
# decorative line of repeated symbols: plain result, plain words.
settings.VERBOSE = 0
unittest.TextTestResult.separator1 = ""
unittest.TextTestResult.separator2 = ""

LOGS_DIRECTORY_OF_THE_CHECKS = ""
KEPT_LOGS_DIRECTORY = ""


def setUpModule():
    """Send every log of the checks into a temporary directory, not into the repository."""
    global LOGS_DIRECTORY_OF_THE_CHECKS, KEPT_LOGS_DIRECTORY
    KEPT_LOGS_DIRECTORY = settings.LOGS_DIRECTORY
    LOGS_DIRECTORY_OF_THE_CHECKS = tempfile.mkdtemp(prefix="bridge-logs-of-the-checks-")
    settings.LOGS_DIRECTORY = LOGS_DIRECTORY_OF_THE_CHECKS


def tearDownModule():
    """Take the temporary log directory away and put the setting back."""
    settings.LOGS_DIRECTORY = KEPT_LOGS_DIRECTORY
    shutil.rmtree(LOGS_DIRECTORY_OF_THE_CHECKS, ignore_errors=True)


def put_a_stand_in(case, target, name, replacement):
    """Put a stand-in in place for the length of one check and take it away after.

    The cleanup of the check itself does the restoring, so a check never has
    to keep a copy of what it replaced and never forgets to put it back.
    """
    patcher = mock.patch.object(target, name, replacement)
    case.addCleanup(patcher.stop)
    return patcher.start()


def sample_nodes():
    """Two nodes that look exactly like the ones the vendor hands out."""
    return [
        {
            "name": "Sota AR Argentina ar-bue-01",
            "address": "13.140.54.5",
            "port": 443,
            "uuid": "8a629a6c-300c-4f98-9169-e56d47977668",
            "flow": "xtls-rprx-vision",
            "sni": "gridsnap.org",
            "fingerprint": "chrome",
            "public_key": "SbVKOEMjK0sIlbwg4akyBg5mL5KZwwB-ed4eEE7YnRc",
            "short_id": "6ba85179e30d4fc2",
        },
        {
            "name": "Sota NL Netherlands nl-ams-01",
            "address": "64.137.54.2",
            "port": 443,
            "uuid": "8a629a6c-300c-4f98-9169-e56d47977668",
            "flow": "xtls-rprx-vision",
            "sni": "differencescope.com",
            "fingerprint": "qq",
            "public_key": "SbVKOEMjK0sIlbwg4akyBg5mL5KZwwB-ed4eEE7YnRc",
            "short_id": "6ba85179e30d4fc2",
        },
    ]


class AnswerCheck(unittest.TestCase):
    def setUp(self):
        self.nodes = sample_nodes()
        self.nodes_text = bridge.answer_raw(self.nodes)

    def test_link_carries_every_parameter(self):
        link = self.nodes_text.splitlines()[0]
        self.assertTrue(link.startswith("vless://8a629a6c-300c-4f98-9169-e56d47977668@13.140.54.5:443?"))
        for piece in ("security=reality", "flow=xtls-rprx-vision", "sni=gridsnap.org", "fp=chrome", "pbk=SbVK", "sid=6ba85179e30d4fc2", "type=tcp"):
            self.assertIn(piece, link)

    def test_base64_answer_decodes_into_the_same_links(self):
        decoded = base64.b64decode(bridge.answer_base64(self.nodes)).decode("utf-8")
        self.assertEqual(decoded, self.nodes_text)
        self.assertEqual(len(decoded.splitlines()), 2)

    def test_clash_answer_has_an_automatic_test_group(self):
        text = bridge.answer_clash(self.nodes)
        self.assertIn("proxies:", text)
        self.assertIn("type: url-test", text)
        self.assertIn(f"url: {settings.AUTOMATIC_TEST_URL}", text)
        for node in self.nodes:
            self.assertIn(node["name"], text)
            self.assertIn(f"public-key: {node['public_key']}", text)

    def test_singbox_answer_has_an_automatic_test_group(self):
        document = json.loads(bridge.answer_singbox(self.nodes))
        tags = [outbound["tag"] for outbound in document["outbounds"]]
        self.assertIn("Sota automatic", tags)
        automatic = document["outbounds"][tags.index("Sota automatic")]
        self.assertEqual(automatic["type"], "urltest")
        self.assertEqual(sorted(automatic["outbounds"]), sorted(node["name"] for node in self.nodes))

    def test_singbox_full_answer_has_a_tun_inbound(self):
        document = json.loads(bridge.answer_singbox_full(self.nodes))
        self.assertEqual(document["inbounds"][0]["type"], "tun")
        self.assertEqual(document["route"]["final"], "Sota automatic")

    def test_xray_answer_has_one_vnext_per_node(self):
        document = json.loads(bridge.answer_xray(self.nodes))
        self.assertEqual(len(document), len(self.nodes))
        self.assertEqual(document[0]["settings"]["vnext"][0]["address"], "13.140.54.5")
        self.assertEqual(document[0]["streamSettings"]["security"], "reality")

    def test_xray_full_answer_has_a_local_socks_port(self):
        document = json.loads(bridge.answer_xray_full(self.nodes))
        self.assertEqual(document["inbounds"][0]["protocol"], "socks")
        self.assertEqual(document["inbounds"][0]["port"], settings.XRAY_LOCAL_SOCKS_PORT)

    def test_html_answer_shows_every_node(self):
        text = bridge.answer_html(self.nodes)
        for node in self.nodes:
            self.assertIn(node["name"], text)
            self.assertIn(node["public_key"], text)

    def test_csv_answer_has_one_row_per_node_and_a_header(self):
        lines = bridge.answer_csv(self.nodes).splitlines()
        self.assertEqual(len(lines), len(self.nodes) + 1)
        self.assertTrue(lines[0].startswith("name,address,port,camouflage_name"))
        self.assertIn("13.140.54.5", lines[1])

    def test_csv_answer_quotes_a_name_with_a_comma(self):
        node = dict(self.nodes[0], name="Sota AR, Argentina")
        line = bridge.answer_csv([node]).splitlines()[1]
        self.assertTrue(line.startswith('"Sota AR, Argentina",'))

    def test_clash_answer_survives_a_name_with_a_quote(self):
        node = dict(self.nodes[0], name='Sota AR "quoted"')
        text = bridge.answer_clash([node])
        self.assertIn('name: "Sota AR \\"quoted\\""', text)
        self.assertIn('proxies: ["Sota AR \\"quoted\\""]', text)

    def test_every_answer_carries_its_builder_its_type_and_its_description(self):
        for suffix, (builder, content_type, description) in bridge.ANSWERS.items():
            self.assertTrue(callable(builder), suffix)
            self.assertIn("/", content_type, suffix)
            self.assertTrue(description.strip(), suffix)

    def test_the_group_names_of_the_answers_come_from_the_settings(self):
        put_a_stand_in(self, settings, "AUTOMATIC_GROUP_NAME", "My automatic")
        put_a_stand_in(self, settings, "MANUAL_GROUP_NAME", "My manual")
        clash = bridge.answer_clash(self.nodes)
        singbox = json.loads(bridge.answer_singbox(self.nodes))
        full = json.loads(bridge.answer_singbox_full(self.nodes))
        self.assertIn('  - name: "My automatic"', clash)
        self.assertIn('  - name: "My manual"', clash)
        self.assertIn('    proxies: ["My automatic"]', clash)
        self.assertIn('  - MATCH,"My manual"', clash)
        self.assertIn("My automatic", [outbound["tag"] for outbound in singbox["outbounds"]])
        self.assertEqual(full["route"]["final"], "My automatic")

    def test_one_interval_serves_the_two_answers_that_want_it(self):
        put_a_stand_in(self, settings, "AUTOMATIC_TEST_URL", "http://the.check/generate_204")
        put_a_stand_in(self, settings, "AUTOMATIC_TEST_INTERVAL_SECONDS", 900)
        clash = bridge.answer_clash(self.nodes)
        singbox = json.loads(bridge.answer_singbox(self.nodes))
        automatic = [out for out in singbox["outbounds"] if out["type"] == "urltest"][0]
        self.assertIn("url: http://the.check/generate_204", clash)
        self.assertIn("interval: 900", clash)
        self.assertEqual(automatic["url"], "http://the.check/generate_204")
        self.assertEqual(automatic["interval"], "900s")


class SubscriptionMomentCheck(unittest.TestCase):
    def test_a_utc_moment_keeps_its_own_time_zone(self):
        self.assertEqual(bridge.moment_to_epoch("2026-11-12T14:31:59.800289+0000"), 1794493919)
        self.assertEqual(bridge.moment_to_epoch("2026-11-12T14:31:59.800289Z"), 1794493919)
        self.assertEqual(bridge.moment_to_epoch("2026-11-12T14:31:59+0000"), 1794493919)

    def test_an_offset_moment_is_counted_from_utc(self):
        self.assertEqual(bridge.moment_to_epoch("2026-11-12T17:31:59+0300"), 1794493919)
        self.assertEqual(bridge.moment_to_epoch("2026-11-12T11:31:59-0300"), 1794493919)

    def test_the_time_zone_of_the_machine_does_not_move_the_moment(self):
        original = os.environ.get("TZ")
        answers = []
        try:
            for zone in ("UTC", "Asia/Tokyo", "America/Argentina/Buenos_Aires"):
                os.environ["TZ"] = zone
                time.tzset()
                answers.append(bridge.moment_to_epoch("2026-11-12T14:31:59.800289+0000"))
        finally:
            if original is None:
                os.environ.pop("TZ", None)
            else:
                os.environ["TZ"] = original
            time.tzset()
        self.assertEqual(answers, [1794493919, 1794493919, 1794493919])

    def test_an_unknown_moment_gives_zero(self):
        self.assertEqual(bridge.moment_to_epoch(""), 0)
        self.assertEqual(bridge.moment_to_epoch(None), 0)
        self.assertEqual(bridge.moment_to_epoch("next month"), 0)


class ClientNameCheck(unittest.TestCase):
    def test_clash_family_gets_yaml(self):
        self.assertEqual(bridge.guess_answer_from_client_name("Mihomo/1.18.0"), "clash")
        self.assertEqual(bridge.guess_answer_from_client_name("clash-verge/2.0"), "clash")
        self.assertEqual(bridge.guess_answer_from_client_name("Stash/2.5"), "clash")

    def test_sing_box_family_gets_json(self):
        self.assertEqual(bridge.guess_answer_from_client_name("sing-box 1.10.0"), "singbox")
        self.assertEqual(bridge.guess_answer_from_client_name("Hiddify/2.0"), "singbox")

    def test_every_other_client_gets_base64(self):
        self.assertEqual(bridge.guess_answer_from_client_name("v2rayN/7.0"), "base64")
        self.assertEqual(bridge.guess_answer_from_client_name(""), "base64")
        self.assertEqual(bridge.guess_answer_from_client_name(None), "base64")


class RootPageCheck(unittest.TestCase):
    """The root page of the port the visitor came through tells that very port."""

    def setUp(self):
        self.opened_servers = []

    def tearDown(self):
        for server in self.opened_servers:
            server.shutdown()
            server.server_close()

    def page_of_a_visitor_that_came_through(self, secure):
        """Open a listener of the real program on a free port and read its root page."""
        server = bridge.HTTPServer(("127.0.0.1", 0), bridge.BridgeAnswerHandler)
        if secure:
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.load_cert_chain(
                bridge.path_next_to_the_program(settings.CERTIFICATE_FILE),
                bridge.path_next_to_the_program(settings.PRIVATE_KEY_FILE),
            )
            server.socket = context.wrap_socket(server.socket, server_side=True)
        self.opened_servers.append(server)
        port = server.server_address[1]
        threading.Thread(target=server.serve_forever, daemon=True).start()
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        scheme = "https" if secure else "http"
        with urllib.request.urlopen(f"{scheme}://127.0.0.1:{port}/", context=context, timeout=15) as answer:
            return answer.read().decode("utf-8"), port

    def address_lines_of(self, page):
        return [line for line in page.splitlines() if "/sub/<access key>/" in line]

    def test_a_plain_visitor_sees_plain_addresses(self):
        page, port = self.page_of_a_visitor_that_came_through(secure=False)
        addresses = self.address_lines_of(page)
        self.assertEqual(len(addresses), len(bridge.ANSWERS))
        for line in addresses:
            self.assertTrue(line.startswith(f"http://127.0.0.1:{port}/sub/<access key>/"), line)

    def test_a_secure_visitor_sees_secure_addresses(self):
        page, port = self.page_of_a_visitor_that_came_through(secure=True)
        addresses = self.address_lines_of(page)
        self.assertEqual(len(addresses), len(bridge.ANSWERS))
        for line in addresses:
            self.assertTrue(line.startswith(f"https://127.0.0.1:{port}/sub/<access key>/"), line)

    def test_the_secure_page_never_sends_the_visitor_to_the_plain_port(self):
        page, _ = self.page_of_a_visitor_that_came_through(secure=True)
        self.assertNotIn(f"http://127.0.0.1:{settings.HTTP_PORT}", page)

    def test_the_refresh_seconds_of_the_page_come_from_the_settings(self):
        kept = settings.SNAPSHOT_FRESH_SECONDS
        settings.SNAPSHOT_FRESH_SECONDS = 7
        try:
            page, _ = self.page_of_a_visitor_that_came_through(secure=False)
        finally:
            settings.SNAPSHOT_FRESH_SECONDS = kept
        self.assertIn("older than 7 seconds", page)


class SnapshotCheck(unittest.TestCase):
    def setUp(self):
        self.snapshot = bridge.AccountSnapshot("access key", "device id")
        self.snapshot.nodes = sample_nodes()
        self.snapshot.collected_at = 1.0

    def a_collection_that_breaks(self, complaint, error=ValueError):
        """A collection that fails the way a vendor answer that cannot be read fails."""

        def broken_collection(access_key, hardware_id):
            raise error(complaint)

        return broken_collection

    def test_old_nodes_survive_a_failed_collection(self):
        put_a_stand_in(
            self, bridge, "collect_nodes", self.a_collection_that_breaks("the vendor is unreachable", RuntimeError)
        )
        nodes, age, complaint = self.snapshot.nodes_for_request()
        self.assertEqual(len(nodes), 2)
        self.assertIn("unreachable", complaint)
        self.assertIsNotNone(age)

    def test_a_fresh_list_is_given_back_without_a_new_collection(self):
        self.snapshot.collected_at = bridge.time.monotonic()

        def must_not_be_called(access_key, hardware_id):
            self.fail("a fresh list must not be collected again")

        put_a_stand_in(self, bridge, "collect_nodes", must_not_be_called)
        nodes, age, _complaint = self.snapshot.nodes_for_request()
        self.assertEqual(len(nodes), 2)
        self.assertLess(age, settings.SNAPSHOT_FRESH_SECONDS)

    def test_an_unexpected_failure_also_keeps_the_old_nodes(self):
        put_a_stand_in(
            self, bridge, "collect_nodes", self.a_collection_that_breaks("a shape the program did not expect")
        )
        nodes, _age, complaint = self.snapshot.nodes_for_request()
        self.assertEqual(len(nodes), 2)
        self.assertIn("did not expect", complaint)


class SubscriptionHeaderCheck(unittest.TestCase):
    def setUp(self):
        self.snapshot = bridge.AccountSnapshot("access key", "device id")

    def header_names(self, expiry):
        self.snapshot.expiry = expiry
        return [name for name, _ in bridge.subscription_headers(self.snapshot, 2, 7)]

    def test_the_end_date_header_appears_when_the_date_is_known(self):
        self.snapshot.expiry = 1794493919
        sent = dict(bridge.subscription_headers(self.snapshot, 2, 7))
        self.assertEqual(sent["Subscription-Userinfo"], "upload=0; download=0; total=0; expire=1794493919")
        self.assertEqual(sent["X-Bridge-Nodes"], "2")
        self.assertEqual(sent["X-Bridge-Age-Seconds"], "7")

    def test_the_end_date_header_stays_away_when_the_date_is_unknown(self):
        self.assertNotIn("Subscription-Userinfo", self.header_names(0))


class CollectionCheck(unittest.TestCase):
    def setUp(self):
        put_a_stand_in(self, settings, "VENDOR_PAUSE_BETWEEN_REQUESTS_SECONDS", 0)
        put_a_stand_in(self, bridge, "vendor_request_with_retries", self.an_answer_of_the_vendor)

    def an_answer_of_the_vendor(self, path, access_key, hardware_id, query="", what=""):
        """The two answers a collection needs: the location list and one configuration."""
        if path == "/connection/list":
            return [
                {
                    "id": 7,
                    "name": "Argentina",
                    "shortname": "AR",
                    "gateways": [
                        {"name": "ar-bue-01", "address": "13.140.54.5"},
                        {"name": "ar-bue-02", "address": ""},
                    ],
                }
            ]
        return {
            "configuration": {
                "outbounds": [
                    {
                        "type": "vless",
                        "server_port": 443,
                        "uuid": "8a629a6c-300c-4f98-9169-e56d47977668",
                        "flow": "xtls-rprx-vision",
                        "tls": {
                            "server_name": "gridsnap.org",
                            "utls": {"fingerprint": "chrome"},
                            "reality": {"public_key": "SbVK", "short_id": "6ba85179e30d4fc2"},
                        },
                    }
                ]
            }
        }

    def test_a_gateway_without_an_address_is_left_out(self):
        nodes = bridge.collect_nodes("access key", "device id")
        self.assertEqual(len(nodes), 1)
        self.assertEqual(nodes[0]["address"], "13.140.54.5")
        self.assertIn("AR", nodes[0]["name"])
        self.assertIn("ar-bue-01", nodes[0]["name"])
        self.assertEqual(nodes[0]["sni"], "gridsnap.org")


class DeviceIdCheck(unittest.TestCase):
    def test_plain_text_is_accepted(self):
        self.assertTrue(bridge.looks_like_a_device_id("bc595c0af2e559eb9b19aec5aaf597dd6546b6945df791990de5f3d098a4289e"))
        self.assertTrue(bridge.looks_like_a_device_id("device-id-01"))

    def test_text_that_breaks_a_header_is_refused(self):
        self.assertFalse(bridge.looks_like_a_device_id(""))
        self.assertFalse(bridge.looks_like_a_device_id("two\nlines"))
        self.assertFalse(bridge.looks_like_a_device_id("inject\r\nX-Page: 1"))
        self.assertFalse(bridge.looks_like_a_device_id("x" * 129))

    def test_a_broken_asked_id_falls_back_to_the_own_one(self):
        key = "the key of the device id check"
        invented = bridge.hardware_id_for(key, "")
        self.assertEqual(bridge.hardware_id_for(key, "inject\r\nX-Page: 1"), invented)
        self.assertNotIn("inject", invented)

    def test_an_empty_ask_gives_the_settings_value_or_an_invented_one(self):
        given = bridge.hardware_id_for("the key of the settings device id", "")
        if settings.DEFAULT_HARDWARE_ID:
            self.assertEqual(given, settings.DEFAULT_HARDWARE_ID)
        else:
            self.assertEqual(len(given), 64)


class SettingsCheck(unittest.TestCase):
    """Every value of the settings is usable as it stands."""

    def test_ports_are_usable_by_a_user(self):
        for port in (settings.HTTP_PORT, settings.HTTPS_PORT):
            self.assertGreater(port, 1024)
            self.assertLess(port, 32768)

    def test_times_are_reasonable(self):
        self.assertGreater(settings.SNAPSHOT_FRESH_SECONDS, 0)
        self.assertGreater(settings.VENDOR_TIME_OUT_SECONDS, 0)
        self.assertGreaterEqual(settings.VENDOR_ATTEMPTS, 1)

    def test_verbose_is_a_switch_of_one_and_zero(self):
        self.assertIn(settings.VERBOSE, (0, 1))

    def test_the_device_id_of_the_settings_is_a_hash_or_empty(self):
        value = settings.DEFAULT_HARDWARE_ID
        self.assertTrue(
            value == ""
            or (len(value) == 64 and all(character in "0123456789abcdef" for character in value))
        )

    def test_the_vendor_and_the_name_prefix_are_set(self):
        self.assertTrue(settings.VENDOR_HOST)
        self.assertTrue(settings.VENDOR_BASE_PATH.startswith("/"))
        self.assertTrue(settings.NODE_NAME_PREFIX)

    def test_every_file_of_the_logs_has_a_suffix_of_its_own(self):
        suffixes = (
            settings.ANSWER_FILE_SUFFIX,
            settings.ERROR_FILE_SUFFIX,
            settings.NAMES_FILE_SUFFIX,
            settings.SERVERS_FILE_SUFFIX,
            settings.FINGERPRINTS_FILE_SUFFIX,
        )
        self.assertEqual(len(set(suffixes)), len(suffixes))

    def test_the_certificate_files_are_in_the_repository(self):
        for path in (settings.CERTIFICATE_FILE, settings.PRIVATE_KEY_FILE):
            self.assertTrue(os.path.isfile(bridge.path_next_to_the_program(path)), f"{path} is missing")

    def test_the_header_of_the_program_carries_the_name_the_source_and_the_author(self):
        header = bridge.__doc__ or ""
        self.assertIn(settings.PROGRAM_NAME, header)
        self.assertIn(settings.PROGRAM_SOURCE_URL, header)
        self.assertIn(settings.PROGRAM_AUTHOR, header)


class LogArchiveCheck(unittest.TestCase):
    """The raw vendor answers and the journal, in a directory of their own."""

    def setUp(self):
        self.directory = tempfile.mkdtemp(prefix="bridge-logs-")
        self.key = "the-access-key-of-the-log-checks"
        self.other_key = "the-access-key-of-the-other-account"
        put_a_stand_in(self, settings, "LOGS_DIRECTORY", self.directory)
        put_a_stand_in(self, bridge, "JOURNAL_FILE", None)
        self.addCleanup(shutil.rmtree, self.directory, ignore_errors=True)
        self.addCleanup(self.close_the_journal)

    def answer_path(self, key=None):
        return os.path.join(self.directory, bridge.answer_file_name(key or self.key))

    def error_path(self, key=None):
        return os.path.join(self.directory, bridge.error_file_name(key or self.key))

    def journal_path(self):
        return os.path.join(self.directory, settings.JOURNAL_FILE_NAME)

    def moment_of(self, path):
        """The moment the file was born, which is what an archived copy carries."""
        return time.strftime(
            settings.ARCHIVE_MOMENT_FORMAT,
            time.localtime(bridge.moment_of_the_birth_of_a_file(path)),
        )

    def read(self, path):
        with open(path, encoding="utf-8") as handle:
            return handle.read()

    def close_the_journal(self):
        if bridge.JOURNAL_FILE is not None:
            bridge.JOURNAL_FILE.close()
            bridge.JOURNAL_FILE = None

    def test_the_first_pass_opens_the_file_of_its_own_account(self):
        bridge.start_a_fresh_log_pass(self.key)
        bridge.keep_vendor_answer(self.key, '{"locations": []}')
        self.assertEqual(self.read(self.answer_path()), '{\n\t"locations": []\n}\n\n')
        self.assertEqual(os.listdir(self.directory), [bridge.answer_file_name(self.key)])

    def test_the_answer_is_printed_with_tabs_and_readable_text(self):
        bridge.start_a_fresh_log_pass(self.key)
        bridge.keep_vendor_answer(self.key, '{"locations":[{"id":8,"name":"Лучший сервер"}]}')
        text = self.read(self.answer_path())
        self.assertIn('\n\t"locations": [\n\t\t{\n\t\t\t"id": 8,\n\t\t\t"name": "Лучший сервер"\n\t\t}\n\t]\n', text)
        self.assertNotIn("\\u", text)

    def test_one_pass_keeps_every_answer_of_that_pass_in_one_file(self):
        bridge.start_a_fresh_log_pass(self.key)
        for answer in ('{"a": 1}', '[{"b": 2}]', '{"c": 3}'):
            bridge.keep_vendor_answer(self.key, answer)
        blocks = [block for block in self.read(self.answer_path()).split("\n\n") if block.strip()]
        self.assertEqual([json.loads(block) for block in blocks], [{"a": 1}, [{"b": 2}], {"c": 3}])
        self.assertEqual(len(os.listdir(self.directory)), 1)

    def test_two_accounts_keep_their_answers_apart(self):
        bridge.start_a_fresh_log_pass(self.key)
        bridge.start_a_fresh_log_pass(self.other_key)
        bridge.keep_vendor_answer(self.key, '{"account": "first"}')
        bridge.keep_vendor_answer(self.other_key, '{"account": "second"}')
        self.assertEqual(json.loads(self.read(self.answer_path())), {"account": "first"})
        self.assertEqual(json.loads(self.read(self.answer_path(self.other_key))), {"account": "second"})
        self.assertEqual(
            sorted(os.listdir(self.directory)),
            sorted([bridge.answer_file_name(self.key), bridge.answer_file_name(self.other_key)]),
        )

    def test_the_next_pass_moves_the_previous_answers_aside(self):
        bridge.start_a_fresh_log_pass(self.key)
        bridge.keep_vendor_answer(self.key, '{"first": true}')
        moment = self.moment_of(self.answer_path())
        bridge.start_a_fresh_log_pass(self.key)
        bridge.keep_vendor_answer(self.key, '{"second": true}')
        self.assertEqual(json.loads(self.read(self.answer_path())), {"second": True})
        archived = os.path.join(self.directory, f"{moment}_{bridge.answer_file_name(self.key)}")
        self.assertEqual(json.loads(self.read(archived)), {"first": True})

    def test_the_logs_directory_stays_flat(self):
        bridge.start_a_fresh_log_pass(self.key)
        bridge.keep_vendor_answer(self.key, '{"first": true}')
        bridge.start_a_fresh_log_pass(self.key)
        bridge.keep_vendor_error(self.key, 500, "the vendor broke")
        for entry in os.listdir(self.directory):
            self.assertTrue(os.path.isfile(os.path.join(self.directory, entry)), entry)

    def test_a_pass_that_arrives_first_finds_nothing_to_move(self):
        bridge.start_a_fresh_log_pass(self.key)
        self.assertEqual(os.listdir(self.directory), [])

    def test_two_files_created_in_the_same_second_get_two_names(self):
        os.makedirs(self.directory, exist_ok=True)
        first = os.path.join(self.directory, "first")
        second = os.path.join(self.directory, "second")
        for path in (first, second):
            open(path, "w", encoding="utf-8").close()
        same = time.time()
        os.utime(first, (same, same))
        os.utime(second, (same, same))
        moved_first = bridge.move_a_log_file_aside(first)
        moved_second = bridge.move_a_log_file_aside(second)
        self.assertNotEqual(moved_first, moved_second)
        self.assertEqual(os.path.dirname(moved_first), self.directory)
        self.assertTrue(os.path.exists(moved_first))
        self.assertTrue(os.path.exists(moved_second))

    def test_a_file_that_is_not_there_is_not_moved(self):
        self.assertEqual(bridge.move_a_log_file_aside(self.answer_path()), "")

    def test_the_journal_of_the_previous_run_moves_away_on_a_new_start(self):
        os.makedirs(self.directory, exist_ok=True)
        with open(self.journal_path(), "w", encoding="utf-8") as handle:
            handle.write("the run of yesterday\n")
        moment = self.moment_of(self.journal_path())
        bridge.start_journal()
        bridge.tell("the new run writes its own journal")
        fresh = self.read(self.journal_path())
        self.close_the_journal()
        self.assertNotIn("yesterday", fresh)
        self.assertIn("the new run writes its own journal", fresh)
        self.assertIn("yesterday", self.read(os.path.join(self.directory, f"{moment}_{settings.JOURNAL_FILE_NAME}")))

    def test_the_quiet_mode_still_writes_the_journal(self):
        self.assertEqual(settings.VERBOSE, 0)
        bridge.start_journal()
        bridge.tell("a line nobody sees on the screen")
        kept = self.read(self.journal_path())
        self.close_the_journal()
        self.assertIn("a line nobody sees on the screen", kept)

    def test_a_journal_line_carries_the_moment_and_the_message_only(self):
        bridge.start_journal()
        bridge.tell("the bridge is ready")
        kept = self.read(self.journal_path()).splitlines()[-1]
        self.close_the_journal()
        self.assertRegex(kept, r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} the bridge is ready$")
        self.assertNotIn(f"{settings.PROGRAM_NAME}:", kept)

    def test_a_refusal_of_the_vendor_lands_in_its_own_file(self):
        bridge.start_a_fresh_log_pass(self.key)
        bridge.keep_vendor_error(self.key, 404, '{"detail": "Invalid access key"}')
        self.assertFalse(os.path.exists(self.answer_path()))
        kept = self.read(self.error_path())
        self.assertRegex(kept, r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} the vendor refused with code 404\n")
        self.assertIn('\t"detail": "Invalid access key"\n', kept)

    def test_the_refusals_of_one_account_stay_apart_from_its_answers(self):
        bridge.start_a_fresh_log_pass(self.key)
        bridge.keep_vendor_answer(self.key, '{"locations": []}')
        bridge.keep_vendor_error(self.key, 429, "too many calls")
        self.assertEqual(
            sorted(os.listdir(self.directory)),
            sorted([bridge.answer_file_name(self.key), bridge.error_file_name(self.key)]),
        )
        self.assertIn("too many calls", self.read(self.error_path()))
        self.assertNotIn("too many calls", self.read(self.answer_path()))

    def test_the_next_pass_moves_the_refusals_of_the_previous_one_away(self):
        bridge.start_a_fresh_log_pass(self.key)
        bridge.keep_vendor_error(self.key, 500, "the vendor broke")
        moment = self.moment_of(self.error_path())
        bridge.start_a_fresh_log_pass(self.key)
        self.assertFalse(os.path.exists(self.error_path()))
        archived = os.path.join(self.directory, f"{moment}_{bridge.error_file_name(self.key)}")
        self.assertIn("the vendor broke", self.read(archived))

    def test_the_opening_lines_name_the_source_and_the_author(self):
        kept = (settings.PROGRAM_NAME, settings.PROGRAM_SOURCE_URL, settings.PROGRAM_AUTHOR)
        settings.PROGRAM_NAME = "the program of the checks"
        settings.PROGRAM_SOURCE_URL = "https://example.invalid/the-source-of-the-checks"
        settings.PROGRAM_AUTHOR = "the author of the checks"
        try:
            bridge.start_journal()
            bridge.tell_the_name_the_source_and_the_author()
            lines = self.read(self.journal_path()).splitlines()
        finally:
            settings.PROGRAM_NAME, settings.PROGRAM_SOURCE_URL, settings.PROGRAM_AUTHOR = kept
            self.close_the_journal()
        self.assertIn("the program of the checks version", lines[0])
        self.assertIn("https://example.invalid/the-source-of-the-checks", lines[1])
        self.assertIn("the author of the checks", lines[2])


class FileMomentCheck(unittest.TestCase):
    """The moment of birth of a file is what an archived copy carries."""

    def setUp(self):
        self.directory = tempfile.mkdtemp(prefix="bridge-file-moment-")
        self.addCleanup(shutil.rmtree, self.directory, ignore_errors=True)
        self.path = os.path.join(self.directory, "a file")
        with open(self.path, "w", encoding="utf-8") as handle:
            handle.write("x\n")
        self.asked = []

    def answering_stat(self, output):
        """A stand-in for the external tool that answers one line."""

        def answering(command, **rest):
            self.asked.append(command)
            return mock.Mock(stdout=output)

        return answering

    def test_the_moment_of_birth_is_asked_from_the_tool_stat(self):
        put_a_stand_in(self, bridge.subprocess, "run", self.answering_stat("1789566554\n"))
        self.assertEqual(bridge.moment_of_the_birth_of_a_file(self.path), 1789566554.0)
        self.assertEqual(self.asked[0][0], "stat")

    def test_a_file_system_without_the_moment_of_birth_falls_back_to_the_last_write(self):
        os.utime(self.path, (1789566554, 1789566554))
        put_a_stand_in(self, bridge.subprocess, "run", self.answering_stat("0\n"))
        self.assertEqual(bridge.moment_of_the_birth_of_a_file(self.path), 1789566554.0)

    def test_a_stat_that_cannot_run_falls_back_to_the_last_write(self):
        os.utime(self.path, (1789566554, 1789566554))

        def refusing(command, **rest):
            raise FileNotFoundError("stat is not here")

        put_a_stand_in(self, bridge.subprocess, "run", refusing)
        self.assertEqual(bridge.moment_of_the_birth_of_a_file(self.path), 1789566554.0)

    def test_the_real_tool_answers_a_moment_for_a_file_that_exists(self):
        self.assertGreater(bridge.moment_of_the_birth_of_a_file(self.path), 0)


class UniqueListsCheck(unittest.TestCase):
    """The unique servers, camouflage names and fingerprints of a run, one value per line."""

    def setUp(self):
        self.directory = tempfile.mkdtemp(prefix="bridge-unique-")
        self.key = "the-access-key-of-the-list-checks"
        self.other_key = "the-access-key-of-the-other-lists"
        put_a_stand_in(self, settings, "LOGS_DIRECTORY", self.directory)
        put_a_stand_in(self, bridge, "JOURNAL_FILE", None)
        self.addCleanup(shutil.rmtree, self.directory, ignore_errors=True)
        self.addCleanup(self.close_the_journal)
        bridge.start_journal()
        self.snapshot = bridge.AccountSnapshot(self.key, "device id")

    def close_the_journal(self):
        """Close the journal of this check, so the next check opens its own."""
        if bridge.JOURNAL_FILE is not None:
            bridge.JOURNAL_FILE.close()
            bridge.JOURNAL_FILE = None

    def servers_path(self, key=None):
        return os.path.join(self.directory, bridge.servers_file_name(key or self.key))

    def names_path(self, key=None):
        return os.path.join(self.directory, bridge.names_file_name(key or self.key))

    def fingerprints_path(self, key=None):
        return os.path.join(self.directory, bridge.fingerprints_file_name(key or self.key))

    def read_lines(self, path):
        with open(path, encoding="utf-8") as handle:
            return handle.read().splitlines()

    def journal_text(self):
        with open(os.path.join(self.directory, settings.JOURNAL_FILE_NAME), encoding="utf-8") as handle:
            return handle.read()

    def moment_ns(self, path):
        return os.stat(path).st_mtime_ns

    def a_pass_of(self, nodes):
        self.snapshot.remember_the_unique_servers_names_and_fingerprints(nodes)
        self.snapshot.keep_the_unique_files_of_the_run()

    def test_a_failed_collection_brings_no_files(self):
        def broken(access_key, hardware_id):
            raise RuntimeError("the vendor is unreachable")

        put_a_stand_in(self, bridge, "collect_nodes", broken)
        self.snapshot.collect_locked()
        self.assertEqual(os.listdir(self.directory), [settings.JOURNAL_FILE_NAME])

    def test_the_files_are_born_by_the_first_answered_collection(self):
        put_a_stand_in(self, bridge, "collect_nodes", lambda access_key, hardware_id: sample_nodes())
        put_a_stand_in(self, bridge, "read_subscription_expiry", lambda access_key, hardware_id: 0)
        self.snapshot.collect_locked()
        self.assertEqual(self.read_lines(self.servers_path()), ["13.140.54.5", "64.137.54.2"])
        self.assertEqual(self.read_lines(self.names_path()), ["differencescope.com", "gridsnap.org"])
        self.assertEqual(self.read_lines(self.fingerprints_path()), ["chrome", "qq"])

    def test_one_value_per_line_with_no_repeats(self):
        second_place = dict(sample_nodes()[0], name="Sota AR Argentina ar-bue-02")
        self.a_pass_of(sample_nodes() + [second_place])
        self.assertEqual(self.read_lines(self.servers_path()), ["13.140.54.5", "64.137.54.2"])
        self.assertEqual(self.read_lines(self.names_path()), ["differencescope.com", "gridsnap.org"])
        self.assertEqual(self.read_lines(self.fingerprints_path()), ["chrome", "qq"])

    def test_addresses_sort_as_numbers_and_names_sort_as_text(self):
        self.a_pass_of(
            [
                dict(sample_nodes()[0], address="217.217.109.1", sni="zzz.example"),
                dict(sample_nodes()[0], address="13.140.54.5", sni="aaa.example"),
                dict(sample_nodes()[0], address="64.137.54.2", sni="mmm.example"),
            ]
        )
        self.assertEqual(
            self.read_lines(self.servers_path()), ["13.140.54.5", "64.137.54.2", "217.217.109.1"]
        )
        self.assertEqual(
            self.read_lines(self.names_path()), ["aaa.example", "mmm.example", "zzz.example"]
        )

    def test_an_address_that_is_not_ipv4_goes_after_the_numbers(self):
        self.a_pass_of(
            [
                dict(sample_nodes()[0], address="host.example"),
                dict(sample_nodes()[0], address="13.140.54.5"),
            ]
        )
        self.assertEqual(self.read_lines(self.servers_path()), ["13.140.54.5", "host.example"])

    def test_a_node_without_a_camouflage_name_adds_no_name(self):
        self.a_pass_of(sample_nodes() + [dict(sample_nodes()[0], address="95.181.152.1", sni="")])
        self.assertIn("95.181.152.1", self.read_lines(self.servers_path()))
        self.assertEqual(self.read_lines(self.names_path()), ["differencescope.com", "gridsnap.org"])

    def test_a_node_without_a_fingerprint_adds_no_fingerprint(self):
        self.a_pass_of(
            sample_nodes() + [dict(sample_nodes()[0], address="95.181.152.1", fingerprint="")]
        )
        self.assertIn("95.181.152.1", self.read_lines(self.servers_path()))
        self.assertEqual(self.read_lines(self.fingerprints_path()), ["chrome", "qq"])

    def moments_of_the_list_files(self):
        return (
            self.moment_ns(self.servers_path()),
            self.moment_ns(self.names_path()),
            self.moment_ns(self.fingerprints_path()),
        )

    def test_a_pass_that_adds_nothing_leaves_the_files_untouched(self):
        self.a_pass_of(sample_nodes())
        moments = self.moments_of_the_list_files()
        self.a_pass_of(sample_nodes())
        self.assertEqual(moments, self.moments_of_the_list_files())

    def test_a_pass_that_grows_the_servers_rewrites_only_that_file(self):
        self.a_pass_of(sample_nodes())
        names_moment = self.moment_ns(self.names_path())
        fingerprints_moment = self.moment_ns(self.fingerprints_path())
        self.a_pass_of(sample_nodes() + [dict(sample_nodes()[0], address="95.181.152.1")])
        self.assertIn("95.181.152.1", self.read_lines(self.servers_path()))
        self.assertEqual(names_moment, self.moment_ns(self.names_path()))
        self.assertEqual(fingerprints_moment, self.moment_ns(self.fingerprints_path()))

    def test_a_pass_that_grows_the_names_rewrites_only_that_file(self):
        self.a_pass_of(sample_nodes())
        servers_moment = self.moment_ns(self.servers_path())
        fingerprints_moment = self.moment_ns(self.fingerprints_path())
        self.a_pass_of(sample_nodes() + [dict(sample_nodes()[0], sni="aaa.example")])
        self.assertIn("aaa.example", self.read_lines(self.names_path()))
        self.assertEqual(servers_moment, self.moment_ns(self.servers_path()))
        self.assertEqual(fingerprints_moment, self.moment_ns(self.fingerprints_path()))

    def test_a_pass_that_grows_the_fingerprints_rewrites_only_that_file(self):
        self.a_pass_of(sample_nodes())
        servers_moment = self.moment_ns(self.servers_path())
        names_moment = self.moment_ns(self.names_path())
        self.a_pass_of(sample_nodes() + [dict(sample_nodes()[0], fingerprint="firefox")])
        self.assertEqual(self.read_lines(self.fingerprints_path()), ["chrome", "firefox", "qq"])
        self.assertEqual(servers_moment, self.moment_ns(self.servers_path()))
        self.assertEqual(names_moment, self.moment_ns(self.names_path()))

    def test_the_journal_names_the_files_at_the_birth_and_is_quiet_on_a_rewrite(self):
        self.a_pass_of(sample_nodes())
        kept = self.journal_text()
        self.assertIn(bridge.servers_file_name(self.key), kept)
        self.assertIn(bridge.names_file_name(self.key), kept)
        self.assertIn(bridge.fingerprints_file_name(self.key), kept)
        mentions = kept.count(bridge.servers_file_name(self.key))
        self.a_pass_of(sample_nodes() + [dict(sample_nodes()[0], address="95.181.152.1")])
        self.assertEqual(mentions, self.journal_text().count(bridge.servers_file_name(self.key)))

    def test_older_files_move_aside_under_the_moment_of_their_birth(self):
        for path in (self.servers_path(), self.names_path(), self.fingerprints_path()):
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("an older run\n")
        moments = {
            path: time.strftime(
                settings.ARCHIVE_MOMENT_FORMAT,
                time.localtime(bridge.moment_of_the_birth_of_a_file(path)),
            )
            for path in (self.servers_path(), self.names_path(), self.fingerprints_path())
        }
        self.a_pass_of(sample_nodes())
        for path, moment in moments.items():
            archived = os.path.join(self.directory, f"{moment}_{os.path.basename(path)}")
            self.assertTrue(os.path.exists(archived), archived)
            self.assertEqual(self.read_lines(archived), ["an older run"])
        self.assertEqual(self.read_lines(self.servers_path()), ["13.140.54.5", "64.137.54.2"])

    def test_two_accounts_keep_their_lists_apart(self):
        self.a_pass_of(sample_nodes())
        other = bridge.AccountSnapshot(self.other_key, "device id")
        other.remember_the_unique_servers_names_and_fingerprints(
            [dict(sample_nodes()[0], address="95.181.152.1", sni="aaa.example", fingerprint="firefox")]
        )
        other.keep_the_unique_files_of_the_run()
        self.assertEqual(self.read_lines(self.servers_path()), ["13.140.54.5", "64.137.54.2"])
        self.assertEqual(self.read_lines(self.servers_path(self.other_key)), ["95.181.152.1"])
        self.assertEqual(self.read_lines(self.fingerprints_path(self.other_key)), ["firefox"])


class VendorRefusalCheck(unittest.TestCase):
    """A refused call of the vendor keeps its body in the file of refusals."""

    def setUp(self):
        self.directory = tempfile.mkdtemp(prefix="bridge-refusals-")
        self.key = "the-access-key-of-the-refusal-checks"
        put_a_stand_in(self, settings, "LOGS_DIRECTORY", self.directory)
        self.addCleanup(shutil.rmtree, self.directory, ignore_errors=True)

    def vendor_that_refuses(self, code, body):
        """Answer every call the way the vendor answers a key it will not serve."""

        def refusing_call(request, timeout=None):
            raise urllib.error.HTTPError(
                request.full_url, code, "refused", {}, io.BytesIO(body.encode("utf-8"))
            )

        put_a_stand_in(self, bridge.urllib.request, "urlopen", refusing_call)

    def kept_refusals(self):
        with open(os.path.join(self.directory, bridge.error_file_name(self.key)), encoding="utf-8") as handle:
            return handle.read()

    def test_the_body_of_a_refusal_reaches_the_file_of_refusals(self):
        self.vendor_that_refuses(404, '{"detail": "Invalid access key"}')
        with self.assertRaises(RuntimeError) as refused:
            bridge.vendor_request_with_retries(
                "/connection/list", self.key, "device id", what="the location list"
            )
        refused.exception.__cause__.close()
        kept = self.kept_refusals()
        self.assertIn("the vendor refused with code 404", kept)
        self.assertIn('\t"detail": "Invalid access key"', kept)


class BusyPortCheck(unittest.TestCase):
    """A busy port is taken from another copy of this program, and from nobody else."""

    def setUp(self):
        self.directory = tempfile.mkdtemp(prefix="bridge-busy-port-")
        put_a_stand_in(self, settings, "LOGS_DIRECTORY", self.directory)
        put_a_stand_in(self, settings, "BUSY_PORT_SOFT_WAIT_SECONDS", 0)
        put_a_stand_in(self, settings, "BUSY_PORT_HARD_WAIT_SECONDS", 0)
        put_a_stand_in(self, bridge, "JOURNAL_FILE", None)
        self.addCleanup(shutil.rmtree, self.directory, ignore_errors=True)
        self.addCleanup(self.close_the_journal)
        self.signals = []
        self.tries = []
        self.the_server = object()
        put_a_stand_in(self, bridge, "send_a_signal_to", self.remember_the_signal)
        bridge.start_journal()

    def close_the_journal(self):
        """Close the journal of this check, so the next check opens its own."""
        if bridge.JOURNAL_FILE is not None:
            bridge.JOURNAL_FILE.close()
            bridge.JOURNAL_FILE = None

    def remember_the_signal(self, pid, signal_number):
        """Record one signal instead of sending it."""
        self.signals.append((pid, signal_number))
        return True

    def the_port_is_held_by(self, pid, by_a_copy_of_this_program):
        """Make the world look as if one process holds the port."""
        put_a_stand_in(self, bridge, "pids_holding_the_port", lambda port: [pid])
        put_a_stand_in(
            self, bridge, "is_another_copy_of_this_program", lambda other: by_a_copy_of_this_program
        )

    def listening_answers_a_server_after(self, how_many_tries):
        """A listening call that answers nothing until the given number of tries has passed."""

        def listening(_port):
            self.tries.append(1)
            return self.the_server if len(self.tries) >= how_many_tries else None

        put_a_stand_in(self, bridge, "listen_or_nothing", listening)

    def read_the_journal(self):
        with open(os.path.join(self.directory, settings.JOURNAL_FILE_NAME), encoding="utf-8") as handle:
            return handle.read()

    def test_the_port_is_taken_from_another_copy_of_this_program(self):
        self.the_port_is_held_by(4242, True)
        self.listening_answers_a_server_after(2)
        server = bridge.open_a_listening_server(settings.HTTP_PORT, "HTTP_PORT")
        self.assertIs(server, self.the_server)
        self.assertEqual(self.signals, [(4242, signal.SIGTERM)])
        self.assertIn("asking it to stop", self.read_the_journal())
        self.assertIn("was free after the soft signal", self.read_the_journal())

    def test_a_copy_that_does_not_stop_gets_the_hard_signal(self):
        self.the_port_is_held_by(4242, True)
        self.listening_answers_a_server_after(1000)
        self.assertIsNone(bridge.open_a_listening_server(settings.HTTP_PORT, "HTTP_PORT"))
        self.assertEqual(self.signals, [(4242, signal.SIGTERM), (4242, signal.SIGKILL)])
        self.assertIn("this port is given up", self.read_the_journal())

    def test_a_stranger_holds_the_port_and_is_left_alone(self):
        self.the_port_is_held_by(1, False)
        self.listening_answers_a_server_after(1000)
        self.assertIsNone(bridge.open_a_listening_server(settings.HTTP_PORT, "HTTP_PORT"))
        self.assertEqual(self.signals, [])
        self.assertIn("is held by another program", self.read_the_journal())

    def test_taking_the_port_can_be_switched_off(self):
        put_a_stand_in(self, settings, "TAKE_A_BUSY_PORT_FROM_ANOTHER_COPY", 0)
        self.the_port_is_held_by(4242, True)
        self.listening_answers_a_server_after(1000)
        self.assertIsNone(bridge.open_a_listening_server(settings.HTTP_PORT, "HTTP_PORT"))
        self.assertEqual(self.signals, [])
        self.assertIn("switched off", self.read_the_journal())

    def test_a_free_port_is_opened_without_any_signal(self):
        server = bridge.open_a_listening_server(0, "HTTP_PORT")
        self.assertIsNotNone(server)
        server.server_close()
        self.assertEqual(self.signals, [])

    def test_the_name_of_the_file_decides_who_is_a_copy(self):
        name = bridge.PROGRAM_FILE_NAME
        for arguments, expected in (
            (["python3", name], True),
            (["python3", os.path.join("/opt/sotavpn-bridge", name)], True),
            (["python3", "some-other-program.py"], False),
            (["python3"], False),
            ([], False),
        ):
            with mock.patch.object(bridge, "arguments_of", lambda pid, arguments=arguments: arguments):
                self.assertEqual(bridge.is_another_copy_of_this_program(4242), expected, arguments)

    def test_the_waits_come_from_the_settings(self):
        put_a_stand_in(self, settings, "BUSY_PORT_SOFT_WAIT_SECONDS", 0.2)
        self.the_port_is_held_by(4242, True)
        self.listening_answers_a_server_after(1000)
        self.assertIsNone(bridge.open_a_listening_server(settings.HTTP_PORT, "HTTP_PORT"))
        self.assertGreaterEqual(len(self.tries), 4)


class ReadmeCheck(unittest.TestCase):
    """The readme points at the settings instead of repeating their values."""

    def test_the_readme_leaves_the_log_file_names_to_the_settings(self):
        with open(os.path.join(bridge.PROGRAM_DIRECTORY, "README.md"), encoding="utf-8") as handle:
            readme = handle.read()
        self.assertNotIn(bridge.answer_file_name("<access key>"), readme)
        self.assertNotIn(bridge.error_file_name("<access key>"), readme)


class IgnoredFilesCheck(unittest.TestCase):
    """What the program writes while it runs never enters the repository."""

    def test_the_log_directory_never_enters_the_repository(self):
        with open(os.path.join(bridge.PROGRAM_DIRECTORY, ".gitignore"), encoding="utf-8") as handle:
            rules = [line.strip() for line in handle]
        self.assertIn("logs/", rules)


if __name__ == "__main__":
    unittest.main()
