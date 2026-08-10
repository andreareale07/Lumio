"""Ponte DB-aware tra il modello ORM `Rule` e il motore puro
`app/services/rules_engine.py` — stessa separazione gia' usata tra
`csv_import.py` (puro) e `import_job.py` (DB-aware). Condiviso tra il router
`rules.py` (suggestions), `transactions.py` (creazione/correzione) e il
worker import.
"""
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.rule import Rule
from app.services.rules_engine import RuleSpec


async def load_active_rule_specs(db: AsyncSession, workspace_id: uuid.UUID) -> list[RuleSpec]:
    result = await db.execute(
        select(Rule).where(Rule.workspace_id == workspace_id, Rule.is_active.is_(True))
    )
    return [
        RuleSpec(
            id=rule.id,
            field=rule.field,
            operator=rule.operator,
            value=rule.value,
            category_id=rule.category_id,
            priority=rule.priority,
            created_at=rule.created_at,
        )
        for rule in result.scalars().all()
    ]
