import dataclasses
import logging
import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import case, func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_current_workspace_id
from app.db.session import get_db
from app.models.category import Category
from app.models.classification import Classification
from app.models.financial_account import FinancialAccount
from app.models.import_ import Import
from app.models.open_banking import BankTransactionTombstone
from app.models.transaction import Transaction
from app.models.user import User
from app.schemas.transactions import (
    ClassificationOut,
    TransactionCreate,
    TransactionListSummaryOut,
    TransactionMerchantOut,
    TransactionMerchantsOut,
    TransactionOut,
    TransactionReviewSummaryOut,
    TransactionUpdate,
)
from app.services import analytics as analytics_service
from app.services import fx_rate_service
from app.services.audit_log_service import log_event
from app.services.confidence import needs_review as score_needs_review
from app.services.csv_import import collapse_whitespace
from app.services.rule_loader import load_active_rule_specs
from app.services.rules_engine import Probe, evaluate
from app.services.system_settings_service import get_setting_value
from app.services.transaction_dedup import compute_dedup_fingerprint
from app.worker.queue import enqueue_snapshot_backfill

logger = logging.getLogger("lumio.transactions")

router = APIRouter(prefix="/transactions", tags=["transactions"])

_NEEDS_REVIEW_THRESHOLD_KEY = "classification.needs_review_threshold"


def _is_pending_review(transaction: type[Transaction] = Transaction):
    """SPEC §43 ("319 classificati, 8 da verificare"): "da verificare" copre
    sia le transazioni classificate ma incerte (`needs_review=True`) sia
    quelle mai classificate (`category_id IS NULL`, es. rimaste indietro
    perche' il job AI e' stato interrotto) — entrambe meritano un secondo
    sguardo dell'utente, anche se per motivi diversi. Unica definizione,
    condivisa tra il filtro della lista e il conteggio di riepilogo: usarne
    due diverse (bug reale) fa si' che il badge mostri un numero che la
    lista filtrata non trova mai."""
    return or_(transaction.needs_review.is_(True), transaction.category_id.is_(None))


async def _get_transaction_or_404(
    db: AsyncSession, workspace_id: uuid.UUID, transaction_id: uuid.UUID
) -> Transaction:
    transaction = await db.get(Transaction, transaction_id)
    if transaction is None or transaction.workspace_id != workspace_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Transaction not found")
    return transaction


async def _assert_account_in_workspace(
    db: AsyncSession, workspace_id: uuid.UUID, account_id: uuid.UUID
) -> None:
    account = await db.get(FinancialAccount, account_id)
    if account is None or account.workspace_id != workspace_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid financial_account_id")


