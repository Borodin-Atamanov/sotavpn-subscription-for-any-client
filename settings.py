"""All values of the sotavpn bridge to freedom live here.

This file holds values only. The program imports it, and importing it is
already execution: every name below exists after the import line, so the
program has nothing else to configure. Every name is explained in place:
what it does, which value is the default, and when to change it.
"""

# The name the program calls itself. It names the journal, the service, the
# command and the program file, and the program prints it in the opening line
# of its journal. The version grows with every change of the code and travels
# in the Profile-Title header of the answers as well.
PROGRAM_NAME = "sotavpn_bridge_to_freedom"
PROGRAM_VERSION = "1.0.17"

# Where the source of the program lives and who wrote it. The program prints
# both in the opening lines of its journal and carries them in the header of
# its own file, so a reader of a log or of a copied file knows what this is
# and where it came from. Change these two lines if you publish your own copy.
PROGRAM_SOURCE_URL = "https://github.com/Borodin-Atamanov/sotavpn-subscription-for-any-client"
PROGRAM_AUTHOR = "Borodin-Atamanov"

# The program tells what it is doing after every step while VERBOSE is 1.
# The lines on the screen are a copy of the journal, so switching them off
# loses nothing: set this to 0 only when the noise becomes a problem.
VERBOSE = 1

# The address the program listens on. 127.0.0.1 means this machine only, and
# that is the safe default: the subscription address carries your access key,
# so anyone who can reach the port can read your whole server list. Use
# 0.0.0.0 to serve a home network, and know that HTTPS is worth its
# certificates only in that case.
LISTEN_ADDRESS = "127.0.0.1"

# The two ports the program opens. Plain HTTP works with every client, even
# with the most stubborn one, so try the plain port first. The secure port
# needs the certificate below and a client that is told to accept it. Both
# ports are opened at once and serve the same answers, and a port that cannot
# be taken does not stop the other. Ports above 1024 work for an ordinary
# user, ports below 1024 only for root. Every switch in this file answers
# with one for on and zero for off: ENABLE_HTTPS opens the secure port.
HTTP_PORT = 25080
HTTPS_PORT = 25443
ENABLE_HTTPS = 1

# The self signed certificate and its private key, counted from this program.
# Both files are in this public repository on purpose: HTTPS then works right
# after the clone, with nothing to create. The price is that the private key
# is public as well, so anybody who can stand between you and this program
# can pretend to be this program, while somebody who merely listens to the
# network still cannot read your traffic. Regenerate both for yourself when
# that matters: the command and the full explanation are in certs/README.md.
CERTIFICATE_FILE = "certs/bridge-self-signed-certificate.pem"
PRIVATE_KEY_FILE = "certs/bridge-self-signed-private-key.pem"

# The vendor API this bridge talks to: the host and the base path of every
# call. Change the host only when the vendor moves to another address.
VENDOR_HOST = "meowconnect.com"
VENDOR_BASE_PATH = "/api/v1/public"

# How the bridge calls the vendor. VENDOR_TIME_OUT_SECONDS is the wait for one
# answer, VENDOR_ATTEMPTS is how many times one failed call is repeated,
# VENDOR_RETRY_PAUSE_SECONDS is the wait between two attempts of the same
# call, and VENDOR_PAUSE_BETWEEN_REQUESTS_SECONDS is the small wait between
# two different calls of one pass. One pass makes a call per location of the
# vendor plus two, so the attempts and the pauses add up: a vendor that is
# down makes a pass slow, and the vendor does not like fast hammering.
VENDOR_TIME_OUT_SECONDS = 120
VENDOR_ATTEMPTS = 5
VENDOR_RETRY_PAUSE_SECONDS = 11
VENDOR_PAUSE_BETWEEN_REQUESTS_SECONDS = 0.1

# The vendor identifies a device by this header. Their own client fills it with
# the sha256 of the machine id of the machine it runs on, and this was checked
# against that client on 2026-09-15:
#   printf '%s' "$(cat /etc/machine-id)" | sha256sum
# The value below is the hash of the machine of the author of this program,
# so every copy of this program introduces itself to the vendor as the same
# device as the vendor client does on that machine. Take your own hash with
# the command above, put it either here or into the default_hardware_id
# parameter of the subscription address, and your device is your own. An
# empty value makes the bridge invent a random stable id per access key,
# which the API also accepts.
# The identifier is not a secret: a hash cannot be turned back into the machine
# id. It does name the machine it came from, so do not publish your own hash
# unless you mean to.
DEFAULT_HARDWARE_ID = "bc595c0af2e559eb9b19aec5aaf597dd6546b6945df791990de5f3d098a4289e"

