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

REWORK i18n (SPEC_FE_REDESIGN, DECISION REQUIRED su "testo backend"):
questo modulo NON restituisce piu' testo in nessuna lingua, solo CHIAVI
i18next stabili (namespace "jobs" nel frontend, vedi
`frontend/src/locales/{it,en}/jobs.json`). Il backend resta
language-agnostic per costruzione — un futuro secondo consumer dell'API
(mobile, un secondo frontend) non eredita l'italiano hardcoded. Le chiavi
sono l'identita' stabile di ogni etichetta: rinominare un JOB_DESCRIPTOR
non deve mai cambiare le chiavi generate qui sotto una volta pubblicate.
"""
from dataclasses import dataclass, field
from typing import Any

from app.core.config import get_settings
from app.services.system_settings_service import get_setting_value


@dataclass
class JobParameterSpec:
    label_key: str
    unit_key: str
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
    readonly_reason_key: str | None = None


@dataclass
class JobDescriptor:
    kind: str
    category: str  # "scheduled" | "triggered"
    name_key: str
    description_key: str
    schedule_description_key: str | None = None
    # Perche' la cadenza stessa (non solo i timeout) e' sola lettura: arq
    # registra i cron UNA VOLTA, in Python, all'avvio del processo worker
    # (vedi worker/main.py) — cambiarla richiede una modifica al codice E un
    # riavvio, non solo un riavvio come per i timeout. Nessuna chiave in
    # system_settings la governa oggi: renderla davvero editabile
    # richiederebbe sostituire lo scheduling nativo di arq con un dispatcher
    # che rilegge l'orario a ogni tick, una ristrutturazione a se',
    # sproporzionata rispetto al problema che questa pagina risolve.
    schedule_readonly_reason_key: str | None = None
    disable_warning_key: str | None = None
    parameters: list[JobParameterSpec] = field(default_factory=list)


_READONLY_TIMEOUT_REASON_KEY = "readonlyReason.timeout"
_READONLY_SCHEDULE_REASON_KEY = "readonlyReason.schedule"
_STALE_THRESHOLD_KEY = "params.staleThreshold"
_MAX_EXECUTION_TIMEOUT_KEY = "params.maxExecutionTimeout"
_SECONDS_UNIT_KEY = "units.seconds"

JOB_DESCRIPTORS: list[JobDescriptor] = [
    JobDescriptor(
        kind="market_data_refresh",
        category="scheduled",
        name_key="marketDataRefresh.name",
        description_key="marketDataRefresh.description",
        schedule_description_key="marketDataRefresh.scheduleDescription",
        schedule_readonly_reason_key=_READONLY_SCHEDULE_REASON_KEY,
        disable_warning_key="marketDataRefresh.disableWarning",
        parameters=[
            JobParameterSpec(
                label_key=_STALE_THRESHOLD_KEY,
                unit_key=_SECONDS_UNIT_KEY,
                editable=True,
                setting_key="job_health.market_data_refresh.stale_after_seconds",
            ),
        ],
    ),
    JobDescriptor(
        kind="snapshot_rebuild",
        category="scheduled",
        name_key="snapshotRebuild.name",
        description_key="snapshotRebuild.description",
        schedule_description_key="snapshotRebuild.scheduleDescription",
        schedule_readonly_reason_key=_READONLY_SCHEDULE_REASON_KEY,
        disable_warning_key="snapshotRebuild.disableWarning",
        parameters=[
            JobParameterSpec(
                label_key=_STALE_THRESHOLD_KEY,
                unit_key=_SECONDS_UNIT_KEY,
                editable=True,
                setting_key="job_health.snapshot_rebuild.stale_after_seconds",
            ),
        ],
    ),
    JobDescriptor(
        kind="stale_job_reaper",
        category="scheduled",
        name_key="staleJobReaper.name",
        description_key="staleJobReaper.description",
        schedule_description_key="staleJobReaper.scheduleDescription",
        schedule_readonly_reason_key=_READONLY_SCHEDULE_REASON_KEY,
        disable_warning_key="staleJobReaper.disableWarning",
        parameters=[
            JobParameterSpec(
                label_key="params.staleThresholdImport",
                unit_key=_SECONDS_UNIT_KEY,
                editable=True,
                setting_key="job_health.import.stale_after_seconds",
            ),
            JobParameterSpec(
                label_key="params.staleThresholdAiClassification",
                unit_key=_SECONDS_UNIT_KEY,
                editable=True,
                setting_key="job_health.ai_classification.stale_after_seconds",
            ),
            JobParameterSpec(
                label_key="params.staleThresholdMarketDataRefresh",
                unit_key=_SECONDS_UNIT_KEY,
                editable=True,
                setting_key="job_health.market_data_refresh.stale_after_seconds",
            ),
            JobParameterSpec(
                label_key="params.staleThresholdSnapshotRebuild",
                unit_key=_SECONDS_UNIT_KEY,
                editable=True,
                setting_key="job_health.snapshot_rebuild.stale_after_seconds",
            ),
            JobParameterSpec(
                label_key="params.staleThresholdGoogleSheetsExport",
                unit_key=_SECONDS_UNIT_KEY,
                editable=True,
                setting_key="job_health.google_sheets_export.stale_after_seconds",
            ),
        ],
    ),
    JobDescriptor(
        kind="import",
        category="triggered",
        name_key="import.name",
        description_key="import.description",
        parameters=[
            JobParameterSpec(
                label_key=_STALE_THRESHOLD_KEY,
                unit_key=_SECONDS_UNIT_KEY,
                editable=True,
                setting_key="job_health.import.stale_after_seconds",
            ),
            JobParameterSpec(
                label_key=_MAX_EXECUTION_TIMEOUT_KEY,
                unit_key=_SECONDS_UNIT_KEY,
                editable=False,
                settings_attr="import_job_timeout_seconds",
                readonly_reason_key=_READONLY_TIMEOUT_REASON_KEY,
            ),
            JobParameterSpec(
                label_key="params.pdfOpenTimeout",
                unit_key=_SECONDS_UNIT_KEY,
                editable=False,
                settings_attr="import_pdf_open_timeout_seconds",
                readonly_reason_key=_READONLY_TIMEOUT_REASON_KEY,
            ),
            JobParameterSpec(
                label_key="params.pdfParseTimeout",
                unit_key=_SECONDS_UNIT_KEY,
                editable=False,
                settings_attr="import_pdf_parse_timeout_seconds",
                readonly_reason_key=_READONLY_TIMEOUT_REASON_KEY,
            ),
        ],
    ),
    JobDescriptor(
        kind="ai_classification",
        category="triggered",
        name_key="aiClassification.name",
        description_key="aiClassification.description",
        parameters=[
            JobParameterSpec(
                label_key=_STALE_THRESHOLD_KEY,
                unit_key=_SECONDS_UNIT_KEY,
                editable=True,
                setting_key="job_health.ai_classification.stale_after_seconds",
            ),
            JobParameterSpec(
                label_key=_MAX_EXECUTION_TIMEOUT_KEY,
                unit_key=_SECONDS_UNIT_KEY,
                editable=False,
                settings_attr="ai_classification_job_timeout_seconds",
                readonly_reason_key=_READONLY_TIMEOUT_REASON_KEY,
            ),
            JobParameterSpec(
                label_key="params.aiCallTimeout",
                unit_key=_SECONDS_UNIT_KEY,
                editable=False,
                settings_attr="ai_classify_timeout_seconds",
                readonly_reason_key=_READONLY_TIMEOUT_REASON_KEY,
            ),
        ],
    ),
    JobDescriptor(
        kind="google_sheets_export",
        category="triggered",
        name_key="googleSheetsExport.name",
        description_key="googleSheetsExport.description",
        parameters=[
            JobParameterSpec(
                label_key=_STALE_THRESHOLD_KEY,
                unit_key=_SECONDS_UNIT_KEY,
                editable=True,
                setting_key="job_health.google_sheets_export.stale_after_seconds",
            ),
            JobParameterSpec(
                label_key=_MAX_EXECUTION_TIMEOUT_KEY,
                unit_key=_SECONDS_UNIT_KEY,
                editable=False,
                settings_attr="google_export_job_timeout_seconds",
                readonly_reason_key=_READONLY_TIMEOUT_REASON_KEY,
            ),
        ],
    ),
    JobDescriptor(
        kind="reclassification",
        category="triggered",
        name_key="reclassification.name",
        description_key="reclassification.description",
        parameters=[
            JobParameterSpec(
                label_key=_STALE_THRESHOLD_KEY,
                unit_key=_SECONDS_UNIT_KEY,
                editable=True,
                setting_key="job_health.reclassification.stale_after_seconds",
            ),
            JobParameterSpec(
                label_key=_MAX_EXECUTION_TIMEOUT_KEY,
                unit_key=_SECONDS_UNIT_KEY,
                editable=False,
                settings_attr="reclassification_job_timeout_seconds",
                readonly_reason_key=_READONLY_TIMEOUT_REASON_KEY,
            ),
        ],
    ),
    JobDescriptor(
        kind="snapshot_backfill",
        category="triggered",
        name_key="snapshotBackfill.name",
        description_key="snapshotBackfill.description",
        parameters=[
            JobParameterSpec(
                label_key=_STALE_THRESHOLD_KEY,
                unit_key=_SECONDS_UNIT_KEY,
                editable=True,
                setting_key="job_health.snapshot_backfill.stale_after_seconds",
            ),
            JobParameterSpec(
                label_key=_MAX_EXECUTION_TIMEOUT_KEY,
                unit_key=_SECONDS_UNIT_KEY,
                editable=False,
                settings_attr="snapshot_backfill_job_timeout_seconds",
                readonly_reason_key=_READONLY_TIMEOUT_REASON_KEY,
            ),
        ],
    ),
    JobDescriptor(
        kind="positions_recompute",
        category="triggered",
        name_key="positionsRecompute.name",
        description_key="positionsRecompute.description",
        parameters=[
            JobParameterSpec(
                label_key=_STALE_THRESHOLD_KEY,
                unit_key=_SECONDS_UNIT_KEY,
                editable=True,
                setting_key="job_health.positions_recompute.stale_after_seconds",
            ),
            JobParameterSpec(
                label_key=_MAX_EXECUTION_TIMEOUT_KEY,
                unit_key=_SECONDS_UNIT_KEY,
                editable=False,
                settings_attr="positions_recompute_job_timeout_seconds",
                readonly_reason_key=_READONLY_TIMEOUT_REASON_KEY,
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
        "label_key": spec.label_key,
        "unit_key": spec.unit_key,
        "editable": spec.editable,
        "setting_key": spec.setting_key,
        "value": value,
        "readonly_reason_key": spec.readonly_reason_key,
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
                "name_key": descriptor.name_key,
                "description_key": descriptor.description_key,
                "schedule_description_key": descriptor.schedule_description_key,
                "schedule_readonly_reason_key": descriptor.schedule_readonly_reason_key,
                "disable_warning_key": descriptor.disable_warning_key,
                "enabled": enabled,
                "enabled_setting_key": enabled_setting_key,
                "parameters": [await _resolve_parameter(p) for p in descriptor.parameters],
            }
        )
    return jobs
