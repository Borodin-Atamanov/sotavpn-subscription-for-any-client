# Sota subscription for any client

This is a small program that turns your paid Sota Connect account into an
ordinary subscription address. Every VPN client understands such an address:
v2rayN, NekoBox, NekoRay, Hiddify, Karing, Streisand, Clash, Mihomo, Stash,
sing-box, Xray and the 3x-ui panel.

You do not need the vendor application after this. You keep paying for the
service and you use it with the client you like.

The program is one Python file with no dependencies at all. It asks the
vendor API for the server list of your account and hands that list out. It
does not bring up a tunnel, it does not touch your routes or your DNS, and it
does not check whether a server is alive, because your client does that
better and for free.

## What you need

1. Python 3.8 or newer. Nothing else, no packages to install.
2. Your access key. It looks like `05a6c68e-8443-45fa-9f22-36fbcd2a9927` and
   lives in your Sota account page or in the Sota Telegram bot.

## Quick start

```bash
git clone https://github.com/Borodin-Atamanov/sotavpn-subscription-for-any-client
cd sotavpn-subscription-for-any-client
python3 sotavpn_bridge_to_freedom.py
```

The program tells you what it is doing and then waits. The first line of the
journal says which ports are open.

Now put this address into your client, replacing the access key with yours:

```
http://127.0.0.1:25080/sub/your-access-key
```

The first request takes about fifteen seconds, because the program walks all
locations of the service. Later requests are answered at once.

If you want to know whether it works before touching a client, open the root
page in a browser:

```
http://127.0.0.1:25080/
```

It lists every answer this program can give, with ready to use addresses.

To stop the program, press Control and C in the same terminal.

## Every answer this program gives

Add a suffix after the access key:

```
/sub/<access key>              the list in base64, this is the default
/sub/<access key>/raw          the same list as open vless links
/sub/<access key>/clash        YAML for Clash, Mihomo and Stash
/sub/<access key>/singbox      JSON outbounds for sing-box and Hiddify
/sub/<access key>/singbox-full a complete sing-box configuration with tun
/sub/<access key>/xray         JSON outbounds for Xray and the 3x-ui panel
/sub/<access key>/xray-full    a complete Xray configuration with local socks
/sub/<access key>/html         a page for a human being
/sub/<access key>/csv          a table for manual entry
```

When you give no suffix, the program looks at the name your client calls
itself. A Clash family client gets YAML, a sing-box family client gets JSON,
and everything else gets base64. This is the same trick the 3x-ui panel uses.

## How to put it into your client

v2rayN and v2rayNG: Subscription, Add subscription, paste the address.

NekoBox and NekoRay: Preferences, Subscription, Add, paste the address.

Hiddify: Add profile, Add from URL, paste the address.

Clash Verge, Mihomo Party, ClashX: Profiles, Add profile from URL, paste the
address.

sing-box and Xray by hand: take `/sub/<access key>/singbox-full` or
`/sub/<access key>/xray-full` and save the answer as a configuration file.

3x-ui panel: Xray, outbound subscriptions, Create an outbound subscription,
paste the address, enable private addresses, because the address points to
your own machine.

## About the live servers

The vendor hands out a server address together with its camouflage name, and
that pair goes stale within minutes. Two things follow.

The program collects a fresh list on request, so every client refresh brings
a fresh set. The list older than the value SNAPSHOT_FRESH_SECONDS in
settings.py is collected again.

The answers for Clash and sing-box carry an automatic test group, so the
client itself throws away the servers that stopped answering. That is why the
program never pings anything by itself. Use those two answers, or paste the
node list into a client group of your own, and a dead server will not bother
you.

## The logs directory

The program keeps three files next to itself, in the logs directory.

logs/<access key>.json holds the answers the vendor gave during the last
pass, as readable JSON printed with tabs, and an empty line separates two
answers. One account keeps one file, so two accounts never mix.

logs/<access key>-errors.log holds the bodies the vendor sent with a refusal,
with the moment and the code of the refusal in front of each body. A refusal
is an answer in words rather than in JSON, so it stays apart from the answers
of the same pass and never breaks the stream of documents. A pass that goes
well writes no such file at all.

When a new pass collects a fresh list, the previous files move aside inside
the same directory: the moment the file itself was created goes in front of
its name, in the shape 2026-09-23-15-19-45, so the history of one account
reads in order and nothing is ever overwritten. The journal works the same
way: logs/log.log holds the run that is working now, and the next start moves
the journal of the previous run aside first.

The directory stays flat: one file per account and per pass, never a
subdirectory, so a listing shows the whole history at once. Two files of the
same second get a counted name, for example 2026-09-23-15-19-45-2. The
archive grows with every refresh. Look at what it holds and take away what
you do not need.

