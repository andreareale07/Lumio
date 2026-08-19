import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_workspace_id
from app.db.session import get_db
from app.models.currency import Currency
from app.schemas.currencies import CurrencyOut, FxRateManualUpsert, FxRateOut
from app.services import fx_rate_service

router = APIRouter(prefix="/currencies", tags=["currencies"])


@router.get("", response_model=list[CurrencyOut])
async def list_currencies(
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> list[Currency]:
    # RLS gia' restringe alle sole righe visibili (workspace_id IS NULL o
    # di questo workspace) — filtro applicativo esplicito comunque presente
    # per coerenza con `categories.py` (CLAUDE.md: isolamento sempre a
    # doppio livello, mai fidarsi solo della RLS).
    query = select(Currency).where(
        or_(Currency.workspace_id.is_(None), Currency.workspace_id == workspace_id)
    )
    result = await db.execute(query.order_by(Currency.code))
    return list(result.scalars().all())


@router.put("/rates", response_model=FxRateOut)
async def upsert_manual_fx_rate(
    payload: FxRateManualUpsert,
    db: AsyncSession = Depends(get_db),
) -> FxRateOut:
    """Inserimento manuale di un tasso di cambio (SPEC sistema di valute,
    stesso principio di `PUT /assets/{id}/prices`) — SEMPRE disponibile,
    indipendentemente dal market data provider attivo. Nessun controllo di
    ownership qui: `fx_rates` e' una tabella globale senza `workspace_id`
    (vedi `app/models/fx_rate.py`), un tasso di cambio non appartiene a un
    singolo workspace."""
    from_currency = payload.from_currency.upper()
    to_currency = payload.to_currency.upper()
    row = await fx_rate_service.upsert_rate(
        db, from_currency, to_currency, payload.rate_date, payload.rate, "manual"
    )
    # flush+refresh PRIMA del commit (stesso principio di
    # upsert_manual_asset_price: normalizza `rate` alla scala NUMERIC della
    # colonna prima di rispondere).
    await db.flush()
    await db.refresh(row)
    await db.commit()
    return row
