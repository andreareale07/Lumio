import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_current_workspace_id
from app.db.session import get_db
from app.models.category import Category
from app.models.user import User
from app.schemas.categories import CategoryCreate, CategoryKind, CategoryOut, CategoryUpdate
from app.services.audit_log_service import log_event
from app.services.category_service import (
    CategoryValidationError,
    generate_code,
    validate_kind_matches_parent,
    validate_no_children_before_becoming_child,
    validate_parent_depth,
)

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
    kind: CategoryKind | None = None,
    is_active: bool | None = None,
    roots_only: bool = False,
    q: str | None = Query(default=None, min_length=1, max_length=100),
    db: AsyncSession = Depends(get_db),
) -> list[Category]:
    query = select(Category).where(
        or_(Category.workspace_id.is_(None), Category.workspace_id == workspace_id)
    )
    if kind is not None:
        query = query.where(Category.kind == kind)
    if is_active is not None:
        query = query.where(Category.is_active == is_active)
    if roots_only:
        query = query.where(Category.parent_id.is_(None))
    if q is not None:
        # name+code, case-insensitive: l'utente cerca sia per etichetta
        # ("Carburante") sia per lo slug che potrebbe aver visto altrove
        # ("trasporti.carburante").
        like_pattern = f"%{q.lower()}%"
        query = query.where(
            or_(Category.name.ilike(like_pattern), Category.code.ilike(like_pattern))
        )
    result = await db.execute(query.order_by(Category.sort_order, Category.name))
    return list(result.scalars().all())


@router.post("", response_model=CategoryOut, status_code=status.HTTP_201_CREATED)
async def create_category(
    payload: CategoryCreate,
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Category:
    parent: Category | None = None
    if payload.parent_id is not None:
        parent = await db.get(Category, payload.parent_id)
        if parent is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid parent category")

    try:
        validate_parent_depth(parent)
        resolved_kind = validate_kind_matches_parent(payload.kind, parent)
        code = await generate_code(db, workspace_id, payload.name, parent)
    except CategoryValidationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc

    category = Category(
        workspace_id=workspace_id,
        parent_id=payload.parent_id,
        name=payload.name,
        code=code,
        kind=resolved_kind,
        sort_order=payload.sort_order,
    )
    db.add(category)
    try:
        await db.flush()
        await log_event(
            db, workspace_id, user.id, "CATEGORY_CHANGED",
            entity_type="category", entity_id=category.id, metadata={"action": "created"},
        )
        await db.commit()
    except IntegrityError as exc:
        # Rete di sicurezza contro una race tra generate_code() e
        # l'INSERT vero e proprio (finestra minima tra la verifica di
        # unicita' e la scrittura) — il trigger anti-shadowing/gli indici
        # unici parziali (migration 0021) restano l'ultima difesa reale.
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
    updates = payload.model_dump(exclude_unset=True)

    try:
        parent_changing = "parent_id" in updates and updates["parent_id"] != category.parent_id
        new_parent: Category | None = None
        if parent_changing:
            new_parent_id = updates["parent_id"]
            await validate_no_children_before_becoming_child(db, category.id, new_parent_id)
            if new_parent_id is not None:
                new_parent = await db.get(Category, new_parent_id)
                if new_parent is None:
                    raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid parent category")
                validate_parent_depth(new_parent)
        else:
            new_parent = (
                await db.get(Category, category.parent_id) if category.parent_id is not None else None
            )

        # Kind: si eredita SEMPRE dal padre (nuovo o esistente) su un figlio;
        # su una radice resta quello esplicito in `updates`, altrimenti
        # INVARIATO (mai resettato silenziosamente a un default — a
        # differenza della creazione, qui una radice puo' gia' avere un
        # kind scelto in precedenza).
        if new_parent is not None:
            requested_kind = updates.get("kind")
            category.kind = validate_kind_matches_parent(requested_kind, new_parent)
        elif "kind" in updates:
            category.kind = updates["kind"]
        # altrimenti: nessuna modifica al kind esistente.

        if parent_changing:
            category.parent_id = updates["parent_id"]
            # Rinomina sola -> il code NON si rigenera (e' uno slug stabile,
            # vedi app/ai/base.py); un cambio di PADRE invece lo rigenera
            # sempre, altrimenti la dot-notation mentirebbe sulla gerarchia
            # reale.
            new_name = updates.get("name", category.name)
            category.code = await generate_code(db, workspace_id, new_name, new_parent)

        if "name" in updates:
            category.name = updates["name"]
        if "is_active" in updates:
            category.is_active = updates["is_active"]
        if "sort_order" in updates:
            category.sort_order = updates["sort_order"]
    except CategoryValidationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc

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
