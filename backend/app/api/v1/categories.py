import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_current_workspace_id
from app.db.session import get_db
from app.models.category import Category
from app.models.user import User
from app.schemas.categories import CategoryCreate, CategoryOut, CategoryUpdate
from app.services.audit_log_service import log_event

router = APIRouter(prefix="/categories", tags=["categories"])


async def _get_writable_category_or_404(
    db: AsyncSession, workspace_id: uuid.UUID, category_id: uuid.UUID
) -> Category:
    category = await db.get(Category, category_id)
    if category is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Category not found")
    # Il controllo su is_system va prima di quello sul workspace: una system
    # category ha workspace_id NULL (mai uguale a nessun workspace_id reale),
    # quindi confrontarla per prima darebbe sempre 404 invece del 403 corretto.
    if category.is_system:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "System categories cannot be modified")
    if category.workspace_id != workspace_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Category not found")
    return category


@router.get("", response_model=list[CategoryOut])
async def list_categories(
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> list[Category]:
    result = await db.execute(
        select(Category)
        .where(or_(Category.workspace_id.is_(None), Category.workspace_id == workspace_id))
        .order_by(Category.sort_order, Category.name)
    )
    return list(result.scalars().all())


@router.post("", response_model=CategoryOut, status_code=status.HTTP_201_CREATED)
async def create_category(
    payload: CategoryCreate,
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Category:
    category = Category(workspace_id=workspace_id, **payload.model_dump())
    db.add(category)
    try:
        await db.flush()
        await log_event(
            db, workspace_id, user.id, "CATEGORY_CHANGED",
            entity_type="category", entity_id=category.id, metadata={"action": "created"},
        )
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid parent category") from exc
    return category


@router.patch("/{category_id}", response_model=CategoryOut)
async def update_category(
    category_id: uuid.UUID,
    payload: CategoryUpdate,
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Category:
    category = await _get_writable_category_or_404(db, workspace_id, category_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(category, field, value)
    try:
        await log_event(
            db, workspace_id, user.id, "CATEGORY_CHANGED",
            entity_type="category", entity_id=category.id, metadata={"action": "updated"},
        )
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid parent category") from exc
    return category


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_category(
    category_id: uuid.UUID,
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    category = await _get_writable_category_or_404(db, workspace_id, category_id)
    deleted_category_id = category.id
    await db.delete(category)
    try:
        await log_event(
            db, workspace_id, user.id, "CATEGORY_CHANGED",
            entity_type="category", entity_id=deleted_category_id, metadata={"action": "deleted"},
        )
        await db.commit()
    except IntegrityError as exc:
        # category_id ha una FK semplice (non composita) verso categories,
        # senza ondelete: cancellare una categoria gia' usata da transazioni
        # o da una sotto-categoria violerebbe il vincolo. Meglio guidare
        # l'utente verso la disattivazione (is_active=false, gia' supportata)
        # che un 500 non gestito.
        await db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Categoria in uso da transazioni o sotto-categorie: disattivala invece di eliminarla",
        ) from exc
