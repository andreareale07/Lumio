"""Collega il motore a lotti puro (`tax_lot_calc.py`) ai movimenti reali
(SPEC_TAX_REGIME.md FETTA 2) — DB-aware: legge `investment_transactions`,
risolve regime/classificazione fiscale per ciascun evento, produce eventi
realizzati classificati. Nessuna tabella persistita (derivato a lettura,
stesso principio di FETTA 1): questo servizio non scrive mai nulla.
"""
import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.investment_transaction import InvestmentTransaction
from app.services.tax_classification_service import AssetClassificationView, list_asset_classifications
from app.services.tax_lot_calc import RealizedTaxEvent, compute_tax_lots
from app.services.tax_regime_service import resolve_regime_at
from app.tax.base import TaxJurisdiction


@dataclass(frozen=True)
class ClassifiedRealizedEvent:
    financial_account_id: uuid.UUID
    asset_id: uuid.UUID
    trade_date: date
    quantity: Decimal
    proceeds: Decimal
    cost_basis: Decimal
    gain_or_loss: Decimal
    lot_formation_date: date
    lot_transaction_id: uuid.UUID
    sell_transaction_id: uuid.UUID
    # None quando l'evento e' escluso dal calcolo (asset non codificato o
    # nessun regime risolto a questa data) — mai un numero inventato, mai
    # silenziosamente sparito: resta nella lista con `excluded_reason`.
    asset_class: str | None
    gain_category: str | None
    loss_category: str | None
    rate: Decimal | None
    taxable_coefficient: Decimal | None
    legal_reference: str | None
    perimeter: str | None  # str(financial_account_id) se per_account, "dichiarativo" se aggregate
    formed_under_ruleset_code: str | None
    excluded_reason: str | None


async def list_realized_events(
    db: AsyncSession, workspace_id: uuid.UUID, jurisdiction: TaxJurisdiction, on: date
) -> list[ClassifiedRealizedEvent]:
    result = await db.execute(
        select(InvestmentTransaction)
        .where(
            InvestmentTransaction.workspace_id == workspace_id,
            InvestmentTransaction.asset_id.is_not(None),
            InvestmentTransaction.type.in_(("buy", "sell", "opening", "split", "adjustment", "dividend")),
        )
        .order_by(
            InvestmentTransaction.financial_account_id,
            InvestmentTransaction.asset_id,
            InvestmentTransaction.trade_date,
            InvestmentTransaction.created_at,
            InvestmentTransaction.id,
        )
    )
    rows = list(result.scalars().all())
    if not rows:
        return []

    classifications = {
        v.asset_id: v for v in await list_asset_classifications(db, workspace_id, jurisdiction, on)
    }

    # Ordine di consumo dei lotti: dato della giurisdizione VIGENTE ora
    # (`on`), non ricalcolato per ogni singolo evento — e' un metodo di
    # identificazione contabile, non una regola che cambia a meta' della
    # vita di una posizione (vedi app/tax/base.py::TaxRuleset.lot_consumption_order).
    consumption_order = jurisdiction.ruleset_at(on).lot_consumption_order

    events: list[ClassifiedRealizedEvent] = []
    # Raggruppa per (financial_account_id, asset_id): il motore puro lavora
    # su UN solo gruppo alla volta (vedi tax_lot_calc.py docstring).
    groups: dict[tuple[uuid.UUID, uuid.UUID], list[InvestmentTransaction]] = {}
    for row in rows:
        groups.setdefault((row.financial_account_id, row.asset_id), []).append(row)

    for (account_id, asset_id), movements in groups.items():
        state = compute_tax_lots(movements, consumption_order)
        classification = classifications.get(asset_id)
        for raw_event in state.realized_events:
            events.append(
                await _classify_event(db, workspace_id, jurisdiction, account_id, asset_id, raw_event, classification)
            )
    return events


async def _classify_event(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    jurisdiction: TaxJurisdiction,
    account_id: uuid.UUID,
    asset_id: uuid.UUID,
    raw_event: RealizedTaxEvent,
    classification: AssetClassificationView | None,
) -> ClassifiedRealizedEvent:
    base = dict(
        financial_account_id=account_id,
        asset_id=asset_id,
        trade_date=raw_event.trade_date,
        quantity=raw_event.quantity,
        proceeds=raw_event.proceeds,
        cost_basis=raw_event.cost_basis,
        gain_or_loss=raw_event.gain_or_loss,
        lot_formation_date=raw_event.lot_formation_date,
        lot_transaction_id=raw_event.lot_transaction_id,
        sell_transaction_id=raw_event.sell_transaction_id,
    )

    if classification is None or classification.asset_class is None or not classification.codified:
        return ClassifiedRealizedEvent(
            **base,
            asset_class=classification.asset_class if classification else None,
            gain_category=None,
            loss_category=None,
            rate=None,
            taxable_coefficient=None,
            legal_reference=None,
            perimeter=None,
            formed_under_ruleset_code=None,
            excluded_reason="asset_not_codified",
        )

    regime_code = await resolve_regime_at(db, workspace_id, account_id, raw_event.trade_date)
    if regime_code is None:
        return ClassifiedRealizedEvent(
            **base,
            asset_class=classification.asset_class,
            gain_category=None,
            loss_category=None,
            rate=None,
            taxable_coefficient=None,
            legal_reference=None,
            perimeter=None,
            formed_under_ruleset_code=None,
            excluded_reason="no_regime_at_date",
        )
    regime = next((r for r in jurisdiction.regimes(raw_event.trade_date) if r.code == regime_code), None)
    perimeter = (
        "dichiarativo" if regime is not None and regime.pocket_scope == "aggregate" else str(account_id)
    )

    ruleset = jurisdiction.ruleset_at(raw_event.trade_date)
    treatment = ruleset.treatment_for(classification.asset_class, "sale")
    if treatment is None or treatment.status == "not_codified":
        return ClassifiedRealizedEvent(
            **base,
            asset_class=classification.asset_class,
            gain_category=None,
            loss_category=None,
            rate=None,
            taxable_coefficient=None,
            legal_reference=None,
            perimeter=perimeter,
            formed_under_ruleset_code=ruleset.code,
            excluded_reason="treatment_not_codified",
        )

    return ClassifiedRealizedEvent(
        **base,
        asset_class=classification.asset_class,
        gain_category=treatment.gain_category,
        loss_category=treatment.loss_category,
        rate=treatment.rate,
        taxable_coefficient=treatment.taxable_coefficient,
        legal_reference=treatment.legal_reference,
        perimeter=perimeter,
        formed_under_ruleset_code=ruleset.code,
        excluded_reason=None,
    )
