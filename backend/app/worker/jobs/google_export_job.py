"""Job arq per l'export Google Sheets (milestone 10) — CLAUDE.md: "operazioni
lunghe (... export ...) sempre job async via Redis/worker + eventi SSE/
WebSocket", stesso principio gia' applicato all'Import Engine.

Combina i due meccanismi di stato gia' esistenti nel progetto, finora usati
separatamente: `tracked_job_run` (stato persistente "ultimo export",
sopravvive al refresh pagina, come `market_data_refresh`) E `job_events`
(progresso live via SSE, come l'import) — l'export e' l'unico job che
giustifica entrambi: e' abbastanza raro da meritare un pulsante dedicato
con stato persistente, ma abbastanza lungo (chiamate multiple a Google) da
meritare un progresso in tempo reale invece di un semplice "in corso".
"""
import logging
import uuid
from datetime import date

from app.db.rls import rls_session
from app.integrations.google.errors import GoogleAPIError, GoogleReauthRequiredError
from app.integrations.google.report_builder import ReportOptions, build_report
from app.integrations.google.sheets_client import batch_update, list_charts, write_values
from app.services import job_events
from app.services.google_integration_service import get_integration, get_valid_access_token, mark_exported
from app.services.job_run_tracker import tracked_job_run

logger = logging.getLogger("lumio.worker.google_export_job")

JOB_KIND = "google_sheets_export"
NAMESPACE = "google_export"


def _restore_chart_positions(requests: list[dict], positions_by_title: dict[str, dict]) -> list[dict]:
    """Riscrive la `position` di ogni richiesta `addChart` con quella
    salvata (se un grafico con lo stesso titolo esisteva gia' prima della
    cancellazione), altrimenti lascia l'ancoraggio di default deciso da
    `report_builder`. Il titolo e' l'unico identificatore stabile tra un
    export e il successivo — nessun chart ID persistito lato Lumio, si
    rilegge sempre lo stato reale dello spreadsheet."""
    for req in requests:
        chart = req.get("addChart", {}).get("chart")
        if not chart:
            continue
        title = chart.get("spec", {}).get("title")
        saved_position = positions_by_title.get(title)
        if saved_position:
            chart["position"] = saved_position
    return requests


async def google_sheets_export_job(ctx, workspace_id: str, user_id: str, options: dict) -> None:
    ws_id = uuid.UUID(workspace_id)
    uid = uuid.UUID(user_id)
    report_options = ReportOptions(
        date_from=date.fromisoformat(options["date_from"]),
        date_to=date.fromisoformat(options["date_to"]),
        include_portfolio=options.get("include_portfolio"),
        include_charts=options.get("include_charts", True),
    )

    await job_events.emit(ws_id, "job.started", namespace=NAMESPACE, stage="preparazione", progress=10)
    message = "Impossibile completare l'export su Google Sheets"
    try:
        async with tracked_job_run(ws_id, uid, JOB_KIND) as run:
            async with rls_session(uid) as db:
                integration = await get_integration(db, ws_id)
                if integration is None:
                    raise GoogleAPIError("Integrazione Google non trovata: connettiti di nuovo")

                await job_events.emit(
                    ws_id, "job.progress", namespace=NAMESPACE, stage="calcolo dei dati", progress=30
                )
                content = await build_report(db, ws_id, report_options)

                access_token = await get_valid_access_token(db, integration)

                await job_events.emit(
                    ws_id, "job.progress", namespace=NAMESPACE, stage="scrittura su Google Sheets", progress=60
                )
                await write_values(access_token, integration.spreadsheet_id, content.value_ranges)

                # `addChart` non e' idempotente (crea sempre un grafico NUOVO,
                # a differenza della scrittura valori che sovrascrive le
                # stesse celle): senza questo passaggio ogni export
                # accumulerebbe grafici duplicati invece di aggiornarli.
                # Prima di cancellarli, si salva la posizione di ognuno per
                # titolo — se l'utente ha spostato manualmente un grafico nel
                # foglio (per un layout piu' ordinato), quella posizione
                # sopravvive al prossimo export invece di tornare sempre
                # all'ancoraggio di default scelto dal report builder.
                existing_charts = await list_charts(access_token, integration.spreadsheet_id)
                if existing_charts:
                    await batch_update(
                        access_token,
                        integration.spreadsheet_id,
                        [{"deleteEmbeddedObject": {"objectId": c["chart_id"]}} for c in existing_charts],
                    )
                positions_by_title = {
                    c["title"]: c["position"] for c in existing_charts if c.get("title") and c.get("position")
                }
                requests = _restore_chart_positions(content.requests, positions_by_title)
                await batch_update(access_token, integration.spreadsheet_id, requests)

                await mark_exported(db, integration)
            run.message = f"Export completato: {len(content.sheet_titles)} fogli aggiornati"
        await job_events.emit(ws_id, "job.completed", namespace=NAMESPACE, message=run.message)
    except GoogleReauthRequiredError:
        logger.warning("export Google Sheets fallito per workspace %s: riautenticazione necessaria", workspace_id)
        await job_events.emit(
            ws_id,
            "job.failed",
            namespace=NAMESPACE,
            message="L'accesso a Google è stato revocato: è necessario riconnettersi",
        )
    except Exception:
        logger.exception("export Google Sheets fallito per workspace %s", workspace_id)
        await job_events.emit(ws_id, "job.failed", namespace=NAMESPACE, message=message)
        # Non ri-solleva (stesso principio di import_job.py): lo stato e'
        # gia' persistito da tracked_job_run + evento emesso, un retry
        # automatico di arq non aiuterebbe su un errore di configurazione/
        # quota che si ripeterebbe identico.
