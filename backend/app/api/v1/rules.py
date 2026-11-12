import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_current_workspace_id
from app.db.session import get_db
from app.models.category import Category
from app.models.rule import Rule
from app.models.user import User
from app.schemas.rules import (
    RuleCreate,
    RuleOut,
    RulePreviewItem,
    RulePreviewOut,
    RulePreviewRequest,
    RuleSuggestion,
    RuleUpdate,
    SuggestionOption,
)
from app.services.audit_log_service import log_event
from app.services.rule_loader import load_active_rule_specs
from app.services.rule_preview_calc import build_preview
from app.services.rule_preview_service import (
    MAX_SUGGESTION_POOL,
    load_corrected_transactions,
    load_preview_transactions,
)
from app.services.rule_suggestion_calc import build_suggestions
from app.services.rules_engine import Condition, conditions_from_json

router = APIRouter(prefix="/rules", tags=["rules"])



def _conditions_json(payload_conditions) -> list[dict]:
    """Condizioni validate -> JSON per la colonna JSONB (Decimal come stringa)."""
    return [c.model_dump(mode="json") for c in payload_conditions]


def _engine_conditions(payload_conditions) -> tuple[Condition, ...]:
    return conditions_from_json(_conditions_json(payload_conditions))


async def _get_rule_or_404(db: AsyncSession, workspace_id: uuid.UUID, rule_id: uuid.UUID) -> Rule:
    rule = await db.get(Rule, rule_id)
    if rule is None or rule.workspace_id != workspace_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Rule not found")
    return rule


@router.get("", response_model=list[RuleOut])
async def list_rules(
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> list[Rule]:
    result = await db.execute(
        select(Rule).where(Rule.workspace_id == workspace_id).order_by(Rule.priority, Rule.name)
    )
    return list(result.scalars().all())


@router.post("", response_model=RuleOut, status_code=status.HTTP_201_CREATED)
async def create_rule(
    payload: RuleCreate,
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Rule:
    data = payload.model_dump(exclude={"conditions"})
    rule = Rule(workspace_id=workspace_id, conditions=_conditions_json(payload.conditions), **data)
    db.add(rule)
    try:
        await db.flush()
        await log_event(db, workspace_id, user.id, "RULE_CREATED", entity_type="rule", entity_id=rule.id)
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid category_id") from exc
    return rule


@router.post("/preview", response_model=RulePreviewOut)
async def preview_rule(
    payload: RulePreviewRequest,
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> RulePreviewOut:
    """Impatto di una regola NON salvata sui movimenti del workspace, con la
    stessa semantica del motore: quali cambierebbero categoria, quali sono gia'
    giusti, quali sono protetti da una correzione manuale. Nessuna scrittura."""
    category = await db.get(Category, payload.category_id)
    if category is None or (category.workspace_id is not None and category.workspace_id != workspace_id):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid category_id")
    transactions, truncated = await load_preview_transactions(db, workspace_id)
    result = build_preview(
        _engine_conditions(payload.conditions),
        payload.match_mode,
        payload.category_id,
        transactions,
        group=payload.group,
        limit=payload.limit,
        offset=payload.offset,
    )
    return RulePreviewOut(
        would_change=result.would_change,
        already_correct=result.already_correct,
        protected=result.protected,
        recategorized=result.recategorized,
        total=result.would_change + result.already_correct + result.protected,
        group=payload.group,
        truncated=truncated,
        items=[
            RulePreviewItem(
                id=m.tx.id,
                date=m.tx.transaction_date.isoformat(),
                amount=m.tx.amount,
                currency=m.tx.currency,
                description=m.tx.text,
                category_id=m.tx.category_id,
                group=m.group,
                spans=[(start, end) for start, end in m.spans],
            )
            for m in result.matches
        ],
    )


@router.get("/suggestions", response_model=list[RuleSuggestion])
async def list_rule_suggestions(
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> list[RuleSuggestion]:
    """Regole proposte dalle correzioni ripetute dell'utente (SPEC §29),
    calcolate al volo — nessuno stato persistito. Per ogni gruppo di correzioni
    nella stessa categoria si cercano le frasi stabili (senza numeri) e si
    propongono fino a tre opzioni con il relativo impatto. Una correzione gia'
    coperta da una regola attiva non produce suggerimenti."""
    corrected = await load_corrected_transactions(db, workspace_id)
    if not corrected:
        return []
    pool, _ = await load_preview_transactions(db, workspace_id, limit=MAX_SUGGESTION_POOL)
    active_rules = await load_active_rule_specs(db, workspace_id)
    calculated = build_suggestions(corrected, pool, active_rules)
    return [
        RuleSuggestion(
            category_id=item.category_id,
            occurrences=len(item.transaction_ids),
            transaction_ids=list(item.transaction_ids),
            label=item.label,
            ambiguous=item.ambiguous,
            options=[
                SuggestionOption(
                    key=option.key,
                    conditions=[_condition_out(c) for c in option.conditions],
                    match_mode=option.match_mode,
                    would_change=option.would_change,
                    already_correct=option.already_correct,
                    protected=option.protected,
                )
                for option in item.options
            ],
        )
        for item in calculated
    ]


def _condition_out(condition: Condition) -> dict:
    if condition.field == "amount":
        return {
            "field": "amount",
            "operator": "between",
            "min": condition.min_amount,
            "max": condition.max_amount,
        }
    return {"field": condition.field, "operator": condition.operator, "value": condition.value}


@router.get("/{rule_id}", response_model=RuleOut)
async def get_rule(
    rule_id: uuid.UUID,
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> Rule:
    return await _get_rule_or_404(db, workspace_id, rule_id)


@router.patch("/{rule_id}", response_model=RuleOut)
async def update_rule(
    rule_id: uuid.UUID,
    payload: RuleUpdate,
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Rule:
    rule = await _get_rule_or_404(db, workspace_id, rule_id)
    changes = payload.model_dump(exclude_unset=True, exclude={"conditions"})
    if payload.conditions is not None:
        changes["conditions"] = _conditions_json(payload.conditions)
    for field, value in changes.items():
        setattr(rule, field, value)
    try:
        await log_event(db, workspace_id, user.id, "RULE_UPDATED", entity_type="rule", entity_id=rule.id)
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid category_id") from exc
    return rule


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rule(
    rule_id: uuid.UUID,
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> None:
    rule = await _get_rule_or_404(db, workspace_id, rule_id)
    await db.delete(rule)
    await db.commit()
