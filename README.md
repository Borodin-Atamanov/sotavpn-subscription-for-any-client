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
git clone --depth 1 https://github.com/Borodin-Atamanov/sotavpn-subscription-for-any-client
cd sotavpn-subscription-for-any-client
python3 sotavpn_bridge_to_freedom.py
```

The program tells you what it is doing and then waits. The first line of the
journal says which ports are open.

Now put one of these addresses into your client, replacing the access key with
yours. The program serves both at once, and the ports are values in settings.py:

```
http://127.0.0.1:25080/sub/your-access-key
https://127.0.0.1:25443/sub/your-access-key
```

The certificate of the secure port is self signed, so a client needs permission
to accept it. The section about HTTPS below explains that switch.

The first request takes about fifteen seconds, because the program walks all
locations of the service. Later requests are answered at once.

If you want to know whether it works before touching a client, open the root
page of either port in a browser:

```
http://127.0.0.1:25080/
https://127.0.0.1:25443/
```

It lists every answer this program can give, with ready to use addresses.

To stop the program, press Control and C in the same terminal.

## Every answer this program gives

The address of the subscription carries the access key and, when you want
something other than the default, a suffix. Both ports serve the same list, so
use the one your client likes, plain or secure:

```
http://127.0.0.1:25080/sub/<access key>               base64, the default of most clients
https://127.0.0.1:25443/sub/<access key>/raw          the same list as open vless links
http://127.0.0.1:25080/sub/<access key>/clash         YAML for Clash, Mihomo and Stash
https://127.0.0.1:25443/sub/<access key>/singbox      JSON outbounds for sing-box and Hiddify
http://127.0.0.1:25080/sub/<access key>/singbox-full  a complete sing-box configuration
https://127.0.0.1:25443/sub/<access key>/xray         JSON outbounds for Xray and the 3x-ui panel
http://127.0.0.1:25080/sub/<access key>/xray-full     a complete Xray configuration with local socks
https://127.0.0.1:25443/sub/<access key>/html         a page for a human being
http://127.0.0.1:25080/sub/<access key>/csv           a table for manual entry
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

sing-box and Xray by hand: take the full answer of the one you use and save it
as a configuration file:

```
https://127.0.0.1:25443/sub/<access key>/singbox-full
http://127.0.0.1:25080/sub/<access key>/xray-full
```

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

The program writes logs: the answers the vendor gives, the bodies the vendor
sends with a refusal, and the journal of its own run. They lie next to the
program, in the directory named by LOGS_DIRECTORY in settings.py.

How those files are named, which suffix each one carries and how the files of a
previous pass are put aside are values in settings.py as well, so this file does
not describe them. The directory stays flat: one file per account and per pass,
never a subdirectory.

The directory is listed in .gitignore, and it belongs there: a raw vendor answer
carries the addresses, the keys and the camouflage names of your account, so the
directory is as private as your access key.

## HTTPS and the certificate

The program serves plain HTTP and HTTPS at the same time. The root page of each
port tells the addresses with that very scheme, so a visitor of the secure port
is never sent to the plain one. The ports themselves are values in settings.py,
and the first lines of the journal print the addresses the program opened.

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
uses the plain port.

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

## Run it as a service

The installer puts the program where the account that runs it keeps its
programs, writes a systemd service for it and starts that service:

```bash
python3 install_sotavpn_bridge.py install
```

Root runs it, the program goes into the system directories and the service
starts at boot before anybody logs in. An ordinary user runs it, the program
goes into that home directory, the service lives in the user manager, and the
installer turns linger on so it starts at boot without a login. The paths of
both modes are the SYSTEM_INSTALL and USER_INSTALL sets of settings.py, so
there is one place to change them.

Afterwards the command is on your path, and the state of the service and the
last lines of its journal are one command away:

```bash
python3 install_sotavpn_bridge.py status
```

To take the installation away again:

```bash
python3 install_sotavpn_bridge.py uninstall
```

Running install again is the way to update: the fresh program and the fresh
settings replace the installed ones, the settings of the previous installation
stay beside the new ones under a name that starts with their own moment, and
the service is restarted.

Nothing is ever deleted. The trash takes what goes away, and where a machine
has none, the files are renamed beside themselves. The settings of a system
installation stay in place, and the program directory (with the logs inside
it) goes to the trash, so even the logs are not lost.

## If something does not work

The journal says what happened, in plain words. Common cases:

The vendor refused the request: the access key is wrong or the subscription
ended. Check the key in your account page.

The vendor did not answer: the machine has no way to reach the vendor, or the
vendor is down. The bridge keeps serving the previous list, so your client
keeps working, and the journal says how old that list is.

The plain port or the HTTPS port is not free: somebody holds it. Each port is
treated on its own, so when one of them cannot be taken, the program keeps
serving on the other. When the holder is another copy of this program, the
program asks that copy to stop and then kills it, so the copy you started last
wins, and in a fight with the service the service wins in the end, because
systemd starts it again every half a minute until the port is free. A process
of any other program is never touched: the journal names it, and the way out is
to change HTTP_PORT or HTTPS_PORT in settings.py. On Windows, Hyper-V and WSL
sometimes reserve a range of high ports in advance, and then another number
helps.

Nothing helps with a client that refuses a self signed certificate: use the
plain port, or put a web server with a real certificate in front.

## Checks

```bash
python3 -m unittest discover
```

The checks cover the answer formats, the automatic test groups, the choice of
the answer by the client name, the device identifier, the collection of the
node list, and the behaviour when the vendor stops answering. The installer
has checks of its own: they build a root of their own and record every command
they would have run, so a check never touches the machine it runs on.
