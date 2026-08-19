"""Transaction Deduplication Engine (docs/SPEC_DEDUP_TRANSACTION.md).

Fingerprint deterministico + occurrence matching, scoped per
workspace+account, senza dipendenza dall'AI. Principio non negoziabile
(SPEC §3/§14): un fingerprint uguale NON implica automaticamente
"duplicato" — il matching e' per OCCORRENZE (§11), e i casi ambigui restano
in REVIEW, mai risolti automaticamente come duplicati.

Pipeline dell'algoritmo (una sola query aggregata per fase, mai un confronto
riga-per-riga contro l'intera tabella — SPEC §12):

1. fingerprint per ogni riga del batch (puro, in Python);
2. occorrenze esistenti per fingerprint (query aggregata indicizzata,
   `ix_transactions_workspace_account_fingerprint`) -> DUPLICATE per
   min(esistenti, nuove) occorrenze;
3. per le righe rimanenti, ricerca del "core key" (senza descrizione, indice
   `ix_transactions_dedup_core_key`) -> REVIEW se esiste un candidato con
   descrizione diversa, altrimenti NEW;
4. se esiste una decisione utente persistita per la coppia (candidato,
   nuovo fingerprint), la si applica automaticamente invece di riproporre
   la REVIEW (SPEC §17).
"""
from __future__ import annotations

import hashlib
import json
import logging
import unicodedata
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Literal, Protocol

from sqlalchemy import func, select, text, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.transaction import Transaction
from app.models.transaction_dedup_decision import TransactionDedupDecision

logger = logging.getLogger("lumio.dedup")

DedupOutcome = Literal["new", "duplicate", "review"]


class DedupCandidateRow(Protocol):
    """Contratto minimo su cui gira l'algoritmo: sia `ParsedRow`
    (app/services/csv_import.py) sia `TransactionReviewItem` lo soddisfano
    senza adapter — nessuna dipendenza diretta dal canale di import."""

    transaction_date: date
    amount: Decimal
    currency: str
    description_normalized: str | None
    description_raw: str
    transaction_type: str
    balance_after: Decimal | None


def canonical_description_for_fingerprint(text_value: str) -> str:
    """Normalizzazione CONSERVATIVA dedicata al fingerprint (SPEC §8): NFKC +
    trim + lowercase + collasso whitespace. Mai rimozione di numeri/codici —
    diverso (e in aggiunta a) `description_normalized`, che oggi e' solo
    whitespace-collapse (vedi app/services/csv_import.py)."""
    normalized = unicodedata.normalize("NFKC", text_value)
    return " ".join(normalized.strip().lower().split())


def canonical_amount_str(amount: Decimal) -> str:
    """Rappresentazione decimale deterministica per il payload del
    fingerprint — mai float, mai notazione scientifica (SPEC §5)."""
    return format(amount.quantize(Decimal("0.01")), "f")


def canonical_amount_decimal(amount: Decimal) -> Decimal:
    return amount.quantize(Decimal("0.01"))


