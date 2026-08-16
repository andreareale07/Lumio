import csv
import hashlib
import io
import logging
import uuid
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_current_workspace_id
from app.core.config import get_settings
from app.db.session import get_db
from app.models.bank import Bank
from app.models.bank_parser import BankParser as BankParserRow
from app.models.financial_account import FinancialAccount
from app.models.import_ import Import
from app.models.import_mapping import ImportMapping
from app.models.investment_transaction import InvestmentTransaction
from app.models.transaction import Transaction
from app.models.user import User
from app.parsers import detect_parser
from app.schemas.imports import (
    ImportConfirmRequest,
    ImportDeleteResult,
    ImportFileContent,
    ImportMappingOut,
    ImportOut,
    ImportPreview,
    ImportTransactionsCountOut,
    ImportUploadResponse,
)
from app.services import job_events, upload_validation
from app.services.audit_log_service import log_event
from app.services.csv_import import MappingConfig, detect_mapping
from app.services.import_paths import import_dir_prefix, original_file_path
from app.services.position_service import recompute_position
from app.storage import get_storage
from app.worker.queue import enqueue_import_job

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/imports", tags=["imports"])


async def _get_import_or_404(db: AsyncSession, workspace_id: uuid.UUID, import_id: uuid.UUID) -> Import:
    import_row = await db.get(Import, import_id)
    # Come per accounts/transactions: la RLS gia' impedisce di leggere righe
    # di altri workspace, ma il controllo esplicito resta il primo livello
    # di isolamento richiesto da SPEC §7.
    if import_row is None or import_row.workspace_id != workspace_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Import not found")
    return import_row


async def _assert_account_in_workspace(
    db: AsyncSession, workspace_id: uuid.UUID, account_id: uuid.UUID
) -> None:
    account = await db.get(FinancialAccount, account_id)
    if account is None or account.workspace_id != workspace_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid financial_account_id")


def _extract_sample(
    text: str, mapping: MappingConfig, max_rows: int | None = 5
) -> tuple[list[str], list[list[str]]]:
    lines = text.splitlines()[mapping.skip_rows :]
    rows = list(csv.reader(io.StringIO("\n".join(lines)), delimiter=mapping.delimiter))
    if not rows:
        return [], []
    if max_rows is None:
        return rows[0], rows[1:]
    return rows[0], rows[1 : 1 + max_rows]


async def _abort_job_best_effort(job_id: str | None) -> None:
    """Ferma un job arq ancora IN CODA (mai uno gia' in esecuzione — arq non
    ha un meccanismo di interruzione per quelli, vedi commento su
    `delete_import` sotto). Chiamata da `cancel_import`/`delete_import` per il
    job di import (`import_row.job_id`) e da `delete_import` per il job di
    classificazione AI disaccoppiato (id fisso `ai_classification:{id}`,
    vedi `enqueue_classify_import_job`) quando ancora 'pending'."""
    if not job_id:
        return
    try:
        from arq.jobs import Job

        from app.worker.queue import get_arq_pool

        pool = await get_arq_pool()
        # timeout esplicito (mai None): senza, arq resta in attesa "per
        # sempre" di una conferma di risultato (vedi Job.abort docstring)
        # se nessun worker sta davvero eseguendo la coda in quel momento —
        # scoperto da un test reale che si bloccava indefinitamente. E'
        # comunque un'operazione best-effort: non ci serve la conferma, solo
        # segnalare l'abort e proseguire.
        await Job(job_id, pool).abort(timeout=1.0)
    except Exception:
        # Best-effort: la vera rete di sicurezza e' il controllo dello stato
        # ('queued'/'pending') fatto dal job stesso appena parte, vedi
        # import_job.py e ai_classification_job.py — se l'abort arq non
        # funziona, il job comunque non processa nulla trovando lo stato
        # cambiato (cancelled, o la riga import sparita).
        pass


