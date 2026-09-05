"""Orchestrazione FETTA 2: compone aperture manuali + eventi realizzati dal
motore a lotti in un'unica lettura, cosi' `GET /tax/loss-pocket` e
`GET /tax/taxable-gains` vedono SEMPRE lo stesso insieme di eventi (mai due
interrogazioni indipendenti che potrebbero disallinearsi tra una richiesta
e l'altra)."""
import uuid
from dataclasses import dataclass
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.services import tax_opening_service
from app.services.tax_calc import (
    LossPocketEntry,
    LossPocketResult,
    TaxableGainEntry,
    TaxableGainsResult,
    build_loss_pocket,
    compute_taxable_gains,
)
from app.services.tax_realized_service import ClassifiedRealizedEvent, list_realized_events
from app.tax.base import TaxJurisdiction


@dataclass(frozen=True)
class TaxSummary:
    loss_pocket: LossPocketResult
    taxable_gains: TaxableGainsResult
    excluded_events: tuple[ClassifiedRealizedEvent, ...]


async def compute_tax_summary(
    db: AsyncSession, workspace_id: uuid.UUID, jurisdiction: TaxJurisdiction, on: date
) -> TaxSummary:
    openings = await tax_opening_service.list_openings(db, workspace_id)
    realized_events = await list_realized_events(db, workspace_id, jurisdiction, on)
    ruleset = jurisdiction.ruleset_at(on)

    loss_entries = [
        LossPocketEntry(
            formation_date=o.formation_date,
            nominal=o.amount,
            income_category=o.income_category,
            perimeter=str(o.financial_account_id) if o.financial_account_id is not None else "dichiarativo",
            source="user_opening",
            formed_under_ruleset_code=o.formed_under_ruleset_code,
        )
        for o in openings
    ]
    loss_entries.extend(
        LossPocketEntry(
            formation_date=e.trade_date,
            nominal=-e.gain_or_loss,
            income_category=e.loss_category,
            perimeter=e.perimeter,
            source="computed",
            formed_under_ruleset_code=e.formed_under_ruleset_code,
            asset_id=e.asset_id,
        )
        for e in realized_events
        if e.excluded_reason is None and e.gain_or_loss < 0
    )
    pocket = build_loss_pocket(loss_entries, ruleset, on)

    gains = [
        TaxableGainEntry(
            trade_date=e.trade_date,
            perimeter=e.perimeter,
            gain_category=e.gain_category,
            nominal=e.gain_or_loss,
            rate=e.rate,
            taxable_coefficient=e.taxable_coefficient,
            asset_id=e.asset_id,
        )
        for e in realized_events
        if e.excluded_reason is None and e.gain_or_loss > 0
    ]
    taxable_gains = compute_taxable_gains(gains, pocket, ruleset, on)

    excluded_events = tuple(e for e in realized_events if e.excluded_reason is not None)
    return TaxSummary(loss_pocket=pocket, taxable_gains=taxable_gains, excluded_events=excluded_events)
