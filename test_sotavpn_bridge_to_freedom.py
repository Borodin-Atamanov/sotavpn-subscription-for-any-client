"""Checks for the sotavpn bridge to freedom.

Run them with:
    python3 -m unittest test_sotavpn_bridge_to_freedom

The checks cover the answers the program builds and the behaviour when the
vendor stops answering. They do not touch the network and they do not start
the servers, so they are safe to run anywhere.
"""

import base64
import json
import os
import time
import unittest

import settings
import sotavpn_bridge_to_freedom as bridge

# While the checks run the program stays quiet, and the runner prints no
# decorative line of repeated symbols: plain result, plain words.
settings.VERBOSE = 0
unittest.TextTestResult.separator1 = ""
unittest.TextTestResult.separator2 = ""


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


class SettingsCheck(unittest.TestCase):
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

    def test_the_vendor_and_the_name_prefix_are_set(self):
        self.assertTrue(settings.VENDOR_HOST)
        self.assertTrue(settings.VENDOR_BASE_PATH.startswith("/"))
        self.assertTrue(settings.NODE_NAME_PREFIX)

    def test_the_certificate_files_are_in_the_repository(self):
        for path in (settings.CERTIFICATE_FILE, settings.PRIVATE_KEY_FILE):
            self.assertTrue(os.path.isfile(bridge.path_next_to_the_program(path)), f"{path} is missing")


if __name__ == "__main__":
    unittest.main()
