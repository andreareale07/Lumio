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
    # Codice e sotto-codice della banca (ISO 20022) e segnalazioni della
    # normalizzazione (id mancante/placeholder, indicatore assente, campi presenti):
    # servono solo alla diagnostica, mai mostrati.
    bank_code: str | None = None
    bank_sub_code: str | None = None
    flags: tuple[str, ...] = ()


@dataclass
class FetchStats:
    """Statistiche di una lettura dalla banca: SOLO conteggi e metadati della
    richiesta, mai causali, importi o nomi (diagnostica sicura da conservare)."""

    strategy: str = "window"
    date_from: str | None = None
    pages: int = 0
    raw_count: int = 0
    accepted: int = 0
    discarded: dict[str, int] = field(default_factory=dict)
    status_counts: dict[str, int] = field(default_factory=dict)
    sub_codes: dict[str, int] = field(default_factory=dict)
    flag_counts: dict[str, int] = field(default_factory=dict)
    repeated_external_ids: int = 0

    def discard(self, reason: str) -> None:
        self.discarded[reason] = self.discarded.get(reason, 0) + 1

    def bump(self, bucket: dict[str, int], key: str) -> None:
        bucket[key] = bucket.get(key, 0) + 1

    def as_dict(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy,
            "date_from": self.date_from,
            "pages": self.pages,
            "raw_count": self.raw_count,
            "accepted": self.accepted,
            "discarded": dict(self.discarded),
            "status_counts": dict(self.status_counts),
            "sub_codes": dict(self.sub_codes),
            "flags": dict(self.flag_counts),
            "repeated_external_ids": self.repeated_external_ids,
        }


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
        stats: FetchStats | None = None,
    ) -> list[NormalizedTransaction]: ...

    async def revoke(self, session_id: str) -> None: ...
