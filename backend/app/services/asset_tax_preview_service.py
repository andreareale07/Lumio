"""Anteprima fiscale per il dettaglio asset (colonna "Tasse" in
`AssetDetailPage`, seguito di FETTA 2): per la parte GIA' venduta riusa il
numero REALE gia' calcolato da `tax_gains_service.compute_tax_summary` (zero
ricalcolo); per la parte ANCORA APERTA simula "se vendessi oggi" con un
`TaxableGainEntry` sintetico iniettato nella stessa compensazione, PER
CONTO e in ORDINE DI CONSUMO FISCALE (LIFO/FIFO della giurisdizione) — mai
aggregato tra conti diversi (stesso vincolo del motore a lotti, FETTA 2),
mai un'assunzione arbitraria su quale lotto "conterrebbe" la compensazione
condivisa dello zainetto (motivazione completa in SPEC_TAX_REGIME.md).

Ogni scenario ipotetico riparte dallo stesso zainetto REALE (mai da uno gia'
"consumato" da un'ipotesi precedente) — cosi' il valore cumulativo dell'
ultimo lotto in ordine di consumo coincide sempre con "se vendessi oggi
TUTTO l'aperto in un colpo solo", senza bisogno di una nota "totale diverso
dalla somma"."""
import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.investment_transaction import InvestmentTransaction
from app.services.tax_calc import TaxableGainEntry, compute_taxable_gains
from app.services.tax_classification_service import list_asset_classifications
from app.services.tax_gains_service import TaxSummary, compute_tax_summary
from app.services.tax_lot_calc import compute_tax_lots
from app.services.tax_regime_service import resolve_regime_at
from app.tax.base import TaxJurisdiction, TaxRuleset


@dataclass(frozen=True)
class RealizedPortionTax:
    lot_transaction_id: uuid.UUID
    sell_transaction_id: uuid.UUID
    tax_due: Decimal | None
    taxable_amount: Decimal | None
    offset_amount: Decimal | None
    excluded_reason: str | None


@dataclass(frozen=True)
class OpenLotTaxPreview:
    transaction_id: uuid.UUID
    financial_account_id: uuid.UUID
    # Posizione (0-based) nell'ordine di consumo fiscale REALE all'interno
    # del proprio conto (mai tra conti diversi) — il chiamante lo usa per
    # comunicare perche' il valore cumulativo non segue necessariamente
    # l'ordine cronologico di acquisto mostrato in tabella (LIFO: il lotto
    # piu' recente ha sequence=0).
    sequence: int
    cumulative_quantity: Decimal
    cumulative_gain: Decimal
    tax_due: Decimal | None
    taxable_amount: Decimal | None
    offset_amount: Decimal | None
    excluded_reason: str | None


@dataclass(frozen=True)
class AssetTaxPreview:
    realized: tuple[RealizedPortionTax, ...]
    open_cumulative: tuple[OpenLotTaxPreview, ...]