def _referenced_columns(mapping: MappingConfig) -> list[str]:
    c = mapping.columns
    names = [c.transaction_date, c.description_raw]
    if mapping.amount_mode == "separate_debit_credit":
        names += [c.amount_debit, c.amount_credit]
    else:
        names.append(c.amount)
        if mapping.amount_mode == "single_absolute_with_direction":
            names.append(c.direction)
    names += [c.value_date, c.currency, c.reference, c.balance_after]
    return [n for n in names if n]


async def _resolve_suggested_mapping(
    db: AsyncSession, workspace_id: uuid.UUID, account_id: uuid.UUID, text_sample: str
) -> MappingConfig:
    # Decisione presa con l'utente: all'upload si propone la mappatura
    # dell'ultimo import RIUSCITO sullo stesso conto, se esiste; altrimenti
    # si ricade sull'euristica.
    result = await db.execute(
        select(Import.import_mapping_id)
        .where(
            Import.workspace_id == workspace_id,
            Import.financial_account_id == account_id,
            Import.status == "completed",
            Import.import_mapping_id.is_not(None),
        )
        .order_by(Import.completed_at.desc())
        .limit(1)
    )
    mapping_id = result.scalars().first()
    if mapping_id is not None:
        mapping_row = await db.get(ImportMapping, mapping_id)
        if mapping_row is not None:
            return MappingConfig(**mapping_row.config)
    return detect_mapping(text_sample)


async def _build_preview(
    db: AsyncSession, workspace_id: uuid.UUID, account_id: uuid.UUID, raw_bytes: bytes
) -> ImportPreview:
    text_sample = raw_bytes.decode("utf-8-sig", errors="replace")
    suggested = await _resolve_suggested_mapping(db, workspace_id, account_id, text_sample)
    columns, sample_rows = _extract_sample(text_sample, suggested)

    mappings_result = await db.execute(
        select(ImportMapping)
        .where(ImportMapping.workspace_id == workspace_id)
        .order_by(ImportMapping.updated_at.desc())
    )
    available = [ImportMappingOut.model_validate(m) for m in mappings_result.scalars().all()]

    return ImportPreview(
        columns=columns,
        sample_rows=sample_rows,
        suggested_mapping=suggested,
        available_mappings=available,
    )


async def _detect_bank_parser(db: AsyncSession, raw_bytes: bytes) -> tuple[Bank, BankParserRow]:
    """Rilevazione banca per il canale PDF (SPEC §42: stage "banca
    riconosciuta"). `banks`/`bank_parsers` non hanno RLS (entita' globali,
    vedi migration 0003/0005): nessun vincolo di ordine rispetto al commit
    della riga import qui, a differenza delle query su tabelle tenant-scoped.
    """
    parser = detect_parser(raw_bytes)
    if parser is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Banca non riconosciuta per questo PDF")

    bank_result = await db.execute(select(Bank).where(Bank.code == parser.bank_code))
    bank = bank_result.scalars().first()
    parser_row_result = await db.execute(
        select(BankParserRow).where(
            BankParserRow.bank_id == bank.id,
            BankParserRow.parser_type == parser.parser_type,
            BankParserRow.version == parser.version,
            BankParserRow.is_active.is_(True),
        )
    )
    bank_parser_row = parser_row_result.scalars().first()
    if bank is None or bank_parser_row is None:
        # Il parser e' registrato in app/parsers/__init__.py ma manca la riga
        # bank_parsers corrispondente (seed/migration disallineati) — non un
        # input utente invalido, ma comunque non un 500 silenzioso: l'import
        # PDF non puo' procedere in modo tracciabile senza questa riga.
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Parser riconosciuto ma non configurato (bank_parsers mancante)",
        )
    return bank, bank_parser_row


