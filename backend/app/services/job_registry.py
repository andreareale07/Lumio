"""Metadati descrittivi dei job del sistema (pagina Impostazioni > Job) — un
solo posto da estendere quando un futuro job si aggiunge, invece di far
scoprire all'utente cosa esiste leggendo il codice.

Due categorie, mostrate distintamente in UI (vedi CategoryInfo):
- "scheduled": girano da soli via cron, hanno un vero on/off qui.
- "triggered": partono solo da un'azione dell'utente (import, export...);
  il loro "on/off" vive altrove (profilo AI attivo per workspace,
  GOOGLE_ENABLED di istanza) — qui si mostrano solo i loro parametri.

Ogni parametro e' o EDITABILE (letto/scritto in `system_settings`, ha
effetto entro il prossimo utilizzo del job, mai un riavvio) o SOLO LETTURA
(timeout arq, letti una volta sola all'avvio del processo worker — cambiarli
richiede comunque riavviarlo, quindi non ha senso promettere un salvataggio
con effetto immediato).
"""
from dataclasses import dataclass, field
from typing import Any

from app.core.config import get_settings
from app.services.system_settings_service import get_setting_value


@dataclass
class JobParameterSpec:
    label: str
    unit: str
    editable: bool
    # Editabile: chiave in system_settings da cui leggere/scrivere il valore
    # corrente (il PATCH resta quello generico gia' esistente,
    # /system-settings/{key} — nessun nuovo endpoint di scrittura).
    setting_key: str | None = None
    # Sola lettura: valore preso da app.core.config.get_settings() al momento
    # della richiesta (comunque non cache-abile diversamente, e' comunque lo
    # stesso processo che serve l'API).
    settings_attr: str | None = None
    # Sola lettura, valore fisso nel codice (nessun equivalente in
    # app.core.config.Settings) — es. la cadenza di un cron registrata
    # direttamente in worker/main.py.
    static_value: Any | None = None
    readonly_reason: str | None = None


@dataclass
class JobDescriptor:
    kind: str
    category: str  # "scheduled" | "triggered"
    name: str
    description: str
    schedule_description: str | None = None
    # Perche' la cadenza stessa (non solo i timeout) e' sola lettura: arq
    # registra i cron UNA VOLTA, in Python, all'avvio del processo worker
    # (vedi worker/main.py) — cambiarla richiede una modifica al codice E un
    # riavvio, non solo un riavvio come per i timeout. Nessuna chiave in
    # system_settings la governa oggi: renderla davvero editabile
    # richiederebbe sostituire lo scheduling nativo di arq con un dispatcher
    # che rilegge l'orario a ogni tick, una ristrutturazione a se',
    # sproporzionata rispetto al problema che questa pagina risolve.
    schedule_readonly_reason: str | None = None
    disable_warning: str | None = None
    parameters: list[JobParameterSpec] = field(default_factory=list)


_READONLY_TIMEOUT_REASON = "Richiede il riavvio del worker per avere effetto (letto una sola volta all'avvio)."
_READONLY_SCHEDULE_REASON = (
    "Fissa nel codice del worker: cambiarla richiede una modifica al codice, non solo un riavvio."
)