def compute_dedup_fingerprint(
    *,
    workspace_id: uuid.UUID,
    financial_account_id: uuid.UUID,
    transaction_date: date,
    amount: Decimal,
    currency: str,
    description_normalized: str | None,
    description_raw: str,
    transaction_type: str,
) -> str:
    """SHA-256 di un payload JSON canonico (evita ambiguita' di
    concatenazione, SPEC §5) sui campi di identita' (SPEC §4).

    `description_normalized` DEVE essere sempre valorizzata da ogni percorso
    di scrittura nuovo (import, creazione manuale, modifica) — vedi
    `app/api/v1/transactions.py` e `app/worker/jobs/import_job.py`. Il
    fallback a `description_raw` qui sotto e' ESCLUSIVAMENTE compatibilita'
    per dati legacy/inconsistenti (righe storiche precedenti a questo
    motore, o il backfill della migration 0033): se viene raggiunto fuori da
    quei due casi e' un bug da correggere, non un comportamento normale —
    per questo emette un warning esplicito invece di restare silenzioso.
    """
    description_source = description_normalized
    if description_source is None:
        logger.warning(
            "compute_dedup_fingerprint: description_normalized assente, fallback a "
            "description_raw (previsto solo per dati legacy/backfill, mai per scritture nuove)"
        )
        description_source = description_raw
    canonical_desc = canonical_description_for_fingerprint(description_source)
    payload = json.dumps(
        [
            str(workspace_id),
            str(financial_account_id),
            transaction_date.isoformat(),
            canonical_amount_str(amount),
            currency.strip().upper(),
            canonical_desc,
            transaction_type,
        ],
        ensure_ascii=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def core_key_of(row: DedupCandidateRow) -> tuple[date, Decimal, str, str]:
    """Identita' SENZA descrizione (SPEC §11): usata solo per trovare
    candidati REVIEW quando il fingerprint esatto non matcha nulla."""
    return (
        row.transaction_date,
        canonical_amount_decimal(row.amount),
        row.currency.strip().upper(),
        row.transaction_type,
    )


@dataclass
class RowDedupOutcome:
    index: int
    fingerprint: str
    outcome: DedupOutcome
    candidate_existing_transaction_id: uuid.UUID | None = None
    auto_resolved: bool = False
    dedup_decision_id: uuid.UUID | None = None


@dataclass
class DedupBatchResult:
    outcomes: list[RowDedupOutcome]
    new_count: int
    duplicate_count: int
    review_count: int


@dataclass
class _CoreKeyCandidate:
    id: uuid.UUID
    dedup_fingerprint: str
    balance_after: Decimal | None
    created_at: object


async def _lock_account_for_dedup(
    db: AsyncSession, workspace_id: uuid.UUID, financial_account_id: uuid.UUID
) -> None:
    """Serializza import concorrenti sullo STESSO account (SPEC §29): lock
    xact-scoped (rilasciato automaticamente al commit/rollback), valido
    perche' conteggi + insert restano sempre nella stessa transazione DB del
    chiamante (un solo commit, vedi import_job.py). Account diversi non si
    bloccano a vicenda: la chiave del lock include sempre entrambi gli id.

    Nota accettata: `hashtextextended` puo' in teoria far collidere due
    coppie (workspace,account) diverse sulla stessa chiave a 64 bit — solo
    una perdita di parallelismo (si serializzano import che non avrebbero
    dovuto attendersi a vicenda), mai un falso match: le query di conteggio
    restano sempre filtrate sui veri workspace_id/financial_account_id.
    """
    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))"),
        {"lock_key": f"{workspace_id}:{financial_account_id}"},
    )


async def _fetch_core_key_candidates(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    financial_account_id: uuid.UUID,
    keys: list[tuple[date, Decimal, str, str]],
) -> dict[tuple[date, Decimal, str, str], list[_CoreKeyCandidate]]:
    if not keys:
        return {}
    result = await db.execute(
        select(
            Transaction.id,
            Transaction.dedup_fingerprint,
            Transaction.balance_after,
            Transaction.created_at,
            Transaction.transaction_date,
            Transaction.amount,
            Transaction.currency,
            Transaction.transaction_type,
        ).where(
            Transaction.workspace_id == workspace_id,
            Transaction.financial_account_id == financial_account_id,
            tuple_(
                Transaction.transaction_date,
                Transaction.amount,
                func.upper(Transaction.currency),
                Transaction.transaction_type,
            ).in_(keys),
        )
    )
    grouped: dict[tuple[date, Decimal, str, str], list[_CoreKeyCandidate]] = defaultdict(list)
    for row in result.all():
        # upper() applicato anche qui: la currency storica potrebbe non
        # essere sempre maiuscola in modo consistente, si canonicalizza in
        # lettura invece di richiedere una migration di normalizzazione dati.
        key = (row.transaction_date, row.amount, row.currency.strip().upper(), row.transaction_type)
        grouped[key].append(
            _CoreKeyCandidate(
                id=row.id, dedup_fingerprint=row.dedup_fingerprint, balance_after=row.balance_after, created_at=row.created_at
            )
        )
    return grouped


def _pick_best_candidate(
    candidates: list[_CoreKeyCandidate], new_balance_after: Decimal | None
) -> _CoreKeyCandidate:
    """balance_after resta SEMPRE secondario (SPEC §10): usato solo per
    scegliere quale candidato mostrare quando ne esiste piu' di uno a pari
    core key, mai per decidere l'esito NEW/DUPLICATE/REVIEW."""
    if new_balance_after is not None:
        for candidate in candidates:
            if candidate.balance_after == new_balance_after:
                return candidate
    return max(candidates, key=lambda c: c.created_at)