@router.post("", response_model=ImportUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_import(
    financial_account_id: uuid.UUID = Form(...),
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> ImportUploadResponse:
    await _assert_account_in_workspace(db, workspace_id, financial_account_id)

    settings = get_settings()
    raw_bytes, file_type = await upload_validation.read_and_validate_import_upload(
        file, settings.max_import_file_size_bytes, settings.import_pdf_open_timeout_seconds
    )
    filename = upload_validation.sanitize_filename(file.filename)
    file_hash = hashlib.sha256(raw_bytes).hexdigest()

    # Dedup applicativo "preventivo" (SPEC §58): risposta chiara e immediata
    # nel caso comune. La garanzia reale contro le race concorrenti e'
    # l'indice unico parziale sul DB (uq_imports_workspace_file_hash_active),
    # verificato nel blocco IntegrityError sotto. Stesso indice per entrambi
    # i canali: file_hash e' sull'intero contenuto, quindi un CSV e un PDF
    # non collidono mai per caso.
    existing = await db.execute(
        select(Import).where(
            Import.workspace_id == workspace_id,
            Import.file_hash == file_hash,
            Import.status.not_in(("failed", "cancelled")),
        )
    )
    existing_import = existing.scalars().first()
    if existing_import is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            {
                "detail": "Questo file risulta gia' importato in questo workspace",
                "existing_import_id": str(existing_import.id),
                "existing_status": existing_import.status,
            },
        )

    bank_id: uuid.UUID | None = None
    bank_parser_id: uuid.UUID | None = None
    if file_type == "csv":
        # Verifica di interpretabilita' come CSV PRIMA di creare la riga
        # import e scrivere su storage: un file non parsabile non deve
        # lasciare stato orfano da ripulire (SPEC §53 — non fidarsi che sia
        # davvero un CSV valido solo perche' ha passato il controllo binario).
        text_sample = raw_bytes.decode("utf-8-sig", errors="replace")
        try:
            detect_mapping(text_sample)
        except (ValueError, csv.Error, IndexError) as exc:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, "Impossibile interpretare il file come CSV"
            ) from exc
        preview = await _build_preview(db, workspace_id, financial_account_id, raw_bytes)
    else:
        bank, bank_parser_row = await _detect_bank_parser(db, raw_bytes)
        bank_id = bank.id
        bank_parser_id = bank_parser_row.id
        preview = ImportPreview(detected_bank_code=bank.code, detected_bank_name=bank.name)

    import_row = Import(
        workspace_id=workspace_id,
        financial_account_id=financial_account_id,
        created_by_user_id=user.id,
        status="uploaded",
        filename=filename,
        file_hash=file_hash,
        file_size=len(raw_bytes),
        file_type=file_type,
        bank_id=bank_id,
        bank_parser_id=bank_parser_id,
    )
    # La preview (branch csv sopra) si costruisce PRIMA del commit che crea
    # la riga import: interroga solo altri import/mappature gia' esistenti,
    # quindi non ha bisogno che questa riga esista ancora. Ordine importante
    # — non un dettaglio stilistico: `SET LOCAL app.current_user_id`
    # (impostato da get_current_user) vale solo per la transazione corrente e
    # scade al commit; una query RLS-dipendente sulla STESSA sessione dopo il
    # commit gira senza identita' impostata e le policy negano tutto (visto
    # empiricamente: `invalid input syntax for type uuid: ""`).
    db.add(import_row)
    try:
        await db.flush()
        await log_event(
            db, workspace_id, user.id, "IMPORT_CREATED", entity_type="import", entity_id=import_row.id
        )
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, "File gia' in fase di import (rilevato in concorrenza)"
        ) from exc

    get_storage().save(original_file_path(workspace_id, import_row.id, file_type), raw_bytes)

    return ImportUploadResponse(**{"import": import_row, "preview": preview})