async def compute_asset_tax_preview(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    jurisdiction: TaxJurisdiction,
    asset_id: uuid.UUID,
    current_price: Decimal | None,
    on: date,
) -> AssetTaxPreview:
    # Il calcolo reale (zainetto + compensazione) riguarda TUTTO il
    # workspace, non solo questo asset: la compensazione e' cronologica per
    # perimetro, un evento di un altro asset puo' aver gia' consumato parte
    # della capienza prima di questo. Si filtra il risultato per asset SOLO
    # dopo, mai prima.
    summary = await compute_tax_summary(db, workspace_id, jurisdiction, on)
    ruleset = jurisdiction.ruleset_at(on)

    realized_by_key = {
        (r.lot_transaction_id, r.sell_transaction_id): RealizedPortionTax(
            lot_transaction_id=r.lot_transaction_id,
            sell_transaction_id=r.sell_transaction_id,
            tax_due=r.tax_due,
            taxable_amount=r.taxable_amount,
            offset_amount=r.offset_amount,
            excluded_reason=None,
        )
        for r in summary.taxable_gains.rows
        if r.asset_id == asset_id
    }
    # Un evento escluso (asset non codificato/conto senza regime/eccetera) o
    # una minusvalenza realizzata (finita nello zainetto, non tassata di per
    # se') non ha una riga in `taxable_gains.rows` — qui si aggiungono le
    # chiavi mancanti con `excluded_reason` valorizzato (esclusi) o
    # `tax_due=0` (minusvalenze, nessuna assunzione: sappiamo con certezza
    # che una minusvalenza non genera imposta propria).
    other_events = {
        (e.lot_transaction_id, e.sell_transaction_id): RealizedPortionTax(
            lot_transaction_id=e.lot_transaction_id,
            sell_transaction_id=e.sell_transaction_id,
            tax_due=None if e.excluded_reason is not None else Decimal("0"),
            taxable_amount=None if e.excluded_reason is not None else Decimal("0"),
            offset_amount=None if e.excluded_reason is not None else Decimal("0"),
            excluded_reason=e.excluded_reason,
        )
        for e in summary.realized_events
        if e.asset_id == asset_id and (e.lot_transaction_id, e.sell_transaction_id) not in realized_by_key
    }
    realized = tuple({**other_events, **realized_by_key}.values())

    open_cumulative: list[OpenLotTaxPreview] = []
    if current_price is not None:
        open_cumulative = await _compute_open_cumulative(
            db, workspace_id, jurisdiction, ruleset, asset_id, current_price, on, summary
        )

    return AssetTaxPreview(realized=realized, open_cumulative=tuple(open_cumulative))


