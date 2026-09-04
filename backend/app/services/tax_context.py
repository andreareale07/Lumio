"""Risoluzione della giurisdizione fiscale vigente per un workspace a una
data (SPEC_TAX_REGIME.md FETTA 1). Punto unico da cui ogni altro servizio
fiscale DB-aware ottiene la `TaxJurisdiction` — mai una lookup diretta a
`app.tax.registry` sparsa nei vari servizi, cosi' il default silenzioso
(nessuna residenza dichiarata) e' gestito in un solo posto.

`workspace_tax_residences` e' APPEND-ONLY per anno di decorrenza, stesso
pattern di `financial_account_tax_regimes`: una riga (fiscal_year=2015,
jurisdiction=CH) vale da quell'anno fino al successivo cambiamento, non solo
per quell'anno esatto — l'utente imposta la residenza UNA VOLTA e resta
valida finche' non la cambia, invece di doverla ridichiarare ogni gennaio.
Storico multi-periodo supportato aggiungendo piu' righe (es. 2010 IT, 2015
CH, 2020 IT): la risoluzione a una data prende la riga con
`fiscal_year` piu' recente <= l'anno richiesto."""
import uuid
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.workspace_tax_residence import WorkspaceTaxResidence
from app.tax.base import TaxJurisdiction
from app.tax.registry import get_jurisdiction


@dataclass(frozen=True)
class TaxContext:
    jurisdiction: TaxJurisdiction
    fiscal_year: int
    # False quando il workspace non ha ancora dichiarato la residenza per
    # questo anno e si e' ricaduti sul default di istanza
    # (`tax_default_jurisdiction`) — la UI deve poterlo dire esplicitamente
    # ("residenza non dichiarata, mostro le regole italiane"), mai fingere
    # di saperlo.
    residence_declared: bool


async def resolve_tax_context(db: AsyncSession, workspace_id: uuid.UUID, on: date) -> TaxContext:
    result = await db.execute(
        select(WorkspaceTaxResidence)
        .where(
            WorkspaceTaxResidence.workspace_id == workspace_id,
            WorkspaceTaxResidence.fiscal_year <= on.year,
        )
        .order_by(WorkspaceTaxResidence.fiscal_year.desc())
        .limit(1)
    )
    residence = result.scalar_one_or_none()
    if residence is not None:
        return TaxContext(
            jurisdiction=get_jurisdiction(residence.jurisdiction_code),
            fiscal_year=on.year,
            residence_declared=True,
        )
    return TaxContext(
        jurisdiction=get_jurisdiction(get_settings().tax_default_jurisdiction),
        fiscal_year=on.year,
        residence_declared=False,
    )
