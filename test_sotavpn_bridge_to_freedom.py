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
import ssl
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request

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
        self.assertIn(f"url: {settings.CLASH_TEST_URL}", text)
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

    def test_answer_formats_are_all_reachable(self):
        for suffix, _ in settings.ANSWER_FORMATS:
            self.assertIn(suffix, bridge.ANSWERS)


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
        self.assertEqual(len(addresses), len(settings.ANSWER_FORMATS))
        for line in addresses:
            self.assertTrue(line.startswith(f"http://127.0.0.1:{port}/sub/<access key>/"), line)

    def test_a_secure_visitor_sees_secure_addresses(self):
        page, port = self.page_of_a_visitor_that_came_through(secure=True)
        addresses = self.address_lines_of(page)
        self.assertEqual(len(addresses), len(settings.ANSWER_FORMATS))
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

    def test_old_nodes_survive_a_failed_collection(self):
        def broken_collection(access_key, hardware_id):
            raise RuntimeError("the vendor is unreachable")

        bridge.collect_nodes, original = broken_collection, bridge.collect_nodes
        try:
            nodes, age, complaint = self.snapshot.nodes_for_request()
        finally:
            bridge.collect_nodes = original
        self.assertEqual(len(nodes), 2)
        self.assertIn("unreachable", complaint)
        self.assertIsNotNone(age)

    def test_a_fresh_list_is_given_back_without_a_new_collection(self):
        self.snapshot.collected_at = bridge.time.monotonic()

        def must_not_be_called(access_key, hardware_id):
            self.fail("a fresh list must not be collected again")

        bridge.collect_nodes, original = must_not_be_called, bridge.collect_nodes
        try:
            nodes, age, _ = self.snapshot.nodes_for_request()
        finally:
            bridge.collect_nodes = original
        self.assertEqual(len(nodes), 2)
        self.assertLess(age, settings.SNAPSHOT_FRESH_SECONDS)

    def test_an_unexpected_failure_also_keeps_the_old_nodes(self):
        def broken_collection(access_key, hardware_id):
            raise ValueError("a shape the program did not expect")

        bridge.collect_nodes, original = broken_collection, bridge.collect_nodes
        try:
            nodes, _age, complaint = self.snapshot.nodes_for_request()
        finally:
            bridge.collect_nodes = original
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
        self.pause = settings.VENDOR_PAUSE_BETWEEN_REQUESTS_SECONDS
        settings.VENDOR_PAUSE_BETWEEN_REQUESTS_SECONDS = 0
        self.original = bridge.vendor_request_with_retries

        def vendor(path, access_key, hardware_id, query="", what=""):
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

        bridge.vendor_request_with_retries = vendor

    def tearDown(self):
        bridge.vendor_request_with_retries = self.original
        settings.VENDOR_PAUSE_BETWEEN_REQUESTS_SECONDS = self.pause

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
    def test_ports_are_usable_by_a_user(self):
        for port in (settings.HTTP_PORT, settings.HTTPS_PORT):
            self.assertGreater(port, 1024)
            self.assertLess(port, 32768)

    def test_times_are_reasonable(self):
        self.assertGreater(settings.SNAPSHOT_FRESH_SECONDS, 0)
        self.assertGreater(settings.VENDOR_TIME_OUT_SECONDS, 0)


