import logging

from fastapi import APIRouter, Response
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.core.redis import redis_client
from app.db.base import engine

router = APIRouter(tags=["health"])
logger = logging.getLogger("lumio.health")


@router.get("/health")
async def health() -> dict:
    """Liveness: il processo applicativo e' vivo. Nessuna dipendenza esterna verificata."""
    return {"status": "ok"}


@router.get("/ready")
async def ready() -> Response:
    """Readiness: verifica che le dipendenze (Postgres, Redis) siano raggiungibili.

    Endpoint non autenticato (usato da orchestratori/health check): il body
    riporta solo "ok"/"unreachable" per dipendenza, mai il messaggio
    d'eccezione grezzo (SPEC §55 — puo' rivelare host/porta/versione interni
    a chi non e' autenticato). Il dettaglio completo resta nei log server.
    """
    checks = {"database": "ok", "redis": "ok"}

    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        logger.exception("readiness check: database unreachable")
        checks["database"] = "unreachable"

    try:
        await redis_client.ping()
    except Exception:
        logger.exception("readiness check: redis unreachable")
        checks["redis"] = "unreachable"

    is_ready = all(v == "ok" for v in checks.values())
    body = {"status": "ok" if is_ready else "unavailable", "checks": checks}
    return JSONResponse(content=body, status_code=200 if is_ready else 503)
