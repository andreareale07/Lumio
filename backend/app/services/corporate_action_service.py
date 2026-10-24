"""Lato DB delle operazioni societarie (vedi `corporate_action_calc.py` per il
perche'): suggerimenti calcolati dai movimenti registrati, unione di due asset
con rapporto di raggruppamento, chiusura a zero di un derivato scaduto.

Nessuna scrittura diretta su `positions`: tutto passa dal libro mastro
`investment_transactions` (un movimento `split` o `sell`) e da
`recompute_position`, come per ogni altra modifica (vedi `position_service.py`).
"""
import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset import Asset
from app.models.asset_price import AssetPrice
from app.models.asset_profile import AssetProfile
from app.models.investment_transaction import InvestmentTransaction
from app.models.position import Position
from app.services.corporate_action_calc import (
    AssetActivity,
    SplitSuggestionCalc,
    detect_split_suggestions,
    is_derivative_name,
    suggest_split_date,
)
from app.services.position_service import recompute_position

# Un derivato senza quotazioni da piu' di cosi' e' quasi certamente scaduto o
# sospeso: i prezzi giornalieri non mancano mai a lungo per un titolo vivo.
_STALE_PRICE_DAYS = 30
_PRICED_TYPES = ("buy", "sell", "opening")


class CorporateActionError(Exception):
    """Errore di validazione dell'utente, mappato su 400 dall'API."""


@dataclass(frozen=True)
class SplitSuggestion:
    calc: SplitSuggestionCalc
    source_label: str
    target_label: str
    source_quantity: Decimal
    target_quantity: Decimal


@dataclass(frozen=True)
class ExpirySuggestion:
    asset_id: uuid.UUID
    asset_label: str
    quantity: Decimal
    cost_basis: Decimal
    currency: str
    last_price_date: date | None


async def _labels(db: AsyncSession, workspace_id: uuid.UUID, assets: dict[uuid.UUID, Asset]) -> dict[uuid.UUID, str]:
    display = dict(
        (
            await db.execute(
                select(AssetProfile.asset_id, AssetProfile.display_name).where(
                    AssetProfile.workspace_id == workspace_id, AssetProfile.asset_id.in_(assets.keys())
                )
            )
        ).all()
    )
    return {aid: (display.get(aid) or a.symbol or a.name) for aid, a in assets.items()}


async def _build_activities(
    db: AsyncSession, workspace_id: uuid.UUID
) -> tuple[list[AssetActivity], dict[uuid.UUID, Asset]]:
    positions = list(
        (await db.execute(select(Position).where(Position.workspace_id == workspace_id))).scalars().all()
    )
    net_by_asset: dict[uuid.UUID, Decimal] = {}
    for position in positions:
        net_by_asset[position.asset_id] = net_by_asset.get(position.asset_id, Decimal("0")) + position.quantity
    if not net_by_asset:
        return [], {}

    assets = {
        a.id: a
        for a in (await db.execute(select(Asset).where(Asset.id.in_(net_by_asset.keys())))).scalars().all()
    }
    movements = (
        (
            await db.execute(
                select(InvestmentTransaction)
                .where(
                    InvestmentTransaction.workspace_id == workspace_id,
                    InvestmentTransaction.asset_id.in_(net_by_asset.keys()),
                    InvestmentTransaction.type.in_(_PRICED_TYPES),
                )
                .order_by(InvestmentTransaction.trade_date, InvestmentTransaction.created_at)
            )
        )
        .scalars()
        .all()
    )
    by_asset: dict[uuid.UUID, list[InvestmentTransaction]] = {}
    for m in movements:
        by_asset.setdefault(m.asset_id, []).append(m)

    activities: list[AssetActivity] = []
    for asset_id, rows in by_asset.items():
        asset = assets.get(asset_id)
        if asset is None:
            continue
        priced = [m for m in rows if m.price]
        activities.append(
            AssetActivity(
                asset_id=str(asset_id),
                name=asset.name,
                currency=asset.currency,
                net_quantity=net_by_asset[asset_id],
                first_date=rows[0].trade_date,
                last_date=rows[-1].trade_date,
                first_price=priced[0].price if priced else None,
                last_price=priced[-1].price if priced else None,
            )
        )
    return activities, assets