# The user agent the vendor client sends. Kept as it is, because the vendor
# sees the same kind of request as from their own application.
VENDOR_USER_AGENT = "Sota Connect (v1.7.7/windows)"

# How long a collected list counts as fresh, in seconds. The vendor hands out
# a working server address together with its camouflage name, and that pair
# goes stale within minutes, so a client that asks again after this many
# seconds gets a freshly collected list. A small value keeps the list young
# and makes each refresh slower, a large one does the opposite.
SNAPSHOT_FRESH_SECONDS = 15

# Every node name starts with this word, then the country and the gateway
# name follow. Names stay the same between refreshes, so a client does not
# grow duplicates in its list. Change it to mark the list as your own.
NODE_NAME_PREFIX = "Sota"

# The two group names the answers offer to a client: the automatic one, which
# the client fills by testing every node itself, and the manual one, which is
# what the user picks a node from. They name something the bridge invents and
# not a server of the vendor, so they may say anything.
AUTOMATIC_GROUP_NAME = "Sota automatic"
MANUAL_GROUP_NAME = "Sota manual"

# What clients show and how often they come back for a new list: the title of
# the profile, the interval in hours (most clients count it in hours) and the
# page that opens when the user taps the profile.
PROFILE_TITLE = "Sota"
PROFILE_UPDATE_INTERVAL_HOURS = 1
PROFILE_HOME_PAGE = "https://sotavpn.org"

# How the automatic group checks whether a node is alive: the address it
# fetches, how often it repeats that check, and how many milliseconds faster
# another node must be before the client switches to it. A small tolerance
# keeps the client from switching on every flicker of latency. The client
# does this test itself, so the bridge never pings anything. The address is
# the tiny answer of Cloudflare that carries no body and is never cached, so
# it measures the node and nothing else. The interval is one number: the
# Clash answer wants seconds and the sing-box answer wants a duration, and
# the program writes the duration out of this same number.
AUTOMATIC_TEST_URL = "http://cp.cloudflare.com/generate_204"
AUTOMATIC_TEST_INTERVAL_SECONDS = 300
AUTOMATIC_TEST_TOLERANCE_MILLISECONDS = 50

# The local entry points inside the complete configurations the bridge can
# hand out. sing-box gets a tunnel interface with this address and Xray gets
# a socks port; a program of that machine then sends its traffic there. These
# are addresses of the machine that runs the configuration and not of the
# bridge, so change them only when something else already uses them.
SING_BOX_LOCAL_TUN_ADDRESS = "10.0.42.1/30"
XRAY_LOCAL_SOCKS_PORT = 10809

# The converter that turns the raw node list into the dialects this bridge
# does not write by itself: Surge, Loon, Quantumult, Quantumult X and
# Surfboard. The root page shows a ready to copy address. The answers this
# bridge does write are listed in the program itself, each with its own
# description, so there is one list of them and not two that must agree.
SUBCONVERTER_SUBSCRIBE_URL = "http://127.0.0.1:25500/sub"

# Where the program keeps the raw answers of the vendor, the unique lists of
# a run and its own journal.
# The directory sits next to the program, and in a service installation that
# is the program directory, so the logs travel with the program and survive
# an update. It is listed in .gitignore, because a raw vendor answer carries
# the addresses, the keys and the camouflage names of the account.
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
# answers of the same pass. Kept apart from the answers, because a refusal is
# an answer in words and not in JSON, and mixing the two would ruin the
# stream of documents.
ERROR_FILE_SUFFIX = "-errors.log"

# The unique servers, camouflage names and fingerprints an account has seen
# so far in this run, one value per line: one file keeps the addresses, one
# keeps the names, one keeps the fingerprints, and all three are named after
# the access key. The three are born at the moment the first request of that
# account is answered; the files of a previous run move aside right then,
# under the moment of their own birth. A later pass rewrites a file only
# when the number of its values grew, and a file that did not change is not
# touched at all.
NAMES_FILE_SUFFIX = "-names.log"
SERVERS_FILE_SUFFIX = "-servers.log"
FINGERPRINTS_FILE_SUFFIX = "-fingerprints.log"

# What one answer carries beyond the vendor list. With the first switch on,
# every server, every camouflage name and every fingerprint this run has seen
# so far, which are the three unique lists above, are multiplied, and that
# product is appended after the vendor nodes. A node that repeats a server,
# name and fingerprint already in the list is dropped right then, the first
# one staying, so a vendor node wins over the multiplied copy of itself.
# The switch is off at zero and on at one.
APPEND_MULTIPLY_SERVER_WITH_EVERY_NAME_AND_FINGERPRINT = 0

