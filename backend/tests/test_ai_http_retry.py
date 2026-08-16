import httpx
import pytest

from app.ai.http_retry import post_with_retry


@pytest.fixture(autouse=True)
def _no_real_sleep(monkeypatch):
    # Il backoff esponenziale non deve rallentare la suite: verifichiamo il
    # comportamento (numero di tentativi, esito), non i tempi di attesa
    # reali.
    async def _instant_sleep(_seconds):
        return None

    monkeypatch.setattr("app.ai.http_retry.asyncio.sleep", _instant_sleep)


async def test_retries_on_429_then_succeeds(httpx_mock):
    httpx_mock.add_response(url="http://provider.local/v1", status_code=429)
    httpx_mock.add_response(url="http://provider.local/v1", status_code=200, json={"ok": True})
    async with httpx.AsyncClient() as client:
        response = await post_with_retry(client, "http://provider.local/v1", json={})
    assert response.status_code == 200
    assert len(httpx_mock.get_requests()) == 2


async def test_retries_on_5xx_then_succeeds(httpx_mock):
    httpx_mock.add_response(url="http://provider.local/v1", status_code=503)
    httpx_mock.add_response(url="http://provider.local/v1", status_code=200, json={"ok": True})
    async with httpx.AsyncClient() as client:
        response = await post_with_retry(client, "http://provider.local/v1", json={})
    assert response.status_code == 200


async def test_gives_up_after_max_retries_and_returns_last_response(httpx_mock):
    # settings.ai_max_retries di default e' 2 -> 1 tentativo iniziale + 2
    # retry = 3 richieste totali, tutte fallite.
    for _ in range(3):
        httpx_mock.add_response(url="http://provider.local/v1", status_code=429)
    async with httpx.AsyncClient() as client:
        response = await post_with_retry(client, "http://provider.local/v1", json={})
    assert response.status_code == 429
    assert len(httpx_mock.get_requests()) == 3


async def test_non_retryable_status_returns_immediately():
    async def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400)

    transport = httpx.MockTransport(_handler)
    async with httpx.AsyncClient(transport=transport) as client:
        response = await post_with_retry(client, "http://provider.local/v1", json={})
    assert response.status_code == 400


async def test_success_on_first_attempt_makes_no_retries(httpx_mock):
    httpx_mock.add_response(url="http://provider.local/v1", status_code=200, json={"ok": True})
    async with httpx.AsyncClient() as client:
        response = await post_with_retry(client, "http://provider.local/v1", json={})
    assert response.status_code == 200
    assert len(httpx_mock.get_requests()) == 1