async def list_split_suggestions(db: AsyncSession, workspace_id: uuid.UUID) -> list[SplitSuggestion]:
    activities, assets = await _build_activities(db, workspace_id)
    found = detect_split_suggestions(activities)
    if not found:
        return []
    labels = await _labels(db, workspace_id, assets)
    quantity = {a.asset_id: a.net_quantity for a in activities}
    return [
        SplitSuggestion(
            calc=s,
            source_label=labels[uuid.UUID(s.source_asset_id)],
            target_label=labels[uuid.UUID(s.target_asset_id)],
            source_quantity=quantity[s.source_asset_id],
            target_quantity=quantity[s.target_asset_id],
        )
        for s in found
    ]


async def list_expiry_suggestions(
    db: AsyncSession, workspace_id: uuid.UUID, today: date
) -> list[ExpirySuggestion]:
    positions = list(
        (
            await db.execute(
                select(Position).where(Position.workspace_id == workspace_id, Position.quantity > 0)
            )
        )
        .scalars()
        .all()
    )
    if not positions:
        return []
    asset_ids = {p.asset_id for p in positions}
    assets = {
        a.id: a for a in (await db.execute(select(Asset).where(Asset.id.in_(asset_ids)))).scalars().all()
    }
    derivative_ids = {aid for aid, a in assets.items() if is_derivative_name(a.name)}
    if not derivative_ids:
        return []
    labels = await _labels(db, workspace_id, {aid: assets[aid] for aid in derivative_ids})

    by_asset: dict[uuid.UUID, list[Position]] = {}
    for p in positions:
        if p.asset_id in derivative_ids:
            by_asset.setdefault(p.asset_id, []).append(p)

    suggestions: list[ExpirySuggestion] = []
    for asset_id, rows in by_asset.items():
        latest = (
            await db.execute(
                select(AssetPrice.price_date)
                .where(AssetPrice.workspace_id == workspace_id, AssetPrice.asset_id == asset_id)
                .order_by(AssetPrice.price_date.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if latest is not None and (today - latest) <= timedelta(days=_STALE_PRICE_DAYS):
            continue
        suggestions.append(
            ExpirySuggestion(
                asset_id=asset_id,
                asset_label=labels[asset_id],
                quantity=sum((p.quantity for p in rows), Decimal("0")),
                cost_basis=sum((p.quantity * p.average_cost for p in rows), Decimal("0")).quantize(Decimal("0.01")),
                currency=assets[asset_id].currency,
                last_price_date=latest,
            )
        )
    return suggestions


async def _recompute_or_raise(
    db: AsyncSession, workspace_id: uuid.UUID, account_id: uuid.UUID, asset_id: uuid.UUID, currency: str
) -> None:
    _, warnings = await recompute_position(db, workspace_id, account_id, asset_id, currency)
    if warnings:
        raise CorporateActionError("; ".join(warnings))


async def merge_assets(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    source_asset_id: uuid.UUID,
    target_asset_id: uuid.UUID,
    ratio: Decimal,
    split_date: date | None,
) -> None:
    """Sposta TUTTI i movimenti di `source` su `target` e inserisce, per ogni
    conto coinvolto, un movimento `split` (moltiplicatore `ratio`, unita' del
    titolo nuovo per 1 del vecchio) tra i movimenti vecchi e quelli nuovi.
    Il chiamante fa commit/rollback. Al `source` non resta nessun movimento:
    sparisce dalle posizioni (e il suggerimento non si ripresenta)."""
    if source_asset_id == target_asset_id:
        raise CorporateActionError("Gli asset da unire devono essere diversi")
    if ratio <= 0:
        raise CorporateActionError("Il rapporto deve essere maggiore di zero")
    source = await db.get(Asset, source_asset_id)
    target = await db.get(Asset, target_asset_id)
    if source is None or source.workspace_id != workspace_id:
        raise CorporateActionError("Asset di origine non valido")
    if target is None or target.workspace_id != workspace_id:
        raise CorporateActionError("Asset di destinazione non valido")
    if source.currency != target.currency:
        raise CorporateActionError("I due asset hanno valute diverse: unione non supportata")

    source_movements = list(
        (
            await db.execute(
                select(InvestmentTransaction).where(
                    InvestmentTransaction.workspace_id == workspace_id,
                    InvestmentTransaction.asset_id == source_asset_id,
                )
            )
        )
        .scalars()
        .all()
    )
    if not source_movements:
        raise CorporateActionError("L'asset di origine non ha movimenti da unire")
    target_movements = list(
        (
            await db.execute(
                select(InvestmentTransaction).where(
                    InvestmentTransaction.workspace_id == workspace_id,
                    InvestmentTransaction.asset_id == target_asset_id,
                )
            )
        )
        .scalars()
        .all()
    )

    source_last = max(m.trade_date for m in source_movements)
    if split_date is None:
        if target_movements:
            target_first = min(m.trade_date for m in target_movements)
            if target_first <= source_last:
                raise CorporateActionError(
                    "I movimenti dei due asset si sovrappongono nel tempo: indica la data del raggruppamento"
                )
            split_date = suggest_split_date(source_last, target_first)
        else:
            split_date = source_last
    elif split_date < source_last:
        raise CorporateActionError("La data del raggruppamento e' precedente a un movimento dell'asset di origine")

    accounts = {m.financial_account_id for m in source_movements}
    await db.execute(
        update(InvestmentTransaction)
        .where(InvestmentTransaction.workspace_id == workspace_id, InvestmentTransaction.asset_id == source_asset_id)
        .values(asset_id=target_asset_id)
    )
    for account_id in accounts:
        db.add(
            InvestmentTransaction(
                workspace_id=workspace_id,
                financial_account_id=account_id,
                asset_id=target_asset_id,
                trade_date=split_date,
                type="split",
                quantity=ratio,
                amount=Decimal("0"),
                currency=target.currency,
                source_type_raw="asset_merge",
                notes=f"Unione {source.name} -> {target.name} (rapporto {ratio.normalize():f})",
            )
        )
    await db.flush()
    # Le entita' gia' caricate non vedono l'UPDATE in bulk (vedi lumio-rls-gotchas).
    for m in source_movements:
        await db.refresh(m)

    for account_id in accounts:
        await _recompute_or_raise(db, workspace_id, account_id, source_asset_id, source.currency)
        await _recompute_or_raise(db, workspace_id, account_id, target_asset_id, target.currency)


async def expire_asset(
    db: AsyncSession, workspace_id: uuid.UUID, asset_id: uuid.UUID, expiry_date: date
) -> int:
    """Chiude a zero (vendita dell'intera quantita' a prezzo 0, nessun incasso)
    ogni posizione aperta dell'asset: knock-out/scadenza senza valore. Ritorna
    quante posizioni ha chiuso."""
    asset = await db.get(Asset, asset_id)
    if asset is None or asset.workspace_id != workspace_id:
        raise CorporateActionError("Asset non valido")
    positions = list(
        (
            await db.execute(
                select(Position).where(
                    Position.workspace_id == workspace_id, Position.asset_id == asset_id, Position.quantity > 0
                )
            )
        )
        .scalars()
        .all()
    )
    if not positions:
        raise CorporateActionError("Nessuna posizione aperta su questo asset")
    for position in positions:
        db.add(
            InvestmentTransaction(
                workspace_id=workspace_id,
                financial_account_id=position.financial_account_id,
                asset_id=asset_id,
                trade_date=expiry_date,
                type="sell",
                quantity=position.quantity,
                price=Decimal("0"),
                amount=Decimal("0"),
                currency=position.currency,
                source_type_raw="expiry_worthless",
                notes="Scaduto senza valore (knock-out/scadenza)",
            )
        )
    await db.flush()
    for position in positions:
        await _recompute_or_raise(db, workspace_id, position.financial_account_id, asset_id, position.currency)
    return len(positions)