class LogArchiveCheck(unittest.TestCase):
    """The raw vendor answers and the journal, in a directory of their own."""

    def setUp(self):
        self.directory = tempfile.mkdtemp(prefix="bridge-logs-")
        self.key = "the-access-key-of-the-log-checks"
        self.other_key = "the-access-key-of-the-other-account"
        self.kept_directory = settings.LOGS_DIRECTORY
        self.kept_journal = bridge.JOURNAL_FILE
        settings.LOGS_DIRECTORY = self.directory
        bridge.JOURNAL_FILE = None

    def tearDown(self):
        settings.LOGS_DIRECTORY = self.kept_directory
        bridge.JOURNAL_FILE = self.kept_journal
        shutil.rmtree(self.directory, ignore_errors=True)

    def answer_path(self, key=None):
        return os.path.join(self.directory, bridge.answer_file_name(key or self.key))

    def error_path(self, key=None):
        return os.path.join(self.directory, bridge.error_file_name(key or self.key))

    def journal_path(self):
        return os.path.join(self.directory, settings.JOURNAL_FILE_NAME)

    def moment_of(self, path):
        return time.strftime(settings.ARCHIVE_MOMENT_FORMAT, time.localtime(os.path.getmtime(path)))

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

    def test_the_next_pass_moves_the_previous_answers_into_a_dated_directory(self):
        bridge.start_a_fresh_log_pass(self.key)
        bridge.keep_vendor_answer(self.key, '{"first": true}')
        moment = self.moment_of(self.answer_path())
        bridge.start_a_fresh_log_pass(self.key)
        bridge.keep_vendor_answer(self.key, '{"second": true}')
        self.assertEqual(json.loads(self.read(self.answer_path())), {"second": True})
        archived = os.path.join(self.directory, moment, bridge.answer_file_name(self.key))
        self.assertEqual(json.loads(self.read(archived)), {"first": True})

    def test_a_pass_that_arrives_first_finds_nothing_to_move(self):
        bridge.start_a_fresh_log_pass(self.key)
        self.assertEqual(os.listdir(self.directory), [])

    def test_two_files_created_in_the_same_second_get_two_directories(self):
        os.makedirs(self.directory, exist_ok=True)
        first = os.path.join(self.directory, "first")
        second = os.path.join(self.directory, "second")
        for path in (first, second):
            open(path, "w", encoding="utf-8").close()
        same = time.time()
        os.utime(first, (same, same))
        os.utime(second, (same, same))
        moved_first = bridge.move_into_a_dated_directory(first)
        moved_second = bridge.move_into_a_dated_directory(second)
        self.assertNotEqual(os.path.dirname(moved_first), os.path.dirname(moved_second))
        self.assertTrue(os.path.exists(moved_first))
        self.assertTrue(os.path.exists(moved_second))

    def test_a_file_that_is_not_there_is_not_moved(self):
        self.assertEqual(bridge.move_into_a_dated_directory(self.answer_path()), "")

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
        self.assertIn("yesterday", self.read(os.path.join(self.directory, moment, settings.JOURNAL_FILE_NAME)))

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
        archived = os.path.join(self.directory, moment, bridge.error_file_name(self.key))
        self.assertIn("the vendor broke", self.read(archived))


class VendorRefusalCheck(unittest.TestCase):
    """A refused call of the vendor keeps its body in the file of refusals."""

    def setUp(self):
        self.directory = tempfile.mkdtemp(prefix="bridge-refusals-")
        self.key = "the-access-key-of-the-refusal-checks"
        self.kept_directory = settings.LOGS_DIRECTORY
        self.kept_urlopen = bridge.urllib.request.urlopen
        settings.LOGS_DIRECTORY = self.directory

    def tearDown(self):
        settings.LOGS_DIRECTORY = self.kept_directory
        bridge.urllib.request.urlopen = self.kept_urlopen
        shutil.rmtree(self.directory, ignore_errors=True)

    def vendor_that_refuses(self, code, body):
        """Answer every call the way the vendor answers a key it will not serve."""

        def refusing_call(request, timeout=None):
            raise urllib.error.HTTPError(
                request.full_url, code, "refused", {}, io.BytesIO(body.encode("utf-8"))
            )

        bridge.urllib.request.urlopen = refusing_call

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


class IgnoreRuleCheck(unittest.TestCase):
    def test_the_log_directory_never_enters_the_repository(self):
        with open(os.path.join(bridge.PROGRAM_DIRECTORY, ".gitignore"), encoding="utf-8") as handle:
            rules = [line.strip() for line in handle]
        self.assertIn("logs/", rules)
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

    def test_the_certificate_files_are_in_the_repository(self):
        for path in (settings.CERTIFICATE_FILE, settings.PRIVATE_KEY_FILE):
            self.assertTrue(os.path.isfile(bridge.path_next_to_the_program(path)), f"{path} is missing")


if __name__ == "__main__":
    unittest.main()
