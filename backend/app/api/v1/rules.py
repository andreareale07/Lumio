import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_current_workspace_id
from app.db.session import get_db
from app.models.classification import Classification
from app.models.rule import Rule
from app.models.transaction import Transaction
from app.models.user import User
from app.schemas.rules import RuleCreate, RuleOut, RuleSuggestion, RuleUpdate
from app.services.audit_log_service import log_event
from app.services.rule_loader import load_active_rule_specs
from app.services.rules_engine import Probe, evaluate

router = APIRouter(prefix="/rules", tags=["rules"])

# Soglia minima di correzioni ripetute (SPEC §29) prima di proporre una
# regola automatica — scelta minore, documentata nel piano di M06.
_SUGGESTION_THRESHOLD = 2


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
    rule = Rule(workspace_id=workspace_id, **payload.model_dump())
    db.add(rule)
    try:
        await db.flush()
        await log_event(db, workspace_id, user.id, "RULE_CREATED", entity_type="rule", entity_id=rule.id)
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid category_id") from exc
    return rule


@router.get("/suggestions", response_model=list[RuleSuggestion])
async def list_rule_suggestions(
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> list[RuleSuggestion]:
    """Regole proposte dalle correzioni ripetute dell'utente (SPEC §29),
    calcolate al volo — nessuno stato persistito, vedi decisione documentata
    nel piano di M06. Una regola gia' attiva che copre la stessa coppia
    (campo/valore -> categoria) esclude la proposta corrispondente.
    """
    result = await db.execute(
        select(
            Classification.category_id,
            Classification.transaction_id,
            Transaction.merchant,
            Transaction.description_normalized,
            Transaction.description_raw,
        )
        .join(Transaction, Transaction.id == Classification.transaction_id)
        .where(Transaction.workspace_id == workspace_id, Classification.method == "user")
    )

    groups: dict[tuple[str, str, uuid.UUID], dict] = {}
    for category_id, transaction_id, merchant, description_normalized, description_raw in result.all():
        if category_id is None:
            continue
        if merchant:
            field, display_value = "merchant", merchant
        else:
            field, display_value = "description", (description_normalized or description_raw)
        key = (field, display_value.strip().lower(), category_id)
        group = groups.setdefault(
            key, {"display_value": display_value.strip(), "transaction_ids": []}
        )
        group["transaction_ids"].append(transaction_id)

    active_rules = await load_active_rule_specs(db, workspace_id)

    suggestions: list[RuleSuggestion] = []
    for (field, _value_lower, category_id), group in groups.items():
        transaction_ids = group["transaction_ids"]
        if len(transaction_ids) < _SUGGESTION_THRESHOLD:
            continue
        display_value = group["display_value"]
        probe = Probe(
            description_raw=display_value,
            description_normalized=display_value,
            merchant=display_value if field == "merchant" else None,
        )
        if evaluate(active_rules, probe) == category_id:
            continue  # gia' coperta da una regola attiva
        suggestions.append(
            RuleSuggestion(
                match_field=field,
                match_value=display_value,
                category_id=category_id,
                occurrences=len(transaction_ids),
                transaction_ids=transaction_ids,
            )
        )
    return suggestions


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
    for field, value in payload.model_dump(exclude_unset=True).items():
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