# The second switch mixes the node list of every answer right before sending
# it, the vendor nodes and the multiplied ones together, so the first line is
# a different node on every request. Off at zero, on at one; without it the
# order never changes: the vendor nodes first, then the multiplied ones by
# server, name and fingerprint.
RANDOMIZE_ANSWER = 0

# How many nodes one answer carries at most, counted after the append and the
# mixing. The vendor sends about two hundred nodes, so the value starts to
# matter only when the append above multiplies them into thousands. Zero
# means no limit at all.
ANSWER_NODES_LIMIT = 777

# What one request may change for itself. The name in the address is the
# name of the setting here, in any case, and the value has the kind the
# setting has now: a whole number stays a whole number, text stays text. A
# name outside this list is left alone. Nothing here changes settings.py:
# a value from a request travels as the argument of the two functions that
# read these settings, so it belongs to that one request alone.
REQUEST_OVERRIDABLE_SETTINGS = [
    "APPEND_MULTIPLY_SERVER_WITH_EVERY_NAME_AND_FINGERPRINT",
    "RANDOMIZE_ANSWER",
    "ANSWER_NODES_LIMIT",
    "SNAPSHOT_FRESH_SECONDS",
    "DEFAULT_HARDWARE_ID",
]

# The journal of the current run: what the program did, in plain words, one
# line per step. The next start moves the journal of the previous run aside
# inside the same directory, the moment in front of its name, so one file
# always belongs to one run and the failure of a past run is still readable.
JOURNAL_FILE_NAME = "log.log"

# The moment an archived log carries in front of its own name: the moment
# that file itself was created, never the moment of its last write, because
# the two list files of one run are born together and an archive keeps the
# moment they were born with. Linux does not hand the moment of birth to
# Python, so the external tool stat is asked; a file system that does not
# keep the moment of birth makes stat answer 0, and then the moment of the
# last write is used instead.
ARCHIVE_MOMENT_FORMAT = "%Y-%m-%d-%H-%M-%S"

# The short name of an installation: it names the program directory, the
# settings directory, the service file and the command. It is written once
# here, so the two sets below cannot drift apart from each other.
INSTALL_NAME = "sotavpn-bridge"

# Where the installer puts the program and what it asks systemd to do. The
# set is chosen by the account that runs the installer: root installs the
# system set, an ordinary user installs the user set. Every path of an
# installation comes from here, so the installer holds none of its own. A
# leading ~ means the home directory of that account, and %t is the runtime
# directory of the user (in the service file: the temporary directory).
# The settings directory is not part of this set on purpose: the program
# imports settings by its name and Python looks for it in the directory of
# the program, so the settings lie next to the program, and the logs lie
# next to it as well, exactly as LOGS_DIRECTORY above says.
SYSTEM_INSTALL = {
    "code_directory": f"/opt/{INSTALL_NAME}",
    "unit_file": f"/etc/systemd/system/{INSTALL_NAME}.service",
    "command_link": f"/usr/local/bin/{INSTALL_NAME}",
    "wanted_by": "multi-user.target",
    "temporary_directory": "/tmp",
}

USER_INSTALL = {
    "code_directory": f"~/.local/share/{INSTALL_NAME}",
    "unit_file": f"~/.config/systemd/user/{INSTALL_NAME}.service",
    "command_link": f"~/.local/bin/{INSTALL_NAME}",
    "wanted_by": "default.target",
    "temporary_directory": "%t",
}

# How long systemd waits before it starts the program again after a failure.
# The only failure the program knows is a port somebody else holds, and a copy
# of this program that holds it is asked to step aside and then killed, so the
# restart of the service is the moment the fight is decided: the service keeps
# coming back after every such pause and the copy that was started by hand
# goes after one round.
SERVICE_RESTART_PAUSE_SECONDS = 42

# What to do when a port is already held. The program asks the holder to stop
# and takes the port, but only when the holder is another copy of this very
# program: a process of any other program is named in the journal and left
# alone. The first wait follows the soft signal, the second one follows the
# hard signal, and both are counted in seconds. Finding the holder needs the
# program fuser, which comes with the psmisc package on Linux.
TAKE_A_BUSY_PORT_FROM_ANOTHER_COPY = 1
BUSY_PORT_SOFT_WAIT_SECONDS = 5
BUSY_PORT_HARD_WAIT_SECONDS = 7

# How long the installer waits for the program it has just started to say in
# its journal that its ports are open. A first start also collects the server
# list of every account it is asked about, so this wait outlasts one pass over
# the locations of the vendor.
SECONDS_TO_WAIT_FOR_THE_PROGRAM = 15
