"""All values of the sotavpn bridge to freedom live here.

This file holds values only. The program imports it, and importing it is
already execution: every name below exists after the import line, so the
program has nothing else to configure.
"""

# Name and version the program shows in its journal and in HTTP answers.
PROGRAM_NAME = "sotavpn_bridge_to_freedom"
PROGRAM_VERSION = "1.0.9"

# Where the source of the program lives and who wrote it. The program prints
# both in the opening lines of its journal and carries them in the header of
# its own file, so a reader of a log or of a copied file knows what this is
# and where it came from. Change these two lines if you publish your own copy.
PROGRAM_SOURCE_URL = "https://github.com/Borodin-Atamanov/sotavpn-subscription-for-any-client"
PROGRAM_AUTHOR = "Borodin-Atamanov <argentidin@gmail.com>"

# The program tells what it is doing after every step while VERBOSE is 1.
# Set it to 0 only when the journal noise becomes a problem.
VERBOSE = 1

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
VENDOR_TIME_OUT_SECONDS = 120
VENDOR_ATTEMPTS = 5
VENDOR_RETRY_PAUSE_SECONDS = 11
VENDOR_PAUSE_BETWEEN_REQUESTS_SECONDS = 0.1

# The vendor identifies a device by this header. Their own client fills it with
# the sha256 of the machine id of the machine it runs on, and this was checked
# against that client on 2026-09-15:
#   printf '%s' "$(cat /etc/machine-id)" | sha256sum
# The value below is that hash for one machine, so a copy of this program
# introduces itself to the vendor as the same device as the vendor client does
# on that machine. Every copy sends this same value, because a public
# repository cannot carry the hash of the machine of each reader. Take your own
# hash with the command above, put it either here or into ?hwid= of the
# subscription address, and your device is your own. An empty value makes the
# bridge invent a random stable id per access key, which the API also accepts.
DEFAULT_HARDWARE_ID = "bc595c0af2e559eb9b19aec5aaf597dd6546b6945df791990de5f3d098a4289e"

# The user agent the vendor client sends. Kept as it is, because the vendor
# sees the same kind of request as from their own application.
VENDOR_USER_AGENT = "Sota Connect (v1.7.7/windows)"

# How long a collected answer counts as fresh. After this many seconds the
# next client request collects a new one. The vendor hands out a working
# server address together with its camouflage name, and that pair goes stale
# within minutes, so keep this small.
SNAPSHOT_FRESH_SECONDS = 15

# Every node name starts with this word, then the country and the gateway
# name follow. Names stay the same between refreshes, so clients do not grow
# duplicates in their lists.
NODE_NAME_PREFIX = "Sota"

# What clients see as the profile title, how often they should come back
# for a new list, and the page they open when the user taps the profile.
# Most clients count the interval in hours.
PROFILE_TITLE = "Sota"
PROFILE_UPDATE_INTERVAL_HOURS = 1
PROFILE_HOME_PAGE = "https://sotavpn.org"

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

# Where the program keeps the raw answers of the vendor and its own journal.
# The directory sits next to the program. It is listed in .gitignore, because
# a raw vendor answer carries the addresses, the keys and the camouflage
# names of the account.
LOGS_DIRECTORY = "logs"

# The answers of the vendor during the last pass, in a file named after the
# access key of the account. Every answer is kept as a JSON document of its
# own, printed with tabs so a reader can follow the shape, and one empty line
# separates two documents. A pass asks the vendor thirty seven times: once for
# the location list, once per location for its configuration, and once for the
# profile, so one pass cannot live in a single JSON document. The next pass
# moves that file aside inside the same directory before it writes anything,
# the moment in front of its name, so one file always holds one pass of one
# account, two accounts never mix, and the directory stays flat.
ANSWER_FILE_SUFFIX = ".json"

# The bodies the vendor sends together with a refusal: a wrong access key, a
# location it no longer serves, a call it throttled. They go into a file of
# their own, named after the access key, and move aside together with the
# answers of the same pass. Kept apart from the answers,
# because a refusal is an answer in words, not in JSON, and mixing the two
# would ruin the stream of documents.
ERROR_FILE_SUFFIX = "-errors.log"

# The journal of the current run. The next start moves the journal of the
# previous run aside inside the same directory first, the moment in front of
# its name, so one file always belongs to one run.
JOURNAL_FILE_NAME = "log.log"

# The moment an archived log carries in front of its own name: the moment
# that file itself was created, in the same shape Pyntara uses for its
# timestamps.
ARCHIVE_MOMENT_FORMAT = "%Y-%m-%d-%H-%M-%S"
