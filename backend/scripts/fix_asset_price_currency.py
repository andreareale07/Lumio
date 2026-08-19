"""Riparazione una tantum del bug reale: `GET /assets/{id}/price-history`
etichettava ogni prezzo scaricato con `asset.currency` (la valuta con cui
l'utente ha comprato il titolo) invece della valuta REALE con cui Yahoo lo
quota (es. un ISIN giapponese quotato in JPY anche se l'asset e' registrato
in EUR) — vedi il fix in `app/api/v1/assets.py::get_asset_price_history` e
`app/worker/jobs/market_data.py::_refresh_fx_rates`. Questo script corregge
le righe di `asset_prices` gia' scritte prima del fix.

Per ogni workspace con un profilo market data attivo diverso da "manual":
per ogni asset con symbol/isin, chiede al provider la valuta REALE
(`fetch_quote`) e, se diversa da quella gia' persistita, corregge SOLO le
righe con `source` uguale al provider (mai le righe `source="manual"`: una
correzione manuale dell'utente ha sempre priorita', stesso principio delle
classificazioni AI). Poi rilancia il refresh dei tassi di cambio (ora esteso
a guardare anche le valute effettive di `asset_prices`, non solo quelle
dichiarate su asset/conti) cosi' la conversione funziona subito.

Uso: docker compose exec app python scripts/fix_asset_price_currency.py
     docker compose exec app python scripts/fix_asset_price_currency.py --dry-run
"""
import asyncio
import sys

from sqlalchemy import select, update

from app.db.rls import rls_session
from app.marketdata.base import AssetRef, MarketDataProviderError
from app.marketdata.registry import build_provider
from app.models.asset import Asset
from app.models.asset_price import AssetPrice
from app.models.workspace import Workspace
from app.services.market_data_profile_service import get_active_profile
from app.worker.jobs.market_data import _refresh_fx_rates, list_workspace_owners


async def _fix_workspace(workspace_id, owner_user_id, dry_run: bool) -> int:
    fixed = 0
    async with rls_session(owner_user_id) as db:
        profile = await get_active_profile(db, workspace_id)
        if profile is None or profile.provider == "manual":
            return 0
        provider = build_provider(profile)

        assets = (
            await db.execute(
                select(Asset).where(
                    Asset.workspace_id == workspace_id,
                    (Asset.symbol.is_not(None)) | (Asset.isin.is_not(None)),
                )
            )
        ).scalars().all()

        for asset in assets:
            try:
                quote = await provider.fetch_quote(
                    AssetRef(
                        id=asset.id, symbol=asset.symbol, isin=asset.isin, name=asset.name, currency=asset.currency
                    )
                )
            except MarketDataProviderError as exc:
                print(f"  [skip] {asset.name}: provider non raggiungibile ({exc})")
                continue
            if quote is None:
                continue

            wrong_rows = (
                await db.execute(
                    select(AssetPrice).where(
                        AssetPrice.workspace_id == workspace_id,
                        AssetPrice.asset_id == asset.id,
                        AssetPrice.source == profile.provider,
                        AssetPrice.currency != quote.currency,
                    )
                )
            ).scalars().all()
            if not wrong_rows:
                continue

            print(
                f"  {asset.name}: {len(wrong_rows)} righe da "
                f"{ {r.currency for r in wrong_rows} } -> {quote.currency}"
            )
            fixed += len(wrong_rows)
            if not dry_run:
                await db.execute(
                    update(AssetPrice)
                    .where(
                        AssetPrice.workspace_id == workspace_id,
                        AssetPrice.asset_id == asset.id,
                        AssetPrice.source == profile.provider,
                        AssetPrice.currency != quote.currency,
                    )
                    .values(currency=quote.currency)
                )

        if not dry_run and fixed:
            base_currency = (
                await db.execute(select(Workspace.base_currency).where(Workspace.id == workspace_id))
            ).scalar_one()
            fx_updated = await _refresh_fx_rates(db, workspace_id, provider, base_currency, profile.provider)
            print(f"  tassi di cambio aggiornati: {fx_updated}")

        if not dry_run:
            await db.commit()
    return fixed


async def main() -> None:
    dry_run = "--dry-run" in sys.argv
    if dry_run:
        print("=== DRY RUN: nessuna scrittura ===")

    total = 0
    for workspace_id, owner_user_id in await list_workspace_owners():
        print(f"Workspace {workspace_id}:")
        total += await _fix_workspace(workspace_id, owner_user_id, dry_run)

    print(f"\nTotale righe {'da correggere' if dry_run else 'corrette'}: {total}")


if __name__ == "__main__":
    asyncio.run(main())
