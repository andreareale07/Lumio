import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_current_workspace_id
from app.core.crypto import encrypt_secret
from app.db.session import get_db
from app.marketdata.base import MarketDataProviderError
from app.marketdata.registry import build_provider
from app.models.market_data_profile import MarketDataProfile
from app.models.user import User
from app.schemas.market_data import (
    MarketDataConnectionCheckRequest,
    MarketDataProfileCreate,
    MarketDataProfileOut,
    MarketDataProfileUpdate,
    MarketDataRefreshTriggered,
    MarketDataTestConnectionResult,
)
from app.services.market_data_profile_service import (
    activate_profile,
    apply_profile_update,
    build_new_profile,
    deactivate_all_profiles,
    list_profiles,
    validate_connection_prerequisites,
)
from app.worker.queue import enqueue_market_data_refresh

router = APIRouter(prefix="/settings/market-data", tags=["market-data"])


def _to_out(profile: MarketDataProfile) -> MarketDataProfileOut:
    return MarketDataProfileOut(
        id=profile.id,
        name=profile.name,
        provider=profile.provider,
        endpoint=profile.endpoint,
        api_key_set=profile.api_key_encrypted is not None,
        price_field=profile.price_field,
        currency_field=profile.currency_field,
        is_active=profile.is_active,
        created_at=profile.created_at,
        updated_at=profile.updated_at,
    )


async def _get_profile_or_404(
    db: AsyncSession, workspace_id: uuid.UUID, profile_id: uuid.UUID
) -> MarketDataProfile:
    profile = await db.get(MarketDataProfile, profile_id)
    if profile is None or profile.workspace_id != workspace_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Market data profile not found")
    return profile


@router.get("/profiles", response_model=list[MarketDataProfileOut])
async def get_market_data_profiles(
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> list[MarketDataProfileOut]:
    profiles = await list_profiles(db, workspace_id)
    return [_to_out(p) for p in profiles]


@router.post("/profiles", response_model=MarketDataProfileOut, status_code=status.HTTP_201_CREATED)
async def create_market_data_profile(
    payload: MarketDataProfileCreate,
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> MarketDataProfileOut:
    try:
        profile = build_new_profile(workspace_id, payload)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    db.add(profile)
    await db.commit()
    return _to_out(profile)


@router.patch("/profiles/{profile_id}", response_model=MarketDataProfileOut)
async def update_market_data_profile(
    profile_id: uuid.UUID,
    payload: MarketDataProfileUpdate,
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> MarketDataProfileOut:
    profile = await _get_profile_or_404(db, workspace_id, profile_id)
    try:
        apply_profile_update(profile, payload)
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    await db.commit()
    return _to_out(profile)


@router.delete("/profiles/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_market_data_profile(
    profile_id: uuid.UUID,
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> None:
    profile = await _get_profile_or_404(db, workspace_id, profile_id)
    await db.delete(profile)
    await db.commit()


@router.post("/profiles/{profile_id}/activate", response_model=MarketDataProfileOut)
async def activate_market_data_profile(
    profile_id: uuid.UUID,
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> MarketDataProfileOut:
    profile = await _get_profile_or_404(db, workspace_id, profile_id)
    await activate_profile(db, profile)
    await db.commit()
    return _to_out(profile)


@router.post("/refresh", response_model=MarketDataRefreshTriggered, status_code=status.HTTP_202_ACCEPTED)
async def trigger_market_data_refresh(
    user: User = Depends(get_current_user),
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
) -> MarketDataRefreshTriggered:
    """Trigger manuale (DoD M09): accoda il job async invece di scaricare i
    prezzi nella request HTTP stessa (CLAUDE.md, "mai bloccare la request
    HTTP" per operazioni potenzialmente lunghe — il fetch di rete verso un
    provider esterno per ogni asset lo e'). Nessun canale SSE dedicato per
    questo job (vedi `MarketDataRefreshTriggered`): il frontend ri-esegue
    semplicemente le query dopo qualche secondo."""
    job_id = await enqueue_market_data_refresh(workspace_id, user.id)
    return MarketDataRefreshTriggered(job_id=job_id)


@router.post("/deactivate", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_market_data(
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> None:
    await deactivate_all_profiles(db, workspace_id)
    await db.commit()


@router.post("/profiles/{profile_id}/test", response_model=MarketDataTestConnectionResult)
async def test_saved_market_data_profile(
    profile_id: uuid.UUID,
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> MarketDataTestConnectionResult:
    profile = await _get_profile_or_404(db, workspace_id, profile_id)
    provider = build_provider(profile)
    try:
        await provider.test_connection()
    except MarketDataProviderError as exc:
        return MarketDataTestConnectionResult(success=False, message=str(exc))
    return MarketDataTestConnectionResult(success=True, message="Connessione riuscita")


@router.post("/test", response_model=MarketDataTestConnectionResult)
async def test_draft_market_data_profile(
    payload: MarketDataConnectionCheckRequest,
) -> MarketDataTestConnectionResult:
    """Verifica un profilo NON ANCORA salvato — vedi
    `/settings/ai/test` per lo stesso pattern lato AI (M07)."""
    try:
        validate_connection_prerequisites(payload.provider, payload.endpoint)
    except ValueError as exc:
        return MarketDataTestConnectionResult(success=False, message=str(exc))

    profile = _transient_profile(payload)
    provider = build_provider(profile)
    try:
        await provider.test_connection()
    except MarketDataProviderError as exc:
        return MarketDataTestConnectionResult(success=False, message=str(exc))
    return MarketDataTestConnectionResult(success=True, message="Connessione riuscita")


def _transient_profile(payload: MarketDataConnectionCheckRequest) -> MarketDataProfile:
    return MarketDataProfile(
        provider=payload.provider,
        endpoint=payload.endpoint,
        api_key_encrypted=encrypt_secret(payload.api_key) if payload.api_key else None,
        price_field=payload.price_field,
        currency_field=payload.currency_field,
    )
