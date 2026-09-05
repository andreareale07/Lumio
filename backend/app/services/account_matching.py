"""Riconoscimento del conto a cui appartiene un estratto conto in fase di
import — a differenza di `transfer_recognition.py` (che risponde "questo
bonifico e' verso un conto/persona di questo workspace?", un booleano), qui
serve sapere QUALE conto specifico proporre come candidato all'utente.

Solo IBAN: `FinancialAccount` non ha un campo "titolare" da confrontare con
il nominativo estratto dal documento (quel dato descrive una persona, non
un conto — un conto puo' essere cointestato, o il nome sulla carta puo'
differire dal nome del conto in Lumio) — un match per nominativo darebbe un
falso senso di precisione senza un campo su cui appoggiarsi davvero. Il
nominativo estratto (`AccountHeaderInfo.holder_name`) resta comunque utile
altrove: come valore precompilato quando l'utente crea un nuovo conto.

Priorita' IBAN attuale su IBAN storico, stesso principio di
`transfer_recognition._matches_known_account_iban` (un istituto puo' aver
cambiato IBAN pur restando lo stesso conto fisico) — qui pero' la funzione
ritorna il conto matchato, non solo se esiste."""
import uuid
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.financial_account import FinancialAccount
from app.models.financial_account_iban_history import FinancialAccountIbanHistory
from app.services.iban_utils import normalize_iban

MatchReason = Literal["iban", "iban_history"]


@dataclass(frozen=True)
class AccountCandidate:
    account_id: uuid.UUID
    account_name: str
    match_reason: MatchReason


async def find_account_candidates(
    db: AsyncSession, workspace_id: uuid.UUID, iban: str | None
) -> list[AccountCandidate]:
    """`[]` se non c'e' nessun IBAN da confrontare (nessuna estrazione
    riuscita) o se nessun conto del workspace combacia — mai un candidato
    indovinato. Se l'IBAN attuale di uno o piu' conti combacia, quelli
    hanno priorita' assoluta e lo storico non viene nemmeno interrogato."""
    if not iban:
        return []
    target = normalize_iban(iban)

    current_result = await db.execute(
        select(FinancialAccount.id, FinancialAccount.name, FinancialAccount.iban).where(
            FinancialAccount.workspace_id == workspace_id,
            FinancialAccount.iban.is_not(None),
        )
    )
    current_matches = [
        AccountCandidate(account_id=row.id, account_name=row.name, match_reason="iban")
        for row in current_result.all()
        if normalize_iban(row.iban) == target
    ]
    if current_matches:
        return current_matches

    history_result = await db.execute(
        select(
            FinancialAccountIbanHistory.financial_account_id,
            FinancialAccount.name,
            FinancialAccountIbanHistory.iban,
        )
        .join(FinancialAccount, FinancialAccount.id == FinancialAccountIbanHistory.financial_account_id)
        .where(FinancialAccountIbanHistory.workspace_id == workspace_id)
    )
    seen: set[uuid.UUID] = set()
    history_matches: list[AccountCandidate] = []
    for row in history_result.all():
        if normalize_iban(row.iban) != target or row.financial_account_id in seen:
            continue
        seen.add(row.financial_account_id)
        history_matches.append(
            AccountCandidate(account_id=row.financial_account_id, account_name=row.name, match_reason="iban_history")
        )
    return history_matches