async def _find_dedup_decision(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    financial_account_id: uuid.UUID,
    existing_transaction_id: uuid.UUID,
    new_fingerprint: str,
) -> TransactionDedupDecision | None:
    result = await db.execute(
        select(TransactionDedupDecision).where(
            TransactionDedupDecision.workspace_id == workspace_id,
            TransactionDedupDecision.financial_account_id == financial_account_id,
            TransactionDedupDecision.existing_transaction_id == existing_transaction_id,
            TransactionDedupDecision.new_fingerprint == new_fingerprint,
        )
    )
    return result.scalar_one_or_none()


async def run_transaction_dedup(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    financial_account_id: uuid.UUID,
    rows: list[DedupCandidateRow],
) -> DedupBatchResult:
    if not rows:
        return DedupBatchResult(outcomes=[], new_count=0, duplicate_count=0, review_count=0)

    await _lock_account_for_dedup(db, workspace_id, financial_account_id)

    fingerprints = [
        compute_dedup_fingerprint(
            workspace_id=workspace_id,
            financial_account_id=financial_account_id,
            transaction_date=row.transaction_date,
            amount=row.amount,
            currency=row.currency,
            description_normalized=row.description_normalized,
            description_raw=row.description_raw,
            transaction_type=row.transaction_type,
        )
        for row in rows
    ]

    distinct_fingerprints = list(set(fingerprints))
    existing_counts: dict[str, int] = {}
    if distinct_fingerprints:
        result = await db.execute(
            select(Transaction.dedup_fingerprint, func.count())
            .where(
                Transaction.workspace_id == workspace_id,
                Transaction.financial_account_id == financial_account_id,
                Transaction.dedup_fingerprint.in_(distinct_fingerprints),
            )
            .group_by(Transaction.dedup_fingerprint)
        )
        existing_counts = {fp: count for fp, count in result.all()}

    outcomes: list[RowDedupOutcome | None] = [None] * len(rows)
    consumed: Counter[str] = Counter()
    pending_indices: list[int] = []

    # Occurrence matching (SPEC §11): le prime min(esistenti, nuove)
    # occorrenze di ciascun fingerprint, nell'ordine del batch, sono
    # DUPLICATE — le eventuali eccedenti proseguono al core-key check.
    for index, fp in enumerate(fingerprints):
        existing = existing_counts.get(fp, 0)
        if consumed[fp] < existing:
            consumed[fp] += 1
            outcomes[index] = RowDedupOutcome(index=index, fingerprint=fp, outcome="duplicate")
        else:
            pending_indices.append(index)

    if pending_indices:
        distinct_core_keys = list({core_key_of(rows[i]) for i in pending_indices})
        candidates_by_key = await _fetch_core_key_candidates(
            db, workspace_id, financial_account_id, distinct_core_keys
        )
        for index in pending_indices:
            row = rows[index]
            fp = fingerprints[index]
            key = core_key_of(row)
            # Esclude i candidati con lo STESSO fingerprint: sono le
            # occorrenze esistenti gia' consumate/considerate sopra, non un
            # secondo segnale di ambiguita' (altrimenti il test "2 esistenti
            # + 1 eccedente identico" finirebbe in REVIEW invece che NEW).
            candidates = [c for c in candidates_by_key.get(key, []) if c.dedup_fingerprint != fp]
            if not candidates:
                outcomes[index] = RowDedupOutcome(index=index, fingerprint=fp, outcome="new")
                continue

            candidate = _pick_best_candidate(candidates, row.balance_after)
            decision = await _find_dedup_decision(
                db, workspace_id, financial_account_id, candidate.id, fp
            )
            if decision is not None:
                resolved = "new" if decision.decision == "confirmed_distinct" else "duplicate"
                outcomes[index] = RowDedupOutcome(
                    index=index,
                    fingerprint=fp,
                    outcome=resolved,
                    candidate_existing_transaction_id=candidate.id,
                    auto_resolved=True,
                    dedup_decision_id=decision.id,
                )
            else:
                outcomes[index] = RowDedupOutcome(
                    index=index,
                    fingerprint=fp,
                    outcome="review",
                    candidate_existing_transaction_id=candidate.id,
                )

    final_outcomes = [o for o in outcomes if o is not None]
    assert len(final_outcomes) == len(rows)
    return DedupBatchResult(
        outcomes=final_outcomes,
        new_count=sum(1 for o in final_outcomes if o.outcome == "new"),
        duplicate_count=sum(1 for o in final_outcomes if o.outcome == "duplicate"),
        review_count=sum(1 for o in final_outcomes if o.outcome == "review"),
    )
