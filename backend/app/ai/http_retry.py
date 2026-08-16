"""Retry con backoff esponenziale per le chiamate ai provider AI cloud
(OpenAI/Anthropic/Custom) — oggi assenti del tutto: un rate-limit
temporaneo (429) o un errore transitorio del server (5xx) falliva l'intera
classificazione della riga, invece di essere ritentato una manciata di
volte prima di arrendersi.

Non usato da Ollama: locale, non ha un concetto di rate-limit cloud, e i
suoi errori sono quasi sempre di connessione (gia' gestiti come
`AIProviderError` immediato, un retry non cambierebbe l'esito).
"""
import asyncio
import random

import httpx

from app.core.config import get_settings

_RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})


async def post_with_retry(client: httpx.AsyncClient, url: str, **kwargs) -> httpx.Response:
    """Come `client.post(url, **kwargs)`, ma ritenta su 429/5xx con backoff
    esponenziale (+ jitter, per non sincronizzare i retry di piu' righe in
    parallelo sullo stesso intervallo) fino a `settings.ai_max_retries`
    tentativi aggiuntivi. Un errore di trasporto (connessione rifiutata,
    timeout) NON viene ritentato qui: risale subito al chiamante, che lo
    traduce in `AIProviderError` — un retry su un provider irraggiungibile
    non aiuterebbe e allungherebbe solo il tempo prima di segnalarlo.
    """
    settings = get_settings()
    attempt = 0
    while True:
        response = await client.post(url, **kwargs)
        if response.status_code not in _RETRYABLE_STATUS_CODES or attempt >= settings.ai_max_retries:
            return response
        attempt += 1
        backoff_seconds = min(2**attempt, 8) + random.uniform(0, 0.5)
        await asyncio.sleep(backoff_seconds)