@router.get("", response_model=list[ImportOut])
async def list_imports(
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
    status_filter: str | None = Query(default=None, alias="status"),
    financial_account_id: uuid.UUID | None = None,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[Import]:
    query = select(Import).where(Import.workspace_id == workspace_id)
    if status_filter is not None:
        query = query.where(Import.status == status_filter)
    if financial_account_id is not None:
        query = query.where(Import.financial_account_id == financial_account_id)
    query = query.order_by(Import.created_at.desc()).limit(limit).offset(offset)
    result = await db.execute(query)
    return list(result.scalars().all())


@router.get("/{import_id}", response_model=ImportOut)
async def get_import(
    import_id: uuid.UUID,
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> Import:
    return await _get_import_or_404(db, workspace_id, import_id)


@router.get("/{import_id}/preview", response_model=ImportPreview)
async def get_import_preview(
    import_id: uuid.UUID,
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> ImportPreview:
    import_row = await _get_import_or_404(db, workspace_id, import_id)
    if import_row.file_type == "pdf":
        bank = await db.get(Bank, import_row.bank_id) if import_row.bank_id else None
        return ImportPreview(
            detected_bank_code=bank.code if bank else None,
            detected_bank_name=bank.name if bank else None,
        )
    raw_bytes = get_storage().read(original_file_path(workspace_id, import_row.id, "csv"))
    return await _build_preview(db, workspace_id, import_row.financial_account_id, raw_bytes)


@router.post("/{import_id}/confirm", response_model=ImportOut)
async def confirm_import(
    import_id: uuid.UUID,
    payload: ImportConfirmRequest,
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> Import:
    import_row = await _get_import_or_404(db, workspace_id, import_id)
    if import_row.status != "uploaded":
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"Import in stato '{import_row.status}', non confermabile"
        )

    if import_row.file_type == "csv":
        # Invariante applicativa (era un model_validator sullo schema prima
        # che esistesse il canale pdf, per cui un body di conferma vuoto e'
        # legittimo — vedi ImportConfirmRequest): qui dipende da
        # import_row.file_type, che lo schema del payload non conosce.
        if (payload.import_mapping_id is None) == (payload.mapping is None):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "specificare esattamente uno tra import_mapping_id e mapping",
            )
        if payload.save_as and payload.import_mapping_id is not None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "save_as e' valido solo con una mappatura inline (mapping)",
            )

        if payload.import_mapping_id is not None:
            mapping_row = await db.get(ImportMapping, payload.import_mapping_id)
            if mapping_row is None or mapping_row.workspace_id != workspace_id:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Import mapping not found")
            mapping_config = MappingConfig(**mapping_row.config)
            import_row.import_mapping_id = mapping_row.id
        else:
            mapping_config = payload.mapping
            if payload.save_as:
                mapping_row = ImportMapping(
                    workspace_id=workspace_id,
                    financial_account_id=import_row.financial_account_id,
                    name=payload.save_as,
                    config=mapping_config.model_dump(mode="json"),
                )
                db.add(mapping_row)
                await db.flush()
                import_row.import_mapping_id = mapping_row.id

        raw_bytes = get_storage().read(original_file_path(workspace_id, import_row.id, "csv"))
        try:
            text = raw_bytes.decode(mapping_config.encoding, errors="strict")
        except (LookupError, UnicodeDecodeError) as exc:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                f"Encoding '{mapping_config.encoding}' non valido per il file",
            ) from exc

        header, _sample = _extract_sample(text, mapping_config, max_rows=0)
        missing = [name for name in _referenced_columns(mapping_config) if name not in header]
        if missing:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                f"Colonne mancanti nel file per la mappatura scelta: {', '.join(missing)}",
            )

        # Snapshot immutabile: indipendente da import_mapping_id, che punta a
        # una mappatura riusabile salvata (opzionale) — questo e' l'unico
        # posto da cui il worker recupera i parametri di parsing, anche
        # quando la mappatura era inline e mai salvata.
        import_row.mapping_config = mapping_config.model_dump(mode="json")
    # file_type == 'pdf': nessuna scelta di mappatura, bank_id/bank_parser_id
    # sono gia' stati risolti e salvati all'upload — si passa direttamente
    # all'accodamento del job.

    # Bug reale scoperto con un E2E su Docker reale (worker piu' rapido del
    # previsto): l'ordine "enqueue prima, poi commit di status='queued'"
    # apriva una finestra di corsa in cui il worker poteva dequeuare il job
    # e leggere ancora status='uploaded' dal DB (commit non ancora visibile),
    # facendolo abortire per sempre con "status=uploaded (non 'queued'),
    # skip" — l'import restava bloccato a 'queued' senza che nessuno lo
    # riprocessasse mai. Fix: il job_id e' deterministico
    # (f"import:{import_id}", vedi enqueue_import_job) quindi si puo'
    # calcolare e COMMITTARE lo stato PRIMA di accodare davvero il job su
    # Redis, eliminando la finestra di corsa alla radice invece di
    # restringerla soltanto.
    job_id = f"import:{import_row.id}"
    import_row.job_id = job_id
    import_row.status = "queued"
    await db.commit()

    await enqueue_import_job(import_row.id, import_row.created_by_user_id)

    await job_events.emit(
        import_row.id,
        "job.created",
        job_id=job_id,
        type="import",
        stage="queued",
        progress=0,
        message="Import in coda",
    )
    return import_row


