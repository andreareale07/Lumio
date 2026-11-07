"""`state` OAuth del flusso Open Banking e generazione delle chiavi."""
import uuid
from datetime import UTC, datetime, timedelta

import jwt
from cryptography import x509
from cryptography.hazmat.primitives import serialization

from app.core.config import Settings, get_settings
from app.core.crypto import decrypt_secret, encrypt_secret
from app.core.keys import derive_key
from app.core.security import JWT_ALGORITHM, create_access_token, decode_access_token
from app.integrations.google import oauth as google_oauth
from app.openbanking import state as ob_state
from app.openbanking.keys import generate_keypair


def test_state_roundtrip():
    workspace_id, user_id, connection_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    nonce = ob_state.new_nonce()
    decoded = ob_state.decode_state(ob_state.build_state(workspace_id, user_id, connection_id, nonce))
    assert decoded is not None
    assert (decoded.workspace_id, decoded.user_id, decoded.connection_id, decoded.nonce) == (
        workspace_id,
        user_id,
        connection_id,
        nonce,
    )


def test_tampered_or_garbage_state_is_rejected():
    state = ob_state.build_state(uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), "n")
    assert ob_state.decode_state(state[:-3] + "abc") is None
    assert ob_state.decode_state("not-a-jwt") is None


def test_expired_state_is_rejected():
    past = datetime.now(UTC) - timedelta(minutes=30)
    token = jwt.encode(
        {
            "purpose": "open_banking_state",
            "workspace_id": str(uuid.uuid4()),
            "user_id": str(uuid.uuid4()),
            "connection_id": str(uuid.uuid4()),
            "nonce": "n",
            "iat": past,
            "exp": past + timedelta(minutes=10),
        },
        derive_key("open_banking_state").hex(),
        algorithm=JWT_ALGORITHM,
    )
    assert ob_state.decode_state(token) is None


def test_state_of_another_flow_cannot_be_replayed_here():
    """Un `state` valido per Google (stessa SECRET_KEY) non deve passare."""
    google_state = google_oauth.build_state(uuid.uuid4(), uuid.uuid4())
    assert ob_state.decode_state(google_state) is None


def test_nonce_hash_is_stable_and_not_the_nonce():
    assert ob_state.hash_nonce("abc") == ob_state.hash_nonce("abc")
    assert ob_state.hash_nonce("abc") != "abc"
    assert ob_state.new_nonce() != ob_state.new_nonce()


def test_generated_keypair_is_consistent_and_private_key_is_not_in_certificate():
    private_pem, certificate_pem = generate_keypair()
    assert "PRIVATE KEY" in private_pem
    assert "PRIVATE KEY" not in certificate_pem
    key = serialization.load_pem_private_key(private_pem.encode(), password=None)
    certificate = x509.load_pem_x509_certificate(certificate_pem.encode())
    assert certificate.public_key().public_numbers() == key.public_key().public_numbers()


# ---- chiavi per scopo e SECRET_KEY ------------------------------------------------


def test_state_and_access_token_use_independent_keys():
    """Anche con payload identico e `purpose` giusto, lo state firmato con il
    `SECRET_KEY` grezzo (come un token di accesso) non e' accettato."""
    now = datetime.now(UTC)
    forged = jwt.encode(
        {
            "purpose": "open_banking_state",
            "workspace_id": str(uuid.uuid4()),
            "user_id": str(uuid.uuid4()),
            "connection_id": str(uuid.uuid4()),
            "nonce": "n",
            "iat": now,
            "exp": now + timedelta(minutes=5),
        },
        get_settings().secret_key,
        algorithm=JWT_ALGORITHM,
    )
    assert ob_state.decode_state(forged) is None
    state = ob_state.build_state(uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), "n")
    assert decode_access_token(state) is None
    assert ob_state.decode_state(create_access_token(uuid.uuid4())) is None


def test_derived_keys_differ_per_purpose():
    assert derive_key("a") != derive_key("b")
    assert derive_key("a") == derive_key("a")
    assert derive_key("a") != get_settings().secret_key.encode()


def test_encrypt_roundtrip_and_legacy_ciphertext_still_readable():
    import base64
    import hashlib

    from cryptography.fernet import Fernet

    assert decrypt_secret(encrypt_secret("segreto")) == "segreto"
    legacy = Fernet(base64.urlsafe_b64encode(hashlib.sha256(get_settings().secret_key.encode()).digest()))
    old_ciphertext = legacy.encrypt(b"vecchio-segreto").decode()
    assert decrypt_secret(old_ciphertext) == "vecchio-segreto"
    # I nuovi segreti NON si decifrano piu' con la sola chiave storica.
    new_ciphertext = encrypt_secret("nuovo")
    from cryptography.fernet import InvalidToken
    import pytest

    with pytest.raises(InvalidToken):
        legacy.decrypt(new_ciphertext.encode())


_BASE_ENV = {"database_url": "postgresql+asyncpg://x", "redis_url": "redis://x"}


def test_production_rejects_weak_or_placeholder_secret_key():
    import pytest

    for weak in ("short", "change-me-to-a-long-random-value", "ci-secret-key", "a" * 20):
        with pytest.raises(ValueError):
            Settings(_env_file=None, app_env="production", secret_key=weak, **_BASE_ENV)


def test_production_accepts_strong_key_and_development_is_lenient():
    import secrets

    Settings(_env_file=None, app_env="production", secret_key=secrets.token_urlsafe(64), **_BASE_ENV)
    Settings(_env_file=None, app_env="development", secret_key="short", **_BASE_ENV)


def test_production_requires_https_for_open_banking_urls():
    import pytest
    import secrets

    strong = secrets.token_urlsafe(64)
    with pytest.raises(ValueError):
        Settings(_env_file=None, app_env="production", secret_key=strong, open_banking_enabled=True,
                 open_banking_redirect_uri="http://lumio.example/cb", **_BASE_ENV)
    with pytest.raises(ValueError):
        Settings(_env_file=None, app_env="production", secret_key=strong,
                 open_banking_base_url="http://evil.example", **_BASE_ENV)