async def _compute_open_cumulative(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    jurisdiction: TaxJurisdiction,
    ruleset: TaxRuleset,
    asset_id: uuid.UUID,
    current_price: Decimal,
    on: date,
    summary: TaxSummary,
) -> list[OpenLotTaxPreview]:
    result = await db.execute(
        select(InvestmentTransaction)
        .where(
            InvestmentTransaction.workspace_id == workspace_id,
            InvestmentTransaction.asset_id == asset_id,
            InvestmentTransaction.type.in_(("buy", "sell", "opening", "split", "adjustment", "dividend")),
        )
        .order_by(
            InvestmentTransaction.financial_account_id,
            InvestmentTransaction.trade_date,
            InvestmentTransaction.created_at,
            InvestmentTransaction.id,
        )
    )
    rows = list(result.scalars().all())
    if not rows:
        return []

    classifications = {v.asset_id: v for v in await list_asset_classifications(db, workspace_id, jurisdiction, on)}
    classification = classifications.get(asset_id)

    groups: dict[uuid.UUID, list[InvestmentTransaction]] = {}
    for row in rows:
        groups.setdefault(row.financial_account_id, []).append(row)

    # Gains REALI di TUTTO il workspace (non solo questo asset) — stessa
    # lista, stesso filtro, che ha gia' prodotto `summary.taxable_gains`:
    # ogni scenario ipotetico si aggiunge a QUESTA base, mai a una gia'
    # mutata da uno scenario precedente (altrimenti il secondo lotto
    # "vedrebbe" una capienza gia' ridotta dal primo, invalidando
    # l'indipendenza degli scenari).
    real_gains = [
        TaxableGainEntry(
            trade_date=e.trade_date,
            perimeter=e.perimeter,
            gain_category=e.gain_category,
            nominal=e.gain_or_loss,
            rate=e.rate,
            taxable_coefficient=e.taxable_coefficient,
            asset_id=e.asset_id,
            lot_transaction_id=e.lot_transaction_id,
            sell_transaction_id=e.sell_transaction_id,
        )
        for e in summary.realized_events
        if e.excluded_reason is None and e.gain_or_loss > 0
    ]
    pocket = summary.loss_pocket
    consumption_order = ruleset.lot_consumption_order

    previews: list[OpenLotTaxPreview] = []
    for account_id, movements in groups.items():
        state = compute_tax_lots(movements, consumption_order)
        if not state.open_lots:
            continue

        # `state.open_lots` e' sempre in ordine cronologico di acquisizione
        # (LIFO/FIFO decidono solo DA QUALE ESTREMO si preleva, non come la
        # lista e' memorizzata — vedi `_peek_lot`/`_pop_exhausted_lot` in
        # tax_lot_calc.py) — qui si materializza esplicitamente l'ordine di
        # CONSUMO (chi verrebbe venduto per primo oggi).
        ordered_lots = list(reversed(state.open_lots)) if consumption_order == "lifo" else list(state.open_lots)

        regime_code = await resolve_regime_at(db, workspace_id, account_id, on)
        regime = next((r for r in jurisdiction.regimes(on) if r.code == regime_code), None) if regime_code else None
        perimeter = "dichiarativo" if regime is not None and regime.pocket_scope == "aggregate" else str(account_id)

        treatment = None
        excluded_reason: str | None = None
        if classification is None or classification.asset_class is None or not classification.codified:
            excluded_reason = "asset_not_codified"
        elif regime_code is None:
            excluded_reason = "no_regime_at_date"
        else:
            treatment = ruleset.treatment_for(classification.asset_class, "sale")
            if treatment is None or treatment.status == "not_codified":
                excluded_reason = "treatment_not_codified"

        cumulative_quantity = Decimal("0")
        cumulative_gain = Decimal("0")
        for sequence, lot in enumerate(ordered_lots):
            cumulative_quantity += lot.quantity
            cumulative_gain += (current_price - lot.unit_cost) * lot.quantity

            if excluded_reason is not None or treatment is None:
                previews.append(
                    OpenLotTaxPreview(
                        transaction_id=lot.transaction_id,
                        financial_account_id=account_id,
                        sequence=sequence,
                        cumulative_quantity=cumulative_quantity,
                        cumulative_gain=cumulative_gain,
                        tax_due=None,
                        taxable_amount=None,
                        offset_amount=None,
                        excluded_reason=excluded_reason,
                    )
                )
                continue

            if cumulative_gain <= 0:
                # Una minusvalenza ipotetica non genera imposta (diventerebbe
                # zainetto, non un onere) — mai passare un nominale <= 0 a
                # `compute_taxable_gains`, che assume sempre plusvalenze.
                previews.append(
                    OpenLotTaxPreview(
                        transaction_id=lot.transaction_id,
                        financial_account_id=account_id,
                        sequence=sequence,
                        cumulative_quantity=cumulative_quantity,
                        cumulative_gain=cumulative_gain,
                        tax_due=Decimal("0"),
                        taxable_amount=Decimal("0"),
                        offset_amount=Decimal("0"),
                        excluded_reason=None,
                    )
                )
                continue

            synthetic = TaxableGainEntry(
                trade_date=on,
                perimeter=perimeter,
                gain_category=treatment.gain_category,
                nominal=cumulative_gain,
                rate=treatment.rate,
                taxable_coefficient=treatment.taxable_coefficient,
                asset_id=asset_id,
                lot_transaction_id=lot.transaction_id,
                sell_transaction_id=lot.transaction_id,  # nessuna vendita reale: id sintetico, mai persistito
            )
            scenario = compute_taxable_gains([*real_gains, synthetic], pocket, ruleset, on)
            synthetic_row = next(
                r
                for r in scenario.rows
                if r.asset_id == asset_id and r.trade_date == on and r.lot_transaction_id == lot.transaction_id
            )
            previews.append(
                OpenLotTaxPreview(
                    transaction_id=lot.transaction_id,
                    financial_account_id=account_id,
                    sequence=sequence,
                    cumulative_quantity=cumulative_quantity,
                    cumulative_gain=cumulative_gain,
                    tax_due=synthetic_row.tax_due,
                    taxable_amount=synthetic_row.taxable_amount,
                    offset_amount=synthetic_row.offset_amount,
                    excluded_reason=None,
                )
            )

    return previews
