"""Stato minimo persistente per i job async innescabili manualmente
(refresh prezzi, ricalcolo snapshot) o dal cron — gap UX emerso testando
M09b: un toast effimero non basta, l'utente deve poter sapere se/quando
l'ultima esecuzione e' riuscita anche dopo un refresh pagina (CLAUDE.md,
"operazioni lunghe -> job async" non dice nulla sullo stato letto DOPO,
ma senza questo modulo non c'era modo di consultarlo).

Pensato per essere riusabile da qualunque job futuro: basta aggiungere il
suo nome a `JOB_KINDS` (app/models/job_run.py) e usare `tracked_job_run`
attorno al corpo del job.

Regola d'oro: `start_run`/`finish_run` aprono SEMPRE una `rls_session` loro
propria, mai quella del job "vero" che fa il lavoro effettivo. Due motivi:
1) lo stato "running" deve essere visibile a una richiesta HTTP concorrente
   (polling) SUBITO — non solo dopo che il job finisce e committa la sua
   transazione.
2) `SET LOCAL app.current_user_id` scade al commit (vedi app/db/rls.py) —
   un commit intermedio nella sessione del job romperebbe la RLS per le
   query successive del job stesso (lo stesso bug gia' incontrato in
   M09a, vedi position_service.py).
"""
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.rls import rls_session
from app.models.job_run import JobRun

_MESSAGE_MAX_LENGTH = 500


async def _get_or_create(db: AsyncSession, workspace_id: uuid.UUID, job_kind: str) -> JobRun:
    result = await db.execute(
        select(JobRun).where(JobRun.workspace_id == workspace_id, JobRun.job_kind == job_kind)
    )
    run = result.scalar_one_or_none()
    if run is None:
        run = JobRun(workspace_id=workspace_id, job_kind=job_kind, status="running", started_at=datetime.now(UTC))
        db.add(run)
    return run


async def start_run(
    workspace_id: uuid.UUID, user_id: uuid.UUID, job_kind: str, job_id: str | None = None
) -> None:
    async with rls_session(user_id) as db:
        run = await _get_or_create(db, workspace_id, job_kind)
        run.status = "running"
        run.started_at = datetime.now(UTC)
        run.finished_at = None
        run.message = None
        run.job_id = job_id
        await db.commit()


async def finish_run(
    workspace_id: uuid.UUID, user_id: uuid.UUID, job_kind: str, success: bool, message: str | None
) -> None:
    async with rls_session(user_id) as db:
        run = await _get_or_create(db, workspace_id, job_kind)
        run.status = "success" if success else "failed"
        run.finished_at = datetime.now(UTC)
        run.message = message[:_MESSAGE_MAX_LENGTH] if message else None
        await db.commit()


async def get_latest_run(db: AsyncSession, workspace_id: uuid.UUID, job_kind: str) -> JobRun | None:
    """Lettura per l'endpoint API: usa la sessione RLS gia' della request,
    nessuna sessione dedicata (a differenza di start_run/finish_run, che ne
    aprono una propria perche' scrivono da un contesto worker)."""
    result = await db.execute(
        select(JobRun).where(JobRun.workspace_id == workspace_id, JobRun.job_kind == job_kind)
    )
    return result.scalar_one_or_none()


@dataclass
class JobRunHandle:
    """Passata al corpo del job da `tracked_job_run`: il job scrive qui il
    messaggio di risultato prima di uscire con successo."""

    message: str | None = None


@asynccontextmanager
async def tracked_job_run(
    workspace_id: uuid.UUID, user_id: uuid.UUID, job_kind: str, job_id: str | None = None
) -> AsyncIterator[JobRunHandle]:
    """Registra 'running' all'ingresso, 'success'/'failed' all'uscita —
    anche in caso di eccezione, che viene comunque ri-lanciata: chi chiama
    decide se ignorarla (es. il cron, che passa al workspace successivo) o
    lasciarla propagare (es. il job del trigger manuale, dove arq la
    registra comunque come job fallito nella sua coda)."""
    await start_run(workspace_id, user_id, job_kind, job_id)
    handle = JobRunHandle()
    try:
        yield handle
    except Exception as exc:
        await finish_run(workspace_id, user_id, job_kind, success=False, message=str(exc))
        raise
    else:
        await finish_run(workspace_id, user_id, job_kind, success=True, message=handle.message)
