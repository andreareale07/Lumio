import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.base import AIClassifier, AIProviderError
from app.ai.registry import build_classifier
from app.api.deps import get_current_user, get_current_workspace_id
from app.core.crypto import encrypt_secret
from app.db.session import get_db
from app.models.ai_profile import AIProfile
from app.models.user import User
from app.schemas.ai_settings import (
    AIConnectionCheckRequest,
    AIModelListResult,
    AIProfileCreate,
    AIProfileOut,
    AIProfileUpdate,
    AITestConnectionResult,
)
from app.services.ai_profile_service import (
    activate_profile,
    apply_profile_update,
    build_new_profile,
    deactivate_all_profiles,
    list_profiles,
    validate_connection_prerequisites,
)
from app.services.audit_log_service import log_event

router = APIRouter(prefix="/settings/ai", tags=["ai"])


def _to_out(profile: AIProfile) -> AIProfileOut:
    return AIProfileOut(
        id=profile.id,
        name=profile.name,
        provider=profile.provider,
        endpoint=profile.endpoint,
        model=profile.model,
        api_key_set=profile.api_key_encrypted is not None,
        is_active=profile.is_active,
        created_at=profile.created_at,
        updated_at=profile.updated_at,
    )


async def _get_profile_or_404(
    db: AsyncSession, workspace_id: uuid.UUID, profile_id: uuid.UUID
) -> AIProfile:
    profile = await db.get(AIProfile, profile_id)
    if profile is None or profile.workspace_id != workspace_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "AI profile not found")
    return profile


@router.get("/profiles", response_model=list[AIProfileOut])
async def get_ai_profiles(
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> list[AIProfileOut]:
    profiles = await list_profiles(db, workspace_id)
    return [_to_out(p) for p in profiles]


@router.post("/profiles", response_model=AIProfileOut, status_code=status.HTTP_201_CREATED)
async def create_ai_profile(
    payload: AIProfileCreate,
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> AIProfileOut:
    try:
        profile = build_new_profile(workspace_id, payload)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    db.add(profile)
    await db.commit()
    return _to_out(profile)


@router.patch("/profiles/{profile_id}", response_model=AIProfileOut)
async def update_ai_profile(
    profile_id: uuid.UUID,
    payload: AIProfileUpdate,
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> AIProfileOut:
    profile = await _get_profile_or_404(db, workspace_id, profile_id)
    try:
        apply_profile_update(profile, payload)
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    await db.commit()
    return _to_out(profile)


@router.delete("/profiles/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_ai_profile(
    profile_id: uuid.UUID,
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> None:
    profile = await _get_profile_or_404(db, workspace_id, profile_id)
    await db.delete(profile)
    await db.commit()


@router.post("/profiles/{profile_id}/activate", response_model=AIProfileOut)
async def activate_ai_profile(
    profile_id: uuid.UUID,
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AIProfileOut:
    profile = await _get_profile_or_404(db, workspace_id, profile_id)
    await activate_profile(db, profile)
    await log_event(
        db, workspace_id, user.id, "AI_PROVIDER_CHANGED",
        entity_type="ai_profile", entity_id=profile.id,
        metadata={"provider": profile.provider, "action": "activated"},
    )
    await db.commit()
    return _to_out(profile)


@router.post("/deactivate", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_ai(
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    await deactivate_all_profiles(db, workspace_id)
    await log_event(
        db, workspace_id, user.id, "AI_PROVIDER_CHANGED",
        entity_type="ai_profile", entity_id=None, metadata={"action": "deactivated"},
    )
    await db.commit()


@router.post("/profiles/{profile_id}/test", response_model=AITestConnectionResult)
async def test_saved_ai_profile(
    profile_id: uuid.UUID,
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> AITestConnectionResult:
    profile = await _get_profile_or_404(db, workspace_id, profile_id)
    classifier = build_classifier(profile)
    try:
        await classifier.test_connection()
    except AIProviderError as exc:
        return AITestConnectionResult(success=False, message=str(exc))
    return AITestConnectionResult(success=True, message="Connessione riuscita")


@router.post("/profiles/{profile_id}/models", response_model=AIModelListResult)
async def list_saved_ai_profile_models(
    profile_id: uuid.UUID,
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> AIModelListResult:
    profile = await _get_profile_or_404(db, workspace_id, profile_id)
    classifier = build_classifier(profile)
    return await _list_models_result(classifier)


@router.post("/test", response_model=AITestConnectionResult)
async def test_draft_ai_profile(payload: AIConnectionCheckRequest) -> AITestConnectionResult:
    """Verifica un profilo NON ANCORA salvato (in creazione): a differenza
    di `/profiles/{id}/test`, la API key deve essere fornita direttamente
    nel payload — non esiste ancora una chiave salvata da riusare."""
    try:
        validate_connection_prerequisites(payload.provider, payload.endpoint, bool(payload.api_key))
    except ValueError as exc:
        return AITestConnectionResult(success=False, message=str(exc))

    transient = _transient_profile(payload)
    classifier = build_classifier(transient)
    try:
        await classifier.test_connection()
    except AIProviderError as exc:
        return AITestConnectionResult(success=False, message=str(exc))
    return AITestConnectionResult(success=True, message="Connessione riuscita")


@router.post("/models", response_model=AIModelListResult)
async def list_draft_ai_profile_models(payload: AIConnectionCheckRequest) -> AIModelListResult:
    try:
        validate_connection_prerequisites(payload.provider, payload.endpoint, bool(payload.api_key))
    except ValueError as exc:
        return AIModelListResult(success=False, models=[], message=str(exc))

    transient = _transient_profile(payload)
    classifier = build_classifier(transient)
    return await _list_models_result(classifier)


def _transient_profile(payload: AIConnectionCheckRequest) -> AIProfile:
    return AIProfile(
        provider=payload.provider,
        endpoint=payload.endpoint,
        model=payload.model,
        api_key_encrypted=encrypt_secret(payload.api_key) if payload.api_key else None,
    )


async def _list_models_result(classifier: AIClassifier) -> AIModelListResult:
    try:
        models = await classifier.list_models()
    except AIProviderError as exc:
        return AIModelListResult(success=False, models=[], message=str(exc))
    if not models:
        return AIModelListResult(
            success=True, models=[], message="Il provider non ha restituito nessun modello."
        )
    return AIModelListResult(success=True, models=models, message=f"{len(models)} modelli trovati.")
