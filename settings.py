"""All values of the sotavpn bridge to freedom live here.

This file holds values only. The program imports it, and importing it is
already execution: every name below exists after the import line, so the
program has nothing else to configure.
"""

# Name and version the program shows in its journal and in HTTP answers.
PROGRAM_NAME = "sotavpn_bridge_to_freedom"
PROGRAM_VERSION = "1.0.0"

# The program tells what it is doing after every step. Set it to False only
# when the journal noise becomes a problem.
SPEAK_EVERY_STEP = True

# Address the program listens on. 127.0.0.1 means this machine only, which
# is the safe default: the subscription URL contains your access key, so
# anyone who can reach the port can read it. Use 0.0.0.0 to serve a home
# network, and know that HTTPS becomes meaningful only in that case.
LISTEN_ADDRESS = "127.0.0.1"

# Plain HTTP port. Works with every client, even with the most stubborn one.
HTTP_PORT = 25080

# HTTPS port. The certificate in the certs directory is self signed, so the
# client must be told to accept an untrusted certificate. Every client has
# such a switch, and the README explains where it is.
HTTPS_PORT = 25443
ENABLE_HTTPS = True

# The self signed certificate and its private key. Both files are public,
# they live in this repository, so anyone can pretend to be this bridge.
# Regenerate them for yourself, the command is in the README.
CERTIFICATE_FILE = "certs/bridge-self-signed-certificate.pem"
PRIVATE_KEY_FILE = "certs/bridge-self-signed-private-key.pem"

# The vendor API this bridge talks to.
VENDOR_HOST = "meowconnect.com"
VENDOR_BASE_PATH = "/api/v1/public"

# How long to wait for one vendor answer, how many times to retry a failed
# call, how long to wait between retries, and how long to wait between two
# calls in the same pass. The vendor does not like fast hammering.
VENDOR_TIME_OUT_SECONDS = 20
VENDOR_ATTEMPTS = 3
VENDOR_RETRY_PAUSE_SECONDS = 3.0
VENDOR_PAUSE_BETWEEN_REQUESTS_SECONDS = 0.2

# The vendor identifies a device by this header. Their own client sends its
# machine id here. Leave it empty and the bridge invents a random stable id
# per access key, which is enough for the API to answer.
DEFAULT_HARDWARE_ID = ""

# The user agent the vendor client sends. Kept as it is, because the vendor
# sees the same kind of request as from their own application.
VENDOR_USER_AGENT = "Sota Connect (v1.7.7/windows)"

# How long a collected answer counts as fresh. After this many seconds the
# next client request collects a new one. The vendor hands out a working
# server address together with its camouflage name, and that pair goes stale
# within minutes, so keep this small.
SNAPSHOT_FRESH_SECONDS = 120

# Every node name starts with this word, then the country and the gateway
# name follow. Names stay the same between refreshes, so clients do not grow
# duplicates in their lists.
NODE_NAME_PREFIX = "Sota"

# What clients see as the profile title, and how often they should come back
# for a new list. Most clients count this value in hours.
PROFILE_TITLE = "Sota"
PROFILE_UPDATE_INTERVAL_HOURS = 1

# The address the automatic test group in the Clash and sing-box answers
# uses to check whether a node is alive. The client does this test itself,
# so the bridge never has to ping anything.
CLASH_TEST_URL = "http://cp.cloudflare.com/generate_204"
CLASH_TEST_INTERVAL_SECONDS = 300
CLASH_TEST_TOLERANCE_MILLISECONDS = 50
SING_BOX_TEST_URL = "http://cp.cloudflare.com/generate_204"
SING_BOX_TEST_INTERVAL = "5m"
SING_BOX_TEST_TOLERANCE = 50

# Local ports and addresses used inside the full configurations the bridge
# can hand out for sing-box and for Xray.
SING_BOX_LOCAL_TUN_ADDRESS = "10.0.42.1/30"
XRAY_LOCAL_SOCKS_PORT = 10809

# The converter that turns the raw node list into the dialects this bridge
# does not write by itself: Surge, Loon, Quantumult, Quantumult X and
# Surfboard. The root page shows a ready to copy address.
SUBCONVERTER_SUBSCRIBE_URL = "http://127.0.0.1:25500/sub"

# Every answer the bridge can produce. The suffix goes after the access key
# in the address, the description goes to the root page.
ANSWER_FORMATS = (
    ("base64", "subscription in base64, the default for most clients"),
    ("raw", "the same list as open vless links"),
    ("clash", "YAML for Clash, Mihomo and Stash with an automatic test group"),
    ("singbox", "JSON outbounds for sing-box and Hiddify with a test group"),
    ("singbox-full", "complete sing-box configuration with a tun inbound"),
    ("xray", "JSON outbounds for Xray and for the 3x-ui panel"),
    ("xray-full", "complete Xray configuration with a local socks inbound"),
    ("html", "a page for a human being, with every node and its link"),
    ("csv", "a table for manual entry: address, port, sni, key, short id"),
)