JOB_DESCRIPTORS: list[JobDescriptor] = [
    JobDescriptor(
        kind="market_data_refresh",
        category="scheduled",
        name="Refresh prezzi di mercato",
        description="Scarica una quotazione aggiornata per ogni asset con un provider di mercato attivo (per workspace).",
        schedule_description="Ogni giorno alle 2:00",
        schedule_readonly_reason=_READONLY_SCHEDULE_REASON,
        disable_warning=(
            "I prezzi degli asset non verranno più aggiornati automaticamente ogni giorno. "
            "Il bottone \"Aggiorna ora\" nella pagina Market Data resta comunque disponibile."
        ),
        parameters=[
            JobParameterSpec(
                label="Soglia di stallo",
                unit="secondi",
                editable=True,
                setting_key="job_health.market_data_refresh.stale_after_seconds",
            ),
        ],
    ),
    JobDescriptor(
        kind="snapshot_rebuild",
        category="scheduled",
        name="Ricalcolo snapshot patrimonio",
        description="Scrive lo snapshot giornaliero di patrimonio/portfolio per ogni workspace.",
        schedule_description="Ogni giorno alle 3:00",
        schedule_readonly_reason=_READONLY_SCHEDULE_REASON,
        disable_warning=(
            "Lo storico patrimonio non verrà più aggiornato automaticamente ogni giorno "
            "(mancherà un punto dato per i giorni saltati). Il bottone \"Ricalcola ora\" nella "
            "pagina Portfolio resta comunque disponibile."
        ),
        parameters=[
            JobParameterSpec(
                label="Soglia di stallo",
                unit="secondi",
                editable=True,
                setting_key="job_health.snapshot_rebuild.stale_after_seconds",
            ),
        ],
    ),
    JobDescriptor(
        kind="stale_job_reaper",
        category="scheduled",
        name="Rilevatore job bloccati",
        description=(
            "Rileva i job rimasti bloccati da un crash del worker (nessuno stato terminale mai "
            "raggiunto) e li marca falliti — questo stesso meccanismo."
        ),
        schedule_description="Ogni 2 minuti",
        schedule_readonly_reason=_READONLY_SCHEDULE_REASON,
        disable_warning=(
            "ATTENZIONE: un job bloccato da un crash del worker (import, classificazione AI, "
            "refresh prezzi, snapshot, export Google Sheets) non verrà più rilevato automaticamente "
            "e resterà bloccato finché non intervieni manualmente."
        ),
        parameters=[
            JobParameterSpec(
                label="Soglia di stallo — Import",
                unit="secondi",
                editable=True,
                setting_key="job_health.import.stale_after_seconds",
            ),
            JobParameterSpec(
                label="Soglia di stallo — Classificazione AI",
                unit="secondi",
                editable=True,
                setting_key="job_health.ai_classification.stale_after_seconds",
            ),
            JobParameterSpec(
                label="Soglia di stallo — Refresh prezzi",
                unit="secondi",
                editable=True,
                setting_key="job_health.market_data_refresh.stale_after_seconds",
            ),
            JobParameterSpec(
                label="Soglia di stallo — Snapshot",
                unit="secondi",
                editable=True,
                setting_key="job_health.snapshot_rebuild.stale_after_seconds",
            ),
            JobParameterSpec(
                label="Soglia di stallo — Export Google Sheets",
                unit="secondi",
                editable=True,
                setting_key="job_health.google_sheets_export.stale_after_seconds",
            ),
        ],
    ),
    JobDescriptor(
        kind="import",
        category="triggered",
        name="Elaborazione import",
        description="Parsing del file (CSV/PDF) e inserimento delle transazioni, innescato da un import confermato dall'utente.",
        parameters=[
            JobParameterSpec(
                label="Soglia di stallo",
                unit="secondi",
                editable=True,
                setting_key="job_health.import.stale_after_seconds",
            ),
            JobParameterSpec(
                label="Timeout massimo esecuzione",
                unit="secondi",
                editable=False,
                settings_attr="import_job_timeout_seconds",
                readonly_reason=_READONLY_TIMEOUT_REASON,
            ),
            JobParameterSpec(
                label="Timeout apertura PDF",
                unit="secondi",
                editable=False,
                settings_attr="import_pdf_open_timeout_seconds",
                readonly_reason=_READONLY_TIMEOUT_REASON,
            ),
            JobParameterSpec(
                label="Timeout parsing PDF",
                unit="secondi",
                editable=False,
                settings_attr="import_pdf_parse_timeout_seconds",
                readonly_reason=_READONLY_TIMEOUT_REASON,
            ),
        ],
    ),
    JobDescriptor(
        kind="ai_classification",
        category="triggered",
        name="Classificazione AI",
        description=(
            "Classifica le transazioni non riconosciute dalle regole, disaccoppiato dal job di "
            "import — parte solo se un profilo AI e' attivo per il workspace."
        ),
        parameters=[
            JobParameterSpec(
                label="Soglia di stallo",
                unit="secondi",
                editable=True,
                setting_key="job_health.ai_classification.stale_after_seconds",
            ),
            JobParameterSpec(
                label="Timeout massimo esecuzione",
                unit="secondi",
                editable=False,
                settings_attr="ai_classification_job_timeout_seconds",
                readonly_reason=_READONLY_TIMEOUT_REASON,
            ),
            JobParameterSpec(
                label="Timeout per singola chiamata AI",
                unit="secondi",
                editable=False,
                settings_attr="ai_classify_timeout_seconds",
                readonly_reason=_READONLY_TIMEOUT_REASON,
            ),
        ],
    ),
    JobDescriptor(
        kind="google_sheets_export",
        category="triggered",
        name="Export Google Sheets",
        description="Esporta i dati verso Google Sheets, innescato da una richiesta di export dell'utente — richiede l'integrazione Google attiva.",
        parameters=[
            JobParameterSpec(
                label="Soglia di stallo",
                unit="secondi",
                editable=True,
                setting_key="job_health.google_sheets_export.stale_after_seconds",
            ),
            JobParameterSpec(
                label="Timeout massimo esecuzione",
                unit="secondi",
                editable=False,
                settings_attr="google_export_job_timeout_seconds",
                readonly_reason=_READONLY_TIMEOUT_REASON,
            ),
        ],
    ),
    JobDescriptor(
        kind="reclassification",
        category="triggered",
        name="Riclassificazione",
        description=(
            "Riapplica la pipeline di classificazione (regole, sistema, opzionalmente AI) alle "
            "transazioni gia' importate — innescato dall'utente dopo un aggiornamento della "
            "tassonomia. Non tocca mai le correzioni manuali."
        ),
        parameters=[
            JobParameterSpec(
                label="Soglia di stallo",
                unit="secondi",
                editable=True,
                setting_key="job_health.reclassification.stale_after_seconds",
            ),
            JobParameterSpec(
                label="Timeout massimo esecuzione",
                unit="secondi",
                editable=False,
                settings_attr="reclassification_job_timeout_seconds",
                readonly_reason=_READONLY_TIMEOUT_REASON,
            ),
        ],
    ),
]


