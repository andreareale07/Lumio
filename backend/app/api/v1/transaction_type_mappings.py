"""API per la mappatura tipi transazione configurabile per parser
(milestone 09.5) — vedi app/services/transaction_type_mapping_service.py
per il design (default del parser come fallback, rimappatura retroattiva
che salta le correzioni manuali).
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_workspace_id
from app.db.session import get_db
from app.schemas.transaction_type_mappings import (
    LabelOut,
    MappingUpsert,
    MappingUpsertResult,
    ReapplyResultOut,
    TypeCountOut,
)
from app.services.transaction_type_mapping_service import (
    delete_mapping,
    list_observed_labels,
    list_used_parser_types,
    reapply_mapping,
    upsert_mapping,
)

router = APIRouter(prefix="/settings/transaction-types", tags=["transaction-types"])


@router.get("/parsers", response_model=list[str])
async def get_used_parser_types(
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> list[str]:
    return await list_used_parser_types(db, workspace_id)


@router.get("/{parser_type}/labels", response_model=list[LabelOut])
async def get_observed_labels(
    parser_type: str,
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> list[LabelOut]:
    labels = await list_observed_labels(db, workspace_id, parser_type)
    return [
        LabelOut(
            source_type_raw=label.source_type_raw,
            total_count=label.total_count,
            current_types=[
                TypeCountOut(transaction_type=tc.transaction_type, count=tc.count) for tc in label.current_types
            ],
            override=label.override,
        )
        for label in labels
    ]


@router.put("/{parser_type}/labels/{source_type_raw}", response_model=MappingUpsertResult)
async def put_label_mapping(
    parser_type: str,
    source_type_raw: str,
    payload: MappingUpsert,
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> MappingUpsertResult:
    """Salva l'override e lo applica SUBITO anche alle transazioni gia'
    importate con questa etichetta (rimappatura retroattiva, sincrona) —
    e' il momento in cui l'utente si aspetta la correzione, non serve
    aspettare un prossimo import."""
    await upsert_mapping(db, workspace_id, parser_type, source_type_raw, payload.transaction_type)
    reapply_result = await reapply_mapping(
        db, workspace_id, parser_type, source_type_raw, payload.transaction_type
    )
    await db.commit()
    return MappingUpsertResult(
        source_type_raw=source_type_raw,
        transaction_type=payload.transaction_type,
        reapply=ReapplyResultOut(updated=reapply_result.updated, skipped=reapply_result.skipped),
    )


@router.delete("/{parser_type}/labels/{source_type_raw}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_label_mapping(
    parser_type: str,
    source_type_raw: str,
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> None:
    deleted = await delete_mapping(db, workspace_id, parser_type, source_type_raw)
    if not deleted:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nessun override salvato per questa etichetta")
    await db.commit()
