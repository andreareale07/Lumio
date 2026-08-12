"""Registrazione eventi di audit (SPEC §59). Nessun commit qui — come gli
altri service DB-aware del progetto (`ai_profile_service`, ecc.), il
chiamante decide quando accodare l'INSERT alla propria transazione.

Va chiamato SOLO mentre `app.current_user_id` e' impostato sulla sessione
(RLS): se il punto di chiamata e' subito dopo un `db.commit()` sulla stessa
sessione, l'identita' e' scaduta (vedi app/db/rls.py) e la policy INSERT
nega silenziosamente — richiamare `set_rls_current_user` prima di loggare.
"""
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog


async def log_event(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID | None,
    event_type: str,
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
    metadata: dict | None = None,
) -> None:
    db.add(
        AuditLog(
            workspace_id=workspace_id,
            user_id=user_id,
            event_type=event_type,
            entity_type=entity_type,
            entity_id=entity_id,
            event_metadata=metadata,
        )
    )