async def _resolve_parameter(spec: JobParameterSpec) -> dict[str, Any]:
    if spec.editable:
        value = await get_setting_value(spec.setting_key, None)
    elif spec.settings_attr is not None:
        value = getattr(get_settings(), spec.settings_attr)
    else:
        value = spec.static_value
    return {
        "label": spec.label,
        "unit": spec.unit,
        "editable": spec.editable,
        "setting_key": spec.setting_key,
        "value": value,
        "readonly_reason": spec.readonly_reason,
    }


async def build_jobs_view() -> list[dict[str, Any]]:
    jobs = []
    for descriptor in JOB_DESCRIPTORS:
        enabled = None
        enabled_setting_key = None
        if descriptor.category == "scheduled":
            enabled_setting_key = f"jobs.{descriptor.kind}.enabled"
            enabled = bool(await get_setting_value(enabled_setting_key, True))
        jobs.append(
            {
                "kind": descriptor.kind,
                "category": descriptor.category,
                "name": descriptor.name,
                "description": descriptor.description,
                "schedule_description": descriptor.schedule_description,
                "schedule_readonly_reason": descriptor.schedule_readonly_reason,
                "disable_warning": descriptor.disable_warning,
                "enabled": enabled,
                "enabled_setting_key": enabled_setting_key,
                "parameters": [await _resolve_parameter(p) for p in descriptor.parameters],
            }
        )
    return jobs
