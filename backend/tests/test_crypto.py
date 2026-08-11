from app.core.crypto import decrypt_secret, encrypt_secret


def test_encrypt_decrypt_round_trip():
    ciphertext = encrypt_secret("sk-super-secret-key")
    assert ciphertext != "sk-super-secret-key"
    assert decrypt_secret(ciphertext) == "sk-super-secret-key"


def test_decrypt_invalid_token_returns_none():
    assert decrypt_secret("not-a-valid-fernet-token") is None
