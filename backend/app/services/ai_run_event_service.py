"""Registro degli eventi del motore AI di classificazione (vedi
`app/models/ai_run_event.py`): scrittura, lettura e potatura.

Nessun commit qui: lo fa il chiamante, nella stessa transazione in cui gia'
scrive (la sessione RLS in uso ha l'identita' impostata solo fino al commit).
"""
import uuid
from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_run_event import AIRunEvent

# Si conservano solo gli ultimi eventi per workspace: il registro serve a
# capire cosa non va ADESSO, non a fare da archivio storico.
MAX_EVENTS_PER_WORKSPACE = 500
# Tetto di eventi di errore per singola esecuzione: un provider spento su
# 3000 righe non deve produrre 3000 righe di registro identiche.
MAX_ERROR_EVENTS_PER_RUN = 20
_MESSAGE_MAX_LENGTH = 500


@dataclass(frozen=True)
class PendingEvent:
    severity: str
    code: str
    message: str


def describe_provider_error(exc: BaseException) -> str:
    """Descrizione SICURA di un errore del provider: solo il tipo di eccezione
    e, se c'e', lo status HTTP. Mai `str(exc)`: i messaggi di httpx contengono
    l'URL completo e alcuni provider mettono la chiave API nella query string
    — regola non negoziabile (CLAUDE.md): le chiavi non finiscono mai in
    log, risposte API o UI."""
    cause = exc.__cause__ or exc
    status = getattr(getattr(cause, "response", None), "status_code", None)
    name = type(cause).__name__
    return f"{name} (HTTP {status})" if status else name


async def record_events(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    run_kind: str,
    events: Iterable[PendingEvent],
    import_id: uuid.UUID | None = None,
) -> None:
    """Aggiunge gli eventi alla sessione e pota il registro: la potatura vive
    qui, non nei chiamanti, cosi' nessun percorso di scrittura puo' dimenticarla."""
    for event in events:
        db.add(
            AIRunEvent(
                workspace_id=workspace_id,
                run_kind=run_kind,
                import_id=import_id,
                severity=event.severity,
                code=event.code,
                message=event.message[:_MESSAGE_MAX_LENGTH],
            )
        )
    await prune_events(db, workspace_id)


async def prune_events(db: AsyncSession, workspace_id: uuid.UUID) -> None:
    """Tiene gli ultimi `MAX_EVENTS_PER_WORKSPACE` eventi, elimina il resto."""
    cutoff = (
        await db.execute(
            select(AIRunEvent.created_at)
            .where(AIRunEvent.workspace_id == workspace_id)
            .order_by(AIRunEvent.created_at.desc())
            .offset(MAX_EVENTS_PER_WORKSPACE)
            .limit(1)
        )
    ).scalar_one_or_none()
    if cutoff is not None:
        await db.execute(
            delete(AIRunEvent).where(AIRunEvent.workspace_id == workspace_id, AIRunEvent.created_at <= cutoff)
        )


async def list_events(
    db: AsyncSession, workspace_id: uuid.UUID, severity: str | None, limit: int, offset: int
) -> tuple[list[AIRunEvent], int]:
    query = select(AIRunEvent).where(AIRunEvent.workspace_id == workspace_id)
    count_query = select(func.count()).select_from(AIRunEvent).where(AIRunEvent.workspace_id == workspace_id)
    if severity is not None:
        query = query.where(AIRunEvent.severity == severity)
        count_query = count_query.where(AIRunEvent.severity == severity)
    rows = (
        await db.execute(query.order_by(AIRunEvent.created_at.desc(), AIRunEvent.id).limit(limit).offset(offset))
    ).scalars().all()
    total = (await db.execute(count_query)).scalar_one()
    return list(rows), total
