"""Create a self-signed certificate for the probe server.

    python make_cert.py --name 192.168.56.10 --name probe.local

Writes probe-cert.pem and probe-key.pem and prints the SHA-256 fingerprint
to put into the client's probe.ini. Needs the `cryptography` package on the
machine that runs the server (not on the shop-floor PC).

Without `cryptography`, OpenSSL does the same:

    openssl req -x509 -newkey rsa:2048 -nodes -days 30 \\
        -keyout probe-key.pem -out probe-cert.pem \\
        -subj "/CN=nestrack-probe" -addext "subjectAltName=IP:192.168.56.10"
"""

import argparse
import datetime
import ipaddress
import sys

from probe_server import fingerprint_of_pem


def make_cert(names, cert_path="probe-cert.pem", key_path="probe-key.pem",
              days=30) -> str:
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "nestrack-probe")])
    alt = []
    for name in names:
        try:
            alt.append(x509.IPAddress(ipaddress.ip_address(name)))
        except ValueError:
            alt.append(x509.DNSName(name))
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(subject)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(minutes=5))
            .not_valid_after(now + datetime.timedelta(days=days))
            .add_extension(x509.SubjectAlternativeName(alt), critical=False)
            .sign(key, hashes.SHA256()))
    with open(key_path, "wb") as fh:
        fh.write(key.private_bytes(serialization.Encoding.PEM,
                                   serialization.PrivateFormat.TraditionalOpenSSL,
                                   serialization.NoEncryption()))
    with open(cert_path, "wb") as fh:
        fh.write(cert.public_bytes(serialization.Encoding.PEM))
    return fingerprint_of_pem(cert_path)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--name", action="append", default=[],
                        help="IP address or host name the client will use; repeatable")
    parser.add_argument("--days", type=int, default=30)
    args = parser.parse_args(argv)
    names = args.name or ["127.0.0.1", "localhost"]
    print("Fingerprint (SHA-256): %s" % make_cert(names, days=args.days))
    return 0


if __name__ == "__main__":
    sys.exit(main())
