"""Logica DB-aware per i profili AI di workspace (SPEC §25-28), ponte tra
l'API (`app/api/v1/settings_ai.py`) e il modello `AIProfile` + la factory
`app/ai/registry.py` — stessa separazione gia' usata da `rule_loader.py`
per le regole.
"""
import uuid

from sqlalchemy import select
from sqlalchemy import update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import encrypt_secret
from app.models.ai_profile import AIProfile
from app.schemas.ai_settings import AIProfileCreate, AIProfileUpdate


async def list_profiles(db: AsyncSession, workspace_id: uuid.UUID) -> list[AIProfile]:
    result = await db.execute(
        select(AIProfile).where(AIProfile.workspace_id == workspace_id).order_by(AIProfile.created_at)
    )
    return list(result.scalars().all())


async def get_active_profile(db: AsyncSession, workspace_id: uuid.UUID) -> AIProfile | None:
    result = await db.execute(
        select(AIProfile).where(AIProfile.workspace_id == workspace_id, AIProfile.is_active.is_(True))
    )
    return result.scalar_one_or_none()


def validate_connection_prerequisites(provider: str, endpoint: str | None, has_api_key: bool) -> None:
    """Requisiti minimi per POTER TENTARE una chiamata al provider (test
    connessione, elenco modelli): mai `model`, che serve solo a scegliere
    COSA classificare, non a raggiungere il provider — richiederlo qui
    creerebbe un problema dell'uovo e della gallina per l'elenco modelli
    (SPEC §26: l'utente deve poter scoprire i modelli disponibili PRIMA di
    sceglierne uno)."""
    if provider in ("ollama", "custom") and not endpoint:
        raise ValueError("endpoint richiesto per questo provider")
    if provider in ("openai", "anthropic") and not has_api_key:
        raise ValueError("API key richiesta per questo provider")


def validate_profile_config(provider: str, endpoint: str | None, model: str | None, has_api_key: bool) -> None:
    """Requisiti completi per SALVARE un profilo: in piu' rispetto a
    `validate_connection_prerequisites`, un modello scelto per Ollama (per
    OpenAI/Anthropic un default sensato e' gia' applicato dal provider
    stesso se `model` e' vuoto, vedi `app/ai/providers/openai.py` e
    `anthropic.py`)."""
    validate_connection_prerequisites(provider, endpoint, has_api_key)
    if provider == "ollama" and not model:
        raise ValueError("model richiesto per questo provider")


def build_new_profile(workspace_id: uuid.UUID, payload: AIProfileCreate) -> AIProfile:
    validate_profile_config(payload.provider, payload.endpoint, payload.model, bool(payload.api_key))
    return AIProfile(
        workspace_id=workspace_id,
        name=payload.name,
        provider=payload.provider,
        endpoint=payload.endpoint,
        model=payload.model,
        api_key_encrypted=encrypt_secret(payload.api_key) if payload.api_key else None,
        is_active=False,
    )


def apply_profile_update(profile: AIProfile, payload: AIProfileUpdate) -> None:
    updates = payload.model_dump(exclude_unset=True, exclude={"api_key"})
    for field, value in updates.items():
        setattr(profile, field, value)

    if payload.api_key is None:
        has_api_key = profile.api_key_encrypted is not None
    else:
        has_api_key = payload.api_key != ""

    validate_profile_config(profile.provider, profile.endpoint, profile.model, has_api_key)

    if payload.api_key is not None:
        profile.api_key_encrypted = encrypt_secret(payload.api_key) if payload.api_key else None


async def activate_profile(db: AsyncSession, profile: AIProfile) -> None:
    """Mutua esclusivita' applicativa (in aggiunta all'indice UNIQUE
    parziale a livello DB): un UPDATE bulk disattiva tutti gli ALTRI
    profili del workspace (mai due righe attive contemporaneamente, ne'
    anche per un istante, altrimenti l'indice parziale rifiuterebbe la
    seconda) — quello richiesto viene invece attivato mutando l'attributo
    Python, non con un secondo UPDATE bulk: un bulk update non passa per
    l'identity map ORM, quindi l'oggetto `profile' gia' caricato in memoria
    resterebbe stantio dopo il commit senza una query di refresh, che
    servirebbe pero' RLS gia' attiva (SET LOCAL scade al commit, vedi
    lumio-rls-gotchas) — mutare l'attributo evita del tutto il problema:
    SQLAlchemy lo traccia come dirty e lo scrive al prossimo flush/commit,
    nessuna query aggiuntiva necessaria.
    """
    await db.execute(
        sa_update(AIProfile)
        .where(AIProfile.workspace_id == profile.workspace_id, AIProfile.id != profile.id)
        .values(is_active=False)
    )
    profile.is_active = True


async def deactivate_all_profiles(db: AsyncSession, workspace_id: uuid.UUID) -> None:
    await db.execute(sa_update(AIProfile).where(AIProfile.workspace_id == workspace_id).values(is_active=False))
