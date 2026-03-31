import datetime
import ipaddress
import logging
import os
import socket
import ssl

logger = logging.getLogger(__name__)

_PIROBOT_DIR = os.path.join(os.environ["HOME"], ".pirobot")
CERT_PATH = os.path.join(_PIROBOT_DIR, "server.crt")
KEY_PATH = os.path.join(_PIROBOT_DIR, "server.key")


def get_ssl_context() -> ssl.SSLContext:
    if not os.path.exists(CERT_PATH) or not os.path.exists(KEY_PATH):
        _generate_cert()
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(CERT_PATH, KEY_PATH)
    return ctx


def _generate_cert() -> None:
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    logger.info(f"Generating self-signed TLS certificate → {CERT_PATH}")

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    hostname = socket.gethostname()
    try:
        local_ip = ipaddress.IPv4Address(socket.gethostbyname(hostname))
    except Exception:
        local_ip = ipaddress.IPv4Address("127.0.0.1")

    san = x509.SubjectAlternativeName([
        x509.DNSName(hostname),
        x509.DNSName("localhost"),
        x509.IPAddress(ipaddress.IPv4Address("127.0.0.1")),
        x509.IPAddress(local_ip),
    ])

    now = datetime.datetime.now(datetime.timezone.utc)
    subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, hostname)])
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + datetime.timedelta(days=3650))
        .add_extension(san, critical=False)
        .sign(key, hashes.SHA256())
    )

    os.makedirs(_PIROBOT_DIR, exist_ok=True)
    with open(KEY_PATH, "wb") as f:
        f.write(key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        ))
    os.chmod(KEY_PATH, 0o600)

    with open(CERT_PATH, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))

    logger.info("TLS certificate generated (valid 10 years)")
