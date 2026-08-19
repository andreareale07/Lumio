"""Validazione DB-aware delle valute (sistema di valute) — ponte fra
`app/models/currency.py` e gli endpoint che accettano un codice valuta
scelto dall'utente (`FinancialAccountCreate.currency`, `AssetCreate.
currency`, `WorkspaceUpdate.base_currency`). La FK a livello DB (migration
0029) e' gia' sufficiente a impedire un codice inesistente, ma un controllo
applicativo esplicito PRIMA dell'INSERT/UPDATE da' un errore leggibile
("codice valuta sconosciuto") invece di un generico vincolo di integrita' —
stesso principio di "isolamento sempre a doppio livello" gia' applicato
altrove in questo codebase (mai fidarsi di un solo strato).
"""
import uuid

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.currency import Currency


async def currency_exists(db: AsyncSession, workspace_id: uuid.UUID, code: str) -> bool:
    """True se `code` e' una valuta di sistema o una valuta custom di
    QUESTO workspace — stesso criterio di visibilita' di `GET /currencies`
    (RLS + filtro applicativo esplicito)."""
    result = await db.execute(
        select(Currency.code).where(
            Currency.code == code.upper(),
            or_(Currency.workspace_id.is_(None), Currency.workspace_id == workspace_id),
        )
    )
    return result.scalar_one_or_none() is not None