@router.post("", response_model=TransactionOut, status_code=status.HTTP_201_CREATED)
async def create_transaction(
    payload: TransactionCreate,
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> Transaction:
    await _assert_account_in_workspace(db, workspace_id, payload.financial_account_id)
    data = payload.model_dump()

    # Transaction Deduplication Engine (docs/SPEC_DEDUP_TRANSACTION.md):
    # description_normalized non e' un campo di TransactionCreate (l'utente
    # non lo compila a mano) ma deve SEMPRE essere valorizzata — e' un
    # input del fingerprint, e il fallback a description_raw dentro
    # compute_dedup_fingerprint e' pensato solo per dati legacy/backfill,
    # mai per una riga creata da qui in avanti.
    data["description_normalized"] = collapse_whitespace(data["description_raw"])
    data["dedup_fingerprint"] = compute_dedup_fingerprint(
        workspace_id=workspace_id,
        financial_account_id=data["financial_account_id"],
        transaction_date=data["transaction_date"],
        amount=data["amount"],
        currency=data["currency"],
        description_normalized=data["description_normalized"],
        description_raw=data["description_raw"],
        transaction_type=data["transaction_type"],
    )

    # Se il chiamante non fornisce esplicitamente una categoria, prova il
    # motore regole (SPEC §23: prima di qualsiasi AI, che in M06 non esiste
    # ancora). Se il chiamante la fornisce, e' una classificazione 'manual'
    # (SPEC §24) — nessuna riga di storico se resta non classificata.
    classification_method: str | None = "manual" if data["category_id"] is not None else None
    if classification_method is None:
        active_rules = await load_active_rule_specs(db, workspace_id)
        probe = Probe(
            description_raw=data["description_raw"],
            description_normalized=None,
            merchant=data["merchant"],
            amount=data["amount"],
        )
        matched_category_id = evaluate(active_rules, probe)
        if matched_category_id is not None:
            data["category_id"] = matched_category_id
            classification_method = "rule"

    transaction = Transaction(workspace_id=workspace_id, **data)
    db.add(transaction)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid category_id") from exc

    if classification_method is not None:
        score = Decimal("1.00") if classification_method == "rule" else None
        # 'manual' (l'utente ha scelto la categoria alla creazione): mai da
        # verificare, non ha senso segnalare come incerta una scelta
        # dell'utente stesso. 'rule': punteggio fisso 1.00, sotto qualunque
        # soglia sensata, ma il confronto resta esplicito per coerenza con
        # gli altri scrittori.
        transaction.needs_review = (
            False
            if classification_method == "manual"
            else score_needs_review(score, float(await get_setting_value(_NEEDS_REVIEW_THRESHOLD_KEY, 0.6)))
        )
        db.add(
            Classification(
                transaction_id=transaction.id,
                method=classification_method,
                category_id=transaction.category_id,
                score=score,
            )
        )

    await db.commit()
    return transaction


@dataclass
class TransactionListFilters:
    """Filtri condivisi tra la lista e il riepilogo (`/summary`): un'unica
    definizione, cosi' il conteggio/totale mostrato sopra la lista corrisponde
    sempre alle righe che la lista restituisce."""

    # Liste: un filtro con piu' valori e' un OR sui valori (selezione multipla
    # nella barra filtri); un solo valore resta compatibile con i chiamanti
    # che passano `?category_id=...` singolo.
    financial_account_id: list[uuid.UUID] = dataclasses.field(default_factory=list)
    category_id: list[uuid.UUID] = dataclasses.field(default_factory=list)
    transaction_type: list[str] = dataclasses.field(default_factory=list)
    date_from: date | None = None
    date_to: date | None = None
    needs_review: bool | None = None
    import_id: uuid.UUID | None = None
    merchant: list[str] = dataclasses.field(default_factory=list)
    no_merchant: bool = False
    q: str | None = None


def list_filters(
    financial_account_id: list[uuid.UUID] | None = Query(default=None),
    category_id: list[uuid.UUID] | None = Query(default=None),
    transaction_type: list[str] | None = Query(default=None),
    date_from: date | None = None,
    date_to: date | None = None,
    needs_review: bool | None = None,
    import_id: uuid.UUID | None = None,
    merchant: list[str] | None = Query(default=None),
    no_merchant: bool = False,
    q: str | None = Query(default=None, max_length=200),
) -> TransactionListFilters:
    return TransactionListFilters(
        financial_account_id or [],
        category_id or [],
        transaction_type or [],
        date_from,
        date_to,
        needs_review,
        import_id,
        merchant or [],
        no_merchant,
        q,
    )


def _apply_list_filters(query, workspace_id: uuid.UUID, f: TransactionListFilters):
    query = query.where(Transaction.workspace_id == workspace_id)
    needle = (f.q or "").strip()
    if needle:
        # Ricerca testuale libera (ILIKE, case-insensitive) su descrizione
        # originale, merchant, controparte e riferimento. `%`/`_` dell'utente
        # sono escapati: la ricerca e' sempre "contiene", mai un pattern.
        escaped = needle.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{escaped}%"
        query = query.where(
            or_(
                Transaction.description_raw.ilike(pattern, escape="\\"),
                Transaction.merchant.ilike(pattern, escape="\\"),
                Transaction.counterparty_name.ilike(pattern, escape="\\"),
                Transaction.reference.ilike(pattern, escape="\\"),
            )
        )
    if f.no_merchant and f.merchant:
        query = query.where(or_(Transaction.merchant.is_(None), Transaction.merchant.in_(f.merchant)))
    elif f.no_merchant:
        query = query.where(Transaction.merchant.is_(None))
    elif f.merchant:
        query = query.where(Transaction.merchant.in_(f.merchant))
    if f.financial_account_id:
        query = query.where(Transaction.financial_account_id.in_(f.financial_account_id))
    if f.needs_review is True:
        query = query.where(_is_pending_review())
    elif f.needs_review is False:
        query = query.where(~_is_pending_review())
    if f.import_id is not None:
        query = query.where(Transaction.import_id == f.import_id)
    if f.category_id:
        # Match padre-O-figlio, non solo esatto: `category_id` qui e' spesso
        # un group_id riaccorpato (come in analytics.by_merchant, stesso
        # pattern) — puo' essere una categoria padre, e le transazioni sono
        # taggate con la SOTTOCATEGORIA figlia, non col padre stesso. Senza
        # questo, un link "vedi le transazioni di Trasporti" da una futura
        # pagina di dettaglio KPI restituirebbe sempre una lista vuota (bug
        # gia' risolto in by_merchant, qui replicato).
        query = query.outerjoin(Category, Transaction.category_id == Category.id).where(
            or_(Transaction.category_id.in_(f.category_id), Category.parent_id.in_(f.category_id))
        )
    if f.transaction_type:
        query = query.where(Transaction.transaction_type.in_(f.transaction_type))
    if f.date_from is not None:
        query = query.where(Transaction.transaction_date >= f.date_from)
    if f.date_to is not None:
        query = query.where(Transaction.transaction_date <= f.date_to)
    return query


@router.get("", response_model=list[TransactionOut])
async def list_transactions(
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
    filters: TransactionListFilters = Depends(list_filters),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[Transaction]:
    query = _apply_list_filters(select(Transaction), workspace_id, filters)
    query = query.order_by(Transaction.transaction_date.desc()).limit(limit).offset(offset)
    result = await db.execute(query)
    return list(result.scalars().all())


@router.get("/summary", response_model=TransactionListSummaryOut)
async def get_transaction_list_summary(
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
    filters: TransactionListFilters = Depends(list_filters),
) -> TransactionListSummaryOut:
    """Riepilogo delle righe che la lista restituirebbe con gli stessi filtri
    (conteggio + entrate/uscite). Come per i flussi di cassa, trasferimenti
    interni e investimenti non contano come entrata/uscita (regola 6:
    un trasferimento non e' mai spesa ne' entrata), ma restano nel conteggio.
    Gli importi sono convertiti nella valuta base del workspace."""
    currency = await analytics_service.resolve_currency(db, workspace_id, None)
    fx_rate = fx_rate_service.fx_rate_expr(Transaction.currency, Transaction.transaction_date, currency)
    converted = Transaction.amount * fx_rate
    counted = Transaction.transaction_type.notin_(("transfer", "investment"))
    filtered = _apply_list_filters(select(Transaction.id, converted.label("converted"), counted.label("counted")), workspace_id, filters).subquery()
    row = (
        await db.execute(
            select(
                func.count(),
                func.coalesce(func.sum(case((filtered.c.counted & (filtered.c.converted > 0), filtered.c.converted), else_=0)), 0),
                func.coalesce(-func.sum(case((filtered.c.counted & (filtered.c.converted < 0), filtered.c.converted), else_=0)), 0),
            ).select_from(filtered)
        )
    ).one()
    cents = Decimal("0.01")
    income = Decimal(row[1]).quantize(cents)
    expenses = Decimal(row[2]).quantize(cents)
    return TransactionListSummaryOut(
        count=row[0], currency=currency, income=income, expenses=expenses, net=income - expenses
    )


@router.get("/merchants", response_model=TransactionMerchantsOut)
async def list_transaction_merchants(
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
    q: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=10, ge=1, le=50),
) -> TransactionMerchantsOut:
    """Merchant del workspace con il numero di movimenti, dal piu' frequente:
    alimenta il selettore del filtro merchant (con centinaia di valori non si
    scarica l'elenco intero, si mostrano i piu' frequenti e si cerca sul
    server). `total` = quanti merchant corrispondono alla ricerca, per dire
    "10 su 412"."""
    base = select(Transaction.merchant, func.count().label("n")).where(
        Transaction.workspace_id == workspace_id, Transaction.merchant.is_not(None)
    )
    needle = (q or "").strip()
    if needle:
        escaped = needle.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        base = base.where(Transaction.merchant.ilike(f"%{escaped}%", escape="\\"))
    grouped = base.group_by(Transaction.merchant)
    rows = (await db.execute(grouped.order_by(func.count().desc(), Transaction.merchant).limit(limit))).all()
    total = (await db.execute(select(func.count()).select_from(grouped.subquery()))).scalar_one()
    return TransactionMerchantsOut(
        items=[TransactionMerchantOut(merchant=r.merchant, count=r.n) for r in rows], total=total
    )


@router.get("/review-summary", response_model=TransactionReviewSummaryOut)
async def get_transaction_review_summary(
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
    financial_account_id: uuid.UUID | None = None,
    import_id: uuid.UUID | None = None,
) -> TransactionReviewSummaryOut:
    """SPEC §43 ("319 classificati, 8 da verificare"): 'risolta' = ha una
    categoria assegnata E non e' `needs_review` — 'da verificare' e' il
    complemento (include sia le incerte sia le mai classificate, entrambe
    meritano un secondo sguardo dell'utente, per motivi diversi). Nessuna
    riga trasferita al client solo per contare: aggregazione lato DB."""
    base_query = select(Transaction).where(Transaction.workspace_id == workspace_id)
    if financial_account_id is not None:
        base_query = base_query.where(Transaction.financial_account_id == financial_account_id)
    if import_id is not None:
        base_query = base_query.where(Transaction.import_id == import_id)

    total_result = await db.execute(select(func.count()).select_from(base_query.subquery()))
    total = total_result.scalar_one()

    pending_query = base_query.where(_is_pending_review())
    pending_result = await db.execute(select(func.count()).select_from(pending_query.subquery()))
    pending = pending_result.scalar_one()

    return TransactionReviewSummaryOut(total=total, classified=total - pending, needs_review=pending)


@router.get("/{transaction_id}", response_model=TransactionOut)
async def get_transaction(
    transaction_id: uuid.UUID,
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> Transaction:
    return await _get_transaction_or_404(db, workspace_id, transaction_id)


@router.patch("/{transaction_id}", response_model=TransactionOut)
async def update_transaction(
    transaction_id: uuid.UUID,
    payload: TransactionUpdate,
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Transaction:
    transaction = await _get_transaction_or_404(db, workspace_id, transaction_id)
    updates = payload.model_dump(exclude_unset=True)
    # Una modifica esplicita di category_id e' una correzione (SPEC §24,
    # method='user'): e' lo storico da cui parte la proposta di regola
    # automatica dopo correzioni ripetute (SPEC §29, vedi /rules/suggestions).
    category_corrected = "category_id" in updates and updates["category_id"] != transaction.category_id
    # Campi di identita' del fingerprint esposti da TransactionUpdate
    # (amount/currency/financial_account_id non sono modificabili da questo
    # endpoint): se uno di questi cambia, il dedup_fingerprint persistito
    # resterebbe stale rispetto al contenuto reale della transazione,
    # producendo falsi (non-)match nei futuri import — vedi
    # docs/SPEC_DEDUP_TRANSACTION.md e il piano approvato.
    fingerprint_fields = {"transaction_date", "description_normalized", "transaction_type"}
    identity_changed = bool(fingerprint_fields & updates.keys())
    for field, value in updates.items():
        setattr(transaction, field, value)

    if identity_changed:
        transaction.dedup_fingerprint = compute_dedup_fingerprint(
            workspace_id=transaction.workspace_id,
            financial_account_id=transaction.financial_account_id,
            transaction_date=transaction.transaction_date,
            amount=transaction.amount,
            currency=transaction.currency,
            description_normalized=transaction.description_normalized,
            description_raw=transaction.description_raw,
            transaction_type=transaction.transaction_type,
        )

    if category_corrected:
        # Una correzione manuale chiude SEMPRE la review, incondizionatamente
        # (non un confronto con la soglia: l'utente ha gia' deciso, non c'e'
        # altro da verificare) — indipendentemente da cosa l'aveva sollevata
        # in precedenza (AI incerta, o una riga poi reclassificata).
        transaction.needs_review = False
        db.add(
            Classification(
                transaction_id=transaction.id,
                method="user",
                category_id=transaction.category_id,
                created_by_user_id=user.id,
            )
        )

    if updates:
        await log_event(
            db, workspace_id, user.id, "TRANSACTION_UPDATED", entity_type="transaction", entity_id=transaction.id
        )

    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid category_id") from exc
    return transaction


@router.delete("/{transaction_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_transaction(
    transaction_id: uuid.UUID,
    user: User = Depends(get_current_user),
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> None:
    transaction = await _get_transaction_or_404(db, workspace_id, transaction_id)
    if transaction.external_id and transaction.import_id is not None:
        # Movimento arrivato da Open Banking eliminato a mano: la finestra di
        # sovrapposizione della sync lo riporterebbe indietro. Tombstone minima.
        file_type = await db.scalar(
            select(Import.file_type).where(Import.workspace_id == workspace_id, Import.id == transaction.import_id)
        )
        if file_type == "open_banking":
            await db.execute(
                pg_insert(BankTransactionTombstone)
                .values(
                    workspace_id=workspace_id,
                    financial_account_id=transaction.financial_account_id,
                    external_id=transaction.external_id,
                )
                .on_conflict_do_nothing(constraint="uq_bank_transaction_tombstones_account_ext")
            )
    transaction_date = transaction.transaction_date
    await db.delete(transaction)
    await db.commit()
    # Lo storico del patrimonio dipende dai movimenti: va ricostruito dalla data di quello
    # eliminato. Un problema della coda non deve far fallire l'eliminazione, gia' avvenuta.
    try:
        await enqueue_snapshot_backfill(workspace_id, user.id, date_from=transaction_date)
    except Exception:
        logger.warning("delete_transaction: backfill dello storico non accodato", exc_info=True)


@router.get("/{transaction_id}/classifications", response_model=list[ClassificationOut])
async def list_transaction_classifications(
    transaction_id: uuid.UUID,
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> list[Classification]:
    await _get_transaction_or_404(db, workspace_id, transaction_id)
    result = await db.execute(
        select(Classification)
        .where(Classification.transaction_id == transaction_id)
        .order_by(Classification.created_at.desc())
    )
    return list(result.scalars().all())