@router.post("/{import_id}/cancel", response_model=ImportOut)
async def cancel_import(
    import_id: uuid.UUID,
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> Import:
    import_row = await _get_import_or_404(db, workspace_id, import_id)
    if import_row.status not in ("uploaded", "queued"):
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"Import in stato '{import_row.status}', non annullabile"
        )

    await _abort_job_best_effort(import_row.job_id)

    import_row.status = "cancelled"
    await db.commit()
    await job_events.emit(import_row.id, "job.cancelled", message="Import annullato dall'utente")
    return import_row


@router.get("/{import_id}/transactions-count", response_model=ImportTransactionsCountOut)
async def get_import_transactions_count(
    import_id: uuid.UUID,
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> ImportTransactionsCountOut:
    """Conteggio LIVE (non il contatore congelato `transactions_imported`,
    che non rifletterebbe eventuali eliminazioni singole successive via
    `DELETE /transactions/{id}`) — usato dal dialog di conferma eliminazione
    per mostrare l'impatto reale prima che l'utente confermi."""
    await _get_import_or_404(db, workspace_id, import_id)
    result = await db.execute(
        select(func.count())
        .select_from(Transaction)
        .where(Transaction.workspace_id == workspace_id, Transaction.import_id == import_id)
    )
    return ImportTransactionsCountOut(transactions_count=result.scalar_one())


@router.delete("/{import_id}", response_model=ImportDeleteResult)
async def delete_import(
    import_id: uuid.UUID,
    user: User = Depends(get_current_user),
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> ImportDeleteResult:
    """Eliminazione, con comportamento diverso per stato (deciso con
    l'utente dopo aver verificato cosa arq puo' davvero garantire):
    - uploaded/queued: nessuna transazione esiste ancora (il job non ha
      ancora scritto nulla) — si tenta di fermare il job in coda
      (`_abort_job_best_effort`, stesso meccanismo di `cancel_import`) e si
      procede subito con l'eliminazione.
    - processing/parsing: il job e' REALMENTE in esecuzione e arq non ha
      un modo affidabile di interromperlo a meta' (solo i job ancora in
      coda si possono abortire) — eliminare qui rischierebbe una corsa con
      scritture del worker ancora in corso. Rifiutato esplicitamente (409),
      mai un bottone silenziosamente assente: l'utente deve capire perche'
      deve aspettare.
    - completed/failed/cancelled: il job (se mai partito) e' certamente
      terminato — si cancellano le transazioni collegate e la riga import.

    Stesso principio si applica al job di classificazione AI disaccoppiato
    (`ai_classification_status`, vedi ai_classification_job.py), che scrive
    su QUESTE STESSE transazioni dopo che l'import e' gia' 'completed': se e'
    'running' e' REALMENTE in esecuzione (stessa impossibilita' di
    interromperlo a meta') — rifiutato con 409, mai una corsa silenziosa tra
    la sua scrittura e la DELETE. Se e' 'pending' (ancora in coda, non ha
    ancora toccato nulla) si tenta l'abort best-effort e si procede.
    """
    import_row = await _get_import_or_404(db, workspace_id, import_id)

    if import_row.status in ("processing", "parsing"):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Import in elaborazione: attendi il completamento prima di poterlo eliminare",
        )
    if import_row.ai_classification_status == "running":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Classificazione AI in corso: attendi il completamento prima di poterlo eliminare",
        )

    if import_row.status in ("uploaded", "queued"):
        await _abort_job_best_effort(import_row.job_id)
    if import_row.ai_classification_status == "pending":
        await _abort_job_best_effort(f"ai_classification:{import_row.id}")

    # Scoperto su dati reali (import PDF Trade Republic con
    # investment_transactions collegate via transaction_id, M09.5c): cancellare
    # a ritroso, MAI allargare i vincoli — le righe dipendenti vanno rimosse
    # (o scollegate, se non devono sparire) PRIMA della riga padre, cosi'
    # nessuna delete successiva viola mai un vincolo.
    #
    # `source_type_raw` distingue le due categorie (mai popolato da un
    # inserimento manuale, vedi commento su InvestmentTransactionCreate):
    # - auto-creato dal parser durante l'import (source_type_raw NOT NULL):
    #   e' conseguenza dell'import stesso — si cancella per intero, poi si
    #   ricalcola la posizione (asset, conto) coinvolta, stesso servizio
    #   usato da DELETE /investment-transactions/{id}.
    # - inserito/collegato a mano dall'utente (source_type_raw NULL): resta
    #   dato reale dell'utente, NON creato da questo import — si scollega
    #   solo il riferimento alla transazione in via di cancellazione, la riga
    #   stessa non si tocca.
    linked_result = await db.execute(
        select(InvestmentTransaction).where(
            InvestmentTransaction.workspace_id == workspace_id,
            InvestmentTransaction.transaction_id.in_(
                select(Transaction.id).where(
                    Transaction.workspace_id == workspace_id, Transaction.import_id == import_id
                )
            ),
        )
    )
    linked_investment_transactions = list(linked_result.scalars().all())

    positions_to_recompute: set[tuple[uuid.UUID, uuid.UUID, str]] = set()
    for investment_txn in linked_investment_transactions:
        if investment_txn.source_type_raw is not None:
            if investment_txn.asset_id is not None:
                positions_to_recompute.add(
                    (investment_txn.financial_account_id, investment_txn.asset_id, investment_txn.currency)
                )
            await db.delete(investment_txn)
        else:
            investment_txn.transaction_id = None
    await db.flush()

    for account_id, asset_id, currency in positions_to_recompute:
        await recompute_position(db, workspace_id, account_id, asset_id, currency)

    delete_result = await db.execute(
        delete(Transaction).where(
            Transaction.workspace_id == workspace_id, Transaction.import_id == import_id
        )
    )
    deleted_count = delete_result.rowcount

    await log_event(
        db,
        workspace_id,
        user.id,
        "IMPORT_DELETED",
        entity_type="import",
        entity_id=import_row.id,
        metadata={"deleted_transactions_count": deleted_count},
    )
    file_type = import_row.file_type
    await db.delete(import_row)
    await db.commit()

    # I dati finanziari nel DB sono la parte critica e sono gia' stati
    # eliminati con successo a questo punto — la rimozione del file su
    # storage e' un'operazione best-effort separata, MAI dentro la stessa
    # transazione DB (un filesystem non e' transazionale con Postgres: se il
    # commit sopra fallisse dopo aver gia' cancellato il file, resterebbe uno
    # stato inconsistente irreversibile; nel caso peggiore qui si lascia solo
    # un file orfano su disco, innocuo e pulibile a posteriori).
    try:
        get_storage().delete_prefix(import_dir_prefix(workspace_id, import_row.id))
    except Exception:
        logger.warning(
            "delete_import: impossibile rimuovere il file (%s) per import %s",
            file_type,
            import_row.id,
            exc_info=True,
        )

    return ImportDeleteResult(deleted_transactions_count=deleted_count)


