"""Interfaccia astratta dei connettori Open Banking.

Stesso pattern di `BankParser` (`app/parsers/base.py`): un `Protocol`
strutturale; chi la consuma (router, job di sync) non conosce il provider
concreto. Oggi esiste un solo connettore reale (Enable Banking): PDF e CSV non
sono connettori, restano i canali di import esistenti.

Gli importi normalizzati sono SEMPRE con segno (uscite negative, entrate
positive) e conservano valuta, date e id originali della banca; il payload
grezzo del provider viaggia in `raw` per audit/diagnostica.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Protocol


@dataclass
class Institution:
    name: str
    country: str
    logo_url: str | None = None
    psu_types: list[str] = field(default_factory=list)
    maximum_consent_validity_seconds: int | None = None
    beta: bool = False


@dataclass
class AuthorizationStart:
    url: str
    authorization_id: str | None


@dataclass
class ProviderAccount:
    uid: str
    iban: str | None
    name: str | None
    product: str | None
    currency: str | None
    cash_account_type: str | None


@dataclass
class ConnectionSession:
    session_id: str
    accounts: list[ProviderAccount]
    valid_until: datetime | None


@dataclass
class Balance:
    balance_type: str
    amount: Decimal
    currency: str


@dataclass
class NormalizedTransaction:
    external_id: str | None
    status: str  # 'booked' | 'pending'
    amount: Decimal  # con segno
    currency: str
    transaction_date: date
    booking_date: date | None
    value_date: date | None
    description: str
    counterparty_name: str | None
    counterparty_iban: str | None
    balance_after: Decimal | None
    reference: str | None
    bank_transaction_code: str | None
    raw: dict[str, Any]


@dataclass
class PsuContext:
    """Presenza dell'utente (click su "sincronizza ora"): con queste
    intestazioni molte banche non applicano il limite di accessi in background."""

    ip_address: str | None = None
    user_agent: str | None = None


class BankConnector(Protocol):
    provider: str

    async def list_institutions(self, country: str) -> list[Institution]: ...

    async def start_authorization(
        self,
        aspsp_name: str,
        aspsp_country: str,
        *,
        redirect_url: str,
        state: str,
        valid_until: datetime,
        psu_type: str = "personal",
    ) -> AuthorizationStart: ...

    async def complete_authorization(self, code: str) -> ConnectionSession: ...

    async def get_balances(self, account_uid: str, *, psu: PsuContext | None = None) -> list[Balance]: ...

    async def get_transactions(
        self,
        account_uid: str,
        *,
        date_from: date | None = None,
        date_to: date | None = None,
        longest: bool = False,
        psu: PsuContext | None = None,
    ) -> list[NormalizedTransaction]: ...

    async def revoke(self, session_id: str) -> None: ...
