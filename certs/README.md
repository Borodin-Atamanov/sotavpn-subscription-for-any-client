# About the certificate in this directory

bridge-self-signed-certificate.pem is the public part of a self signed
certificate, and bridge-self-signed-private-key.pem is its private key.

Both files are in a public repository on purpose: the program must serve
HTTPS right after the clone, without asking the user to create anything.

The price of that convenience is written here plainly. The private key is
public, so anyone who can stand between your machine and this program can
pretend to be this program. Somebody who only listens to the network cannot
read your traffic, and that is what a self signed certificate is good for.

Regenerate both files for yourself, one command:

```bash
openssl req -x509 -newkey rsa:2048 -nodes -sha256 -days 3650 \
  -keyout certs/bridge-self-signed-private-key.pem \
  -out certs/bridge-self-signed-certificate.pem \
  -subj "/CN=sotavpn-bridge-local" \
  -addext "subjectAltName=DNS:localhost,IP:127.0.0.1"
```

Cloned from a fresh start, the certificate lives until 2036. If it ever
expires, the journal says the certificate is not usable, and the same command
makes a new one in a second.
