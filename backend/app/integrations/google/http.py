"""Unica deviazione dal pattern "nessun retry" degli altri provider esterni
del progetto (AI/Market Data, vedi `app/marketdata/providers/yahoo.py`): un
retry singolo con breve backoff su 429/503 verso le API Google, perche' un
export on-demand fallito per un burst di quota transitoria e' un'esperienza
peggiore di un retry silenzioso da 1-2 secondi.
"""
import asyncio

import httpx

_RETRY_STATUS_CODES = frozenset({429, 503})
_RETRY_DELAY_SECONDS = 1.5


async def request_with_retry(client: httpx.AsyncClient, method: str, url: str, **kwargs) -> httpx.Response:
    response = await client.request(method, url, **kwargs)
    if response.status_code in _RETRY_STATUS_CODES:
        await asyncio.sleep(_RETRY_DELAY_SECONDS)
        response = await client.request(method, url, **kwargs)
    return response


def raise_for_status_with_body(response: httpx.Response) -> None:
    """Come `response.raise_for_status()`, ma include il corpo della
    risposta (dove Google spiega il motivo reale, es. "Google Sheets API
    has not been used..."/"insufficient authentication scopes") nel
    messaggio dell'eccezione — `httpx.HTTPStatusError` di default mostra
    solo lo status code, insufficiente per diagnosticare un 403/400 senza
    dover riprodurre la chiamata a mano."""
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        body = response.text[:500]
        raise httpx.HTTPStatusError(f"{exc}. Risposta: {body}", request=exc.request, response=exc.response) from exc