The logs directory is listed in .gitignore, and it belongs there: a raw
vendor answer carries the addresses, the keys and the camouflage names of
your account, so the directory is as private as your access key.

## HTTPS and the certificate

The program serves plain HTTP on port 25080 and HTTPS on port 25443 at the
same time. The root page of each port tells the addresses with that very
scheme, so a visitor of the secure port is never sent to the plain one.

The certificate in the certs directory is self signed, and its private key is
in this public repository. That means two things. Your traffic cannot be read
by somebody who merely listens to the network, which is the point. But
anybody who can stand between you and this program can pretend to be this
program, because the key is public. That is why the text below matters.

Regenerate the certificate for yourself, it takes one command:

```bash
openssl req -x509 -newkey rsa:2048 -nodes -sha256 -days 3650 \
  -keyout certs/bridge-self-signed-private-key.pem \
  -out certs/bridge-self-signed-certificate.pem \
  -subj "/CN=sotavpn-bridge-local" \
  -addext "subjectAltName=DNS:localhost,IP:127.0.0.1"
```

Because the certificate is self signed, the client must be told to accept it.
Most clients have such a switch: in v2rayN it is the option to allow an
insecure connection, in NekoBox it is in the settings, in Hiddify it is a
checkbox when the address is added. A client without such a switch simply
uses the plain port 25080.

If you want a certificate that clients trust without any switch, put a real
domain in front and let Caddy or nginx get a Let's Encrypt certificate. The
program does not do TLS of that kind on purpose, that is a job for a web
server.

Turning HTTPS off is one line in settings.py.

## Surge, Loon, Quantumult and Surfboard

These families have their own syntax, and this program does not write it.
The converter subconverter does, and it takes the raw list of this program as
its source:

```
http://127.0.0.1:25500/sub?target=surge&url=<address of this bridge, URL encoded>
```

The root page of the bridge shows a ready to copy line like this.

## Where the values live

Every value is in settings.py next to the program: the ports, the vendor
address, the timeouts, the freshness of the list, the name prefix of the
nodes, the test addresses of the automatic groups. The program imports that
file, and the import itself is execution, so there is nothing else to
configure. There are no environment variables and no command line options.

Nothing secret belongs in settings.py. Your access key travels in the address
only, so the file can be published as it is.

## Which device the vendor sees

The vendor API wants a device identifier in the X-HwID header. The vendor
application fills that header with the sha256 of the machine id of the
machine it runs on, so the same hash belongs to the same device:

```bash
printf '%s' "$(cat /etc/machine-id)" | sha256sum
```

settings.py carries one such hash, taken from the machine where this program
was written and checked against the vendor application there. Every copy of
this program therefore introduces itself to the vendor as that one device,
because a public repository cannot carry a personal hash of each reader.

Two ways to be a device of your own. Take your hash with the command above
and put it into the address of the subscription, which does not touch any
file:

```
http://127.0.0.1:25080/sub/your-access-key?hwid=your-own-hash
```

Or put it into DEFAULT_HARDWARE_ID in settings.py and every request uses it.
An empty DEFAULT_HARDWARE_ID makes the program invent a random identifier per
access key, which the vendor API also accepts.

The identifier is not a secret: a hash cannot be turned back into the machine
id. It does identify the machine it came from, so do not publish your own
hash unless you mean to.

## Autostart

The program is a plain command, so any autostart method you already use will
do. One line in a systemd user unit, a launcher in the desktop autostart
directory, a scheduled task in Windows, or a line in a container command, all
of them work the same way: run `python3 sotavpn_bridge_to_freedom.py`.

## If something does not work

The journal says what happened, in plain words. Common cases:

The vendor refused the request: the access key is wrong or the subscription
ended. Check the key in your account page.

The vendor did not answer: the machine has no way to reach the vendor, or the
vendor is down. The bridge keeps serving the previous list, so your client
keeps working, and the journal says how old that list is.

The plain port or the HTTPS port is not free: another program on this machine
already holds it. Change HTTP_PORT or HTTPS_PORT in settings.py. On Windows,
Hyper-V and WSL sometimes reserve a range of high ports in advance, and then
another number helps.

Nothing helps with a client that refuses a self signed certificate: use the
plain port, or put a web server with a real certificate in front.

## Checks

```bash
python3 -m unittest test_sotavpn_bridge_to_freedom
```

The checks cover the answer formats, the automatic test groups, the choice of
the answer by the client name, the device identifier, the collection of the
node list, and the behaviour when the vendor stops answering.
