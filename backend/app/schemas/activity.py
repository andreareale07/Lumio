"""Schema del cruscotto "Attività": vista aggregata di sola lettura su tutte
le elaborazioni in corso o recenti del workspace — import (+ classificazione
AI collegata), riclassificazione, ed i job schedulati (refresh prezzi,
snapshot, export Google Sheets), questi ultimi mostrati anche quando non
sono attivi in questo momento, cosi' l'utente vede sempre "cosa ha fatto
l'ultima volta il sistema", non solo cosa sta facendo ora.
"""
from datetime import datetime

from pydantic import BaseModel


class ActivityItemOut(BaseModel):
    kind: str
    # Testo gia' pronto (import/AI classification: interpola il nome file,
    # sempre italiano — nessuna DECISION REQUIRED riaperta qui). `label_key`
    # ha precedenza quando presente: i job schedulati (market_data,
    # snapshot, ecc.) restituiscono una chiave i18n stabile invece di testo
    # italiano hardcoded (stessa scelta gia' fatta per `job_registry.py`,
    # commit 3545f62 — il frontend risolve con `t(`jobs:${label_key}`)`).
    label: str
    label_key: str | None = None
    status: str
    # Valorizzato solo per i job che emettono eventi SSE riga-per-riga
    # (import, ai_classification, reclassification, google_sheets_export):
    # e' il path relativo dell'endpoint /events gia' esistente per quel job
    # specifico (ognuno con la propria convenzione di namespace/topic_id —
    # esporre l'URL pronto evita che il frontend debba ricostruirla). I job
    # schedulati (market_data, snapshot) non hanno mai granularita' live,
    # solo lo stato dell'ultima esecuzione persistito da tracked_job_run.
    events_url: str | None = None
    # Endpoint (POST) per interrompere l'attivita', solo per quelle che lo
    # permettono e solo finche' sono in corso.
    cancel_url: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    message: str | None = None
    processed: int | None = None
    total: int | None = None


class ActivityListOut(BaseModel):
    items: list[ActivityItemOut]
