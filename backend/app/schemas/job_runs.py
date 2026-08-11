from datetime import datetime

from pydantic import BaseModel


class JobRunOut(BaseModel):
    """Stato dell'ultima esecuzione di un job (refresh prezzi/ricalcolo
    snapshot) — vedi app/services/job_run_tracker.py. Nessun `id`/`job_id`
    esposto: sono dettagli tecnici, non servono al frontend (che mostra solo
    stato/orario/messaggio)."""

    status: str
    started_at: datetime
    finished_at: datetime | None
    message: str | None

    model_config = {"from_attributes": True}
