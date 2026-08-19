"""Risoluzione dello scope "quali conti" per gli endpoint analytics del
portfolio (SPEC §36/§37) — unico punto condiviso da `app/api/v1/
portfolios.py` e `app/api/v1/investment_transactions.py`, cosi' la logica
di sicurezza (un portfolio_id deve appartenere al workspace) non e'
duplicata in due router.

Tre scope possibili, mutuamente esclusivi:
- nessun filtro (`portfolio_id=None`, `unassigned=False`) -> `None`,
  significa "tutti i conti del workspace" (vista implicita, SPEC §36) —
  MAI "nessun conto".
- un portfolio nominato (`portfolio_id=<uuid>`) -> i conti collegati a
  quel `Portfolio` (404 se non esiste o non e' di questo workspace).
- `unassigned=True` -> i conti del workspace che non sono collegati a
  NESSUN `Portfolio` — usato dalla vista "Asset senza portfolio" (redesign
  Investimenti): un conto puo' stare in zero, uno o piu' portfolio,
  "unassigned" e' il complemento di "sta in almeno un portfolio", mai
  filtrato per `account_type` (una `Position` non e' mai vincolata al tipo
  di conto, vedi `position.py`).
"""
import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.financial_account import FinancialAccount
from app.models.portfolio import Portfolio
from app.models.portfolio_account import PortfolioAccount


async def get_portfolio_or_404(db: AsyncSession, workspace_id: uuid.UUID, portfolio_id: uuid.UUID) -> Portfolio:
    portfolio = await db.get(Portfolio, portfolio_id)
    if portfolio is None or portfolio.workspace_id != workspace_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Portfolio not found")
    return portfolio


async def resolve_account_ids(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    portfolio_id: uuid.UUID | None,
    unassigned: bool = False,
) -> set[uuid.UUID] | None:
    """`None` = nessun filtro (tutti i conti). Insieme vuoto = filtro
    applicato ma zero conti in scope (portfolio senza conti collegati, o
    ogni conto del workspace gia' assegnato a un portfolio quando
    `unassigned=True`) — un `set()` vuoto e un `None` sono stati diversi e
    vanno propagati cosi' come sono: i chiamanti (`compute_valuation` e
    affini) trattano gia' correttamente un insieme vuoto come "zero
    posizioni", mai come "nessun filtro"."""
    if unassigned:
        assigned = (
            await db.execute(
                select(PortfolioAccount.financial_account_id)
                .where(PortfolioAccount.workspace_id == workspace_id)
                .distinct()
            )
        ).scalars().all()
        all_accounts = (
            await db.execute(select(FinancialAccount.id).where(FinancialAccount.workspace_id == workspace_id))
        ).scalars().all()
        return set(all_accounts) - set(assigned)

    if portfolio_id is None:
        return None

    await get_portfolio_or_404(db, workspace_id, portfolio_id)
    links = (
        await db.execute(
            select(PortfolioAccount).where(
                PortfolioAccount.workspace_id == workspace_id,
                PortfolioAccount.portfolio_id == portfolio_id,
            )
        )
    ).scalars().all()
    return {link.financial_account_id for link in links}
