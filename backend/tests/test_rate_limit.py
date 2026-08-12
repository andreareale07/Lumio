"""Rate limiting sugli endpoint di autenticazione (milestone 11, SPEC §52).
`app/core/rate_limit.py` — Redis condiviso (chiave keyed su IP client, sempre
127.0.0.1 nei test), pulito ad ogni test da `_reset_connection_pools` in
conftest.py (altrimenti i tanti register/login di test diversi
esaurirebbero il limite reale)."""
from app.core.rate_limit import LOGIN_RATE_LIMIT, REGISTER_RATE_LIMIT


async def test_login_is_rate_limited_after_repeated_failed_attempts(client):
    limit = int(LOGIN_RATE_LIMIT.split("/")[0])
    payload = {"email": "nobody@example.com", "password": "wrong-password"}

    for _ in range(limit):
        response = await client.post("/api/v1/auth/login", json=payload)
        assert response.status_code == 401

    blocked = await client.post("/api/v1/auth/login", json=payload)
    assert blocked.status_code == 429


async def test_register_is_rate_limited_after_repeated_attempts(client):
    limit = int(REGISTER_RATE_LIMIT.split("/")[0])

    for i in range(limit):
        response = await client.post(
            "/api/v1/auth/register",
            json={"email": f"rl-register-{i}@example.com", "password": "correct-password-123", "display_name": "T"},
        )
        assert response.status_code == 201

    blocked = await client.post(
        "/api/v1/auth/register",
        json={"email": "rl-register-over@example.com", "password": "correct-password-123", "display_name": "T"},
    )
    assert blocked.status_code == 429
