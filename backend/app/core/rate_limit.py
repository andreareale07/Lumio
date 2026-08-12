"""Rate limiting (SPEC §52) — backend Redis condiviso, cosi' il limite regge
anche con piu' worker/replica del processo app (a differenza di uno storage
in-memory, che sarebbe per-processo).

Limiti stretti solo sugli endpoint di autenticazione (SPEC §52: superficie
di attacco per credential stuffing/enumerazione, non un limite generale
sull'intera API, che qui non e' richiesto).
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import get_settings

limiter = Limiter(key_func=get_remote_address, storage_uri=get_settings().redis_url)

LOGIN_RATE_LIMIT = "5/minute"
REGISTER_RATE_LIMIT = "5/minute"
REFRESH_RATE_LIMIT = "20/minute"
