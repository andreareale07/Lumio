"""Riconoscimento/creazione automatica di un `Asset` per ISIN (SPEC §33),
usato dal parsing automatico dei movimenti Trade Republic (M09c), sia
all'import che nel backfill (`app/services/investment_backfill.py`). Match
esatto sull'ISIN gia' presente nel workspace; se non esiste, ne crea uno
nuovo con una classificazione best-effort — sempre correggibile dall'utente
via `PATCH /assets/{id}`, mai bloccante.
"""
import re
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset import Asset

_ETF_HINT_RE = re.compile(r"\bETF\b", re.IGNORECASE)


def guess_asset_type(name: str) -> str:
    """Euristica minima (non un catalogo/registro esterno, fuori scope M09):
    il nome di un ETF su Trade Republic contiene sempre "ETF" per
    convenzione UCITS ("... UCITS ETF ..."); un'azione singola no. Default
    onesto a "stock" quando l'euristica non si applica — mai "other" per
    qualcosa che quasi certamente e' un titolo, correggibile comunque."""
    if _ETF_HINT_RE.search(name):
        return "etf"
    return "stock"


async def get_or_create_asset_by_isin(
    db: AsyncSession, workspace_id: uuid.UUID, isin: str, name: str, currency: str
) -> Asset:
    result = await db.execute(select(Asset).where(Asset.workspace_id == workspace_id, Asset.isin == isin))
    asset = result.scalar_one_or_none()
    if asset is not None:
        return asset

    asset = Asset(
        workspace_id=workspace_id,
        isin=isin,
        name=name,
        asset_type=guess_asset_type(name),
        currency=currency,
    )
    db.add(asset)
    # flush, non commit: serve l'id per l'InvestmentTransaction che lo
    # referenzia nella stessa transazione DB (il commit resta al chiamante).
    await db.flush()
    return asset
