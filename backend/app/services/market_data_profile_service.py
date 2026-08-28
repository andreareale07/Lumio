"""Logica DB-aware dei profili MarketDataProvider di workspace (SPEC §38),
ponte tra l'API (`app/api/v1/settings_market_data.py`) e il modello
`MarketDataProfile` + la factory `app/marketdata/registry.py` — stessa
separazione di `ai_profile_service.py` per i profili AI (M07).
"""
import uuid

from sqlalchemy import select
from sqlalchemy import update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import encrypt_secret
from app.models.market_data_profile import MarketDataProfile
from app.schemas.market_data import MarketDataProfileCreate, MarketDataProfileUpdate


async def list_profiles(db: AsyncSession, workspace_id: uuid.UUID) -> list[MarketDataProfile]:
    result = await db.execute(
        select(MarketDataProfile)
        .where(MarketDataProfile.workspace_id == workspace_id)
        .order_by(MarketDataProfile.created_at)
    )
    return list(result.scalars().all())


async def get_active_profile(db: AsyncSession, workspace_id: uuid.UUID) -> MarketDataProfile | None:
    result = await db.execute(
        select(MarketDataProfile).where(
            MarketDataProfile.workspace_id == workspace_id, MarketDataProfile.is_active.is_(True)
        )
    )
    return result.scalar_one_or_none()


def validate_connection_prerequisites(provider: str, endpoint: str | None) -> None:
    """Requisiti minimi per POTER TENTARE una chiamata al provider (test
    connessione): `manual`/`stooq`/`yahoo` non richiedono nulla (endpoint
    fisso o nessun fetch), solo `custom` richiede un endpoint configurato."""
    if provider == "custom" and not endpoint:
        raise ValueError("endpoint richiesto per il provider custom")


def validate_profile_config(provider: str, endpoint: str | None, price_field: str | None) -> None:
    """Requisiti completi per SALVARE un profilo: in piu' rispetto a
    `validate_connection_prerequisites`, `custom` richiede anche il percorso
    per estrarre il prezzo dalla risposta (senza non saprebbe mai come
    interpretarla, anche se l'endpoint risponde)."""
    validate_connection_prerequisites(provider, endpoint)
    if provider == "custom" and not price_field:
        raise ValueError("price_field richiesto per il provider custom")


def build_new_profile(workspace_id: uuid.UUID, payload: MarketDataProfileCreate) -> MarketDataProfile:
    validate_profile_config(payload.provider, payload.endpoint, payload.price_field)
    return MarketDataProfile(
        workspace_id=workspace_id,
        name=payload.name,
        provider=payload.provider,
        endpoint=payload.endpoint,
        api_key_encrypted=encrypt_secret(payload.api_key) if payload.api_key else None,
        price_field=payload.price_field,
        currency_field=payload.currency_field,
        portfolio_refresh_interval_seconds=payload.portfolio_refresh_interval_seconds,
        detail_refresh_interval_seconds=payload.detail_refresh_interval_seconds,
        is_active=False,
    )


def apply_profile_update(profile: MarketDataProfile, payload: MarketDataProfileUpdate) -> None:
    updates = payload.model_dump(exclude_unset=True, exclude={"api_key"})
    for field, value in updates.items():
        setattr(profile, field, value)

    validate_profile_config(profile.provider, profile.endpoint, profile.price_field)

    if payload.api_key is not None:
        profile.api_key_encrypted = encrypt_secret(payload.api_key) if payload.api_key else None


async def activate_profile(db: AsyncSession, profile: MarketDataProfile) -> None:
    """Mutua esclusivita' applicativa in aggiunta all'indice UNIQUE parziale
    a livello DB — stesso pattern di `ai_profile_service.activate_profile`:
    bulk update sugli ALTRI profili, poi si muta l'attributo Python
    dell'oggetto richiesto (mai un secondo bulk update, che non passerebbe
    per l'identity map ORM)."""
    await db.execute(
        sa_update(MarketDataProfile)
        .where(MarketDataProfile.workspace_id == profile.workspace_id, MarketDataProfile.id != profile.id)
        .values(is_active=False)
    )
    profile.is_active = True


async def deactivate_all_profiles(db: AsyncSession, workspace_id: uuid.UUID) -> None:
    await db.execute(
        sa_update(MarketDataProfile)
        .where(MarketDataProfile.workspace_id == workspace_id)
        .values(is_active=False)
    )
