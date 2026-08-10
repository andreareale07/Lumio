import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_workspace_id
from app.db.session import get_db
from app.models.import_mapping import ImportMapping
from app.schemas.imports import ImportMappingCreate, ImportMappingOut, ImportMappingUpdate

router = APIRouter(prefix="/import-mappings", tags=["import-mappings"])


async def _get_mapping_or_404(
    db: AsyncSession, workspace_id: uuid.UUID, mapping_id: uuid.UUID
) -> ImportMapping:
    mapping = await db.get(ImportMapping, mapping_id)
    if mapping is None or mapping.workspace_id != workspace_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Import mapping not found")
    return mapping


@router.post("", response_model=ImportMappingOut, status_code=status.HTTP_201_CREATED)
async def create_mapping(
    payload: ImportMappingCreate,
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> ImportMapping:
    mapping = ImportMapping(
        workspace_id=workspace_id,
        financial_account_id=payload.financial_account_id,
        name=payload.name,
        config=payload.config.model_dump(mode="json"),
    )
    db.add(mapping)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Nome mappatura gia' in uso o conto non valido"
        ) from exc
    return mapping


@router.get("", response_model=list[ImportMappingOut])
async def list_mappings(
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> list[ImportMapping]:
    result = await db.execute(
        select(ImportMapping)
        .where(ImportMapping.workspace_id == workspace_id)
        .order_by(ImportMapping.updated_at.desc())
    )
    return list(result.scalars().all())


@router.get("/{mapping_id}", response_model=ImportMappingOut)
async def get_mapping(
    mapping_id: uuid.UUID,
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> ImportMapping:
    return await _get_mapping_or_404(db, workspace_id, mapping_id)


@router.patch("/{mapping_id}", response_model=ImportMappingOut)
async def update_mapping(
    mapping_id: uuid.UUID,
    payload: ImportMappingUpdate,
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> ImportMapping:
    mapping = await _get_mapping_or_404(db, workspace_id, mapping_id)
    data = payload.model_dump(exclude_unset=True)
    if "config" in data and data["config"] is not None:
        data["config"] = payload.config.model_dump(mode="json")
    for field, value in data.items():
        setattr(mapping, field, value)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Nome mappatura gia' in uso o conto non valido"
        ) from exc
    return mapping


@router.delete("/{mapping_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_mapping(
    mapping_id: uuid.UUID,
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> None:
    mapping = await _get_mapping_or_404(db, workspace_id, mapping_id)
    await db.delete(mapping)
    await db.commit()
