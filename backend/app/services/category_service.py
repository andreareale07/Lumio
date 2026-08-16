"""Logica DB-aware delle categorie non gia' coperta dal solo ORM: generazione
server-side del `code` (rework tassonomia — prima il client lo generava,
senza prefisso del padre, rompendo la convenzione dot-notation del seed) e
validazione anti-ciclo/profondita' che integra i trigger DB (0021) con un
errore applicativo leggibile invece di un generico 500/IntegrityError.
"""
import re
import unicodedata
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.category import Category

_DIACRITICS_PATTERN = re.compile(r"[̀-ͯ]")
_NON_ALNUM_PATTERN = re.compile(r"[^a-z0-9]+")
_MAX_CODE_SUFFIX_ATTEMPTS = 50


def slugify(name: str) -> str:
    decomposed = unicodedata.normalize("NFD", name)
    without_diacritics = _DIACRITICS_PATTERN.sub("", decomposed)
    slug = _NON_ALNUM_PATTERN.sub("_", without_diacritics.lower()).strip("_")
    return slug or "categoria"


async def _code_exists(db: AsyncSession, workspace_id: uuid.UUID, code: str) -> bool:
    # Un code e' "occupato" se esiste gia' come categoria di sistema
    # (workspace_id NULL, visibile/riservato per tutti) o come categoria di
    # QUESTO workspace — stessa coppia di vincoli imposta dagli indici unici
    # parziali e dal trigger anti-shadowing (migration 0021).
    result = await db.execute(
        select(Category.id).where(
            Category.code == code,
            (Category.workspace_id.is_(None)) | (Category.workspace_id == workspace_id),
        )
    )
    return result.scalar_one_or_none() is not None


async def generate_code(db: AsyncSession, workspace_id: uuid.UUID, name: str, parent: Category | None) -> str:
    """Prefisso del padre + slug del nome, con suffisso numerico se occupato
    (`_2`, `_3`, ...) — mai un `IntegrityError` in condizioni normali, il
    trigger anti-shadowing (0021) resta comunque l'ultima difesa contro una
    race tra la verifica qui e l'INSERT vero e proprio."""
    slug = slugify(name)
    base = f"{parent.code}.{slug}" if parent is not None else slug

    candidate = base
    suffix = 1
    while await _code_exists(db, workspace_id, candidate):
        suffix += 1
        if suffix > _MAX_CODE_SUFFIX_ATTEMPTS:
            raise ValueError(f"impossibile generare un code univoco per {name!r} dopo {_MAX_CODE_SUFFIX_ATTEMPTS} tentativi")
        candidate = f"{base}_{suffix}"
    return candidate


class CategoryValidationError(ValueError):
    """Sollevato dalle validazioni sotto — il chiamante HTTP lo traduce in
    422, mai un generico 400/500 indistinguibile da un errore di
    integrita' del DB."""


def validate_parent_depth(parent: Category | None) -> None:
    """Profondita' fissa a 2 (SPEC + convenzione della tassonomia): un
    figlio non puo' a sua volta avere un padre — impedirebbe una gerarchia
    a 3 livelli che ne' `buildCategoryOptions` ne' `by_category`
    sanno gestire."""
    if parent is not None and parent.parent_id is not None:
        raise CategoryValidationError(
            "La categoria selezionata come padre è già una sottocategoria: "
            "non è possibile creare una gerarchia a più di due livelli."
        )


async def validate_no_children_before_becoming_child(
    db: AsyncSession, category_id: uuid.UUID, new_parent_id: uuid.UUID | None
) -> None:
    """Impedisce che una categoria con figli propri diventi a sua volta
    figlia di un'altra (creerebbe una gerarchia a 3 livelli dall'alto)."""
    if new_parent_id is None:
        return
    if new_parent_id == category_id:
        raise CategoryValidationError("Una categoria non può essere il padre di se stessa.")
    result = await db.execute(select(Category.id).where(Category.parent_id == category_id).limit(1))
    if result.scalar_one_or_none() is not None:
        raise CategoryValidationError(
            "Questa categoria ha già delle sottocategorie: non può diventare essa stessa una sottocategoria."
        )


def validate_kind_matches_parent(kind: str | None, parent: Category | None) -> str:
    """Il kind si eredita SEMPRE dal padre su un figlio (il trigger
    enforce_category_kind lo imporrebbe comunque a livello DB, ma un 422
    leggibile qui e' molto meglio di scoprirlo da un valore silenziosamente
    corretto dopo il fatto). Su una radice, `kind` esplicito o il default
    'expense'."""
    if parent is not None:
        if kind is not None and kind != parent.kind:
            raise CategoryValidationError(
                f"Il tipo (kind) si eredita dalla categoria padre ({parent.kind!r}): "
                "non può essere specificato diversamente su una sottocategoria."
            )
        return parent.kind
    return kind or "expense"