@router.get("/{import_id}/file")
async def get_import_file(
    import_id: uuid.UUID,
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Bytes grezzi del file originale (PDF o CSV) — SOLO lettura,
    disponibile per qualunque stato (a differenza di DELETE, che e'
    distruttivo): il file esiste dal momento dell'upload e non si sposta
    finche' la riga import non viene eliminata."""
    import_row = await _get_import_or_404(db, workspace_id, import_id)
    path = original_file_path(workspace_id, import_row.id, import_row.file_type)
    try:
        raw_bytes = get_storage().read(path)
    except FileNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File originale non trovato su storage") from exc

    media_type = "application/pdf" if import_row.file_type == "pdf" else "text/csv"
    ascii_fallback = import_row.filename.encode("ascii", errors="replace").decode("ascii")
    return Response(
        content=raw_bytes,
        media_type=media_type,
        headers={
            "Content-Disposition": (
                f'inline; filename="{ascii_fallback}"; filename*=UTF-8\'\'{quote(import_row.filename)}'
            ),
            "Cache-Control": "private, no-store",
        },
    )


@router.get("/{import_id}/file-content", response_model=ImportFileContent)
async def get_import_file_content(
    import_id: uuid.UUID,
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> ImportFileContent:
    """Contenuto del CSV originale come tabella completa (non un campione
    come /preview, che serve invece a scegliere la mappatura prima della
    conferma) — pensato per il viewer, con un tetto di sicurezza sulla UI
    (`MAX_VIEWER_ROWS`), non sull'import: il file resta scaricabile per
    intero via /file indipendentemente da questo limite."""
    import_row = await _get_import_or_404(db, workspace_id, import_id)
    if import_row.file_type != "csv":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "file-content disponibile solo per import CSV")

    raw_bytes = get_storage().read(original_file_path(workspace_id, import_row.id, "csv"))
    mapping = (
        MappingConfig(**import_row.mapping_config)
        if import_row.mapping_config
        else detect_mapping(raw_bytes.decode("utf-8-sig", errors="replace"))
    )
    text = raw_bytes.decode(mapping.encoding, errors="replace")
    header, all_rows = _extract_sample(text, mapping, max_rows=None)

    MAX_VIEWER_ROWS = 2000
    return ImportFileContent(
        columns=header,
        rows=all_rows[:MAX_VIEWER_ROWS],
        truncated=len(all_rows) > MAX_VIEWER_ROWS,
        total_rows=len(all_rows),
    )


@router.get("/{import_id}/events")
async def stream_import_events(
    import_id: uuid.UUID,
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    # Autorizzato come ogni altro endpoint (bearer token + verifica
    # workspace): EventSource nativo non puo' inviare un header Authorization
    # e mettere il token in query string finirebbe nei log (SPEC §55), quindi
    # la UI futura user' fetch()+ReadableStream mantenendo l'header, non
    # EventSource — questo endpoint resta un normale endpoint protetto.
    import_row = await _get_import_or_404(db, workspace_id, import_id)
    return StreamingResponse(
        job_events.stream(import_row.id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/{import_id}/ai-classification-events")
async def stream_ai_classification_events(
    import_id: uuid.UUID,
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Mirror di /events, ma per il namespace 'ai_classification' (job
    disaccoppiato, vedi ai_classification_job.py) — stessa autenticazione,
    stesso motivo per cui non e' un EventSource nativo."""
    import_row = await _get_import_or_404(db, workspace_id, import_id)
    return StreamingResponse(
        job_events.stream(
            import_row.id,
            namespace="ai_classification",
            timeout_seconds=get_settings().ai_classification_job_timeout_seconds,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
