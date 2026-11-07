"""Generazione della coppia di chiavi dell'app Enable Banking.

La chiave privata RSA resta sul server (cifrata a riposo, mai restituita
dall'API); all'utente va solo il certificato autofirmato, da caricare sul
Control Panel del provider insieme alla registrazione dell'applicazione.
"""
from datetime import UTC, datetime, timedelta

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

_CERT_VALIDITY_DAYS = 3650


def generate_keypair() -> tuple[str, str]:
    """Ritorna `(private_key_pem, certificate_pem)`."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Lumio")])
    now = datetime.now(UTC)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=_CERT_VALIDITY_DAYS))
        .sign(key, hashes.SHA256())
    )
    private_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    certificate_pem = certificate.public_bytes(serialization.Encoding.PEM).decode()
    return private_pem, certificate_pem
