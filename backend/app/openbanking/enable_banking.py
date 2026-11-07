"""Connettore Enable Banking (https://enablebanking.com/docs/api/reference/).

REST diretto via `httpx` (nessun SDK, come per Google/market data). Le
richieste sono autenticate con un JWT RS256 firmato con la chiave privata
dell'app dell'UTENTE (`kid` = application ID); il JWT dura al massimo 24 ore
secondo la documentazione, qui ne emettiamo uno da 1 ora per richiesta.

Campi e endpoint usati, tutti verificati sulla documentazione ufficiale
(2026-11-06): `GET /aspsps`, `POST /auth`, `POST /sessions`,
`GET /accounts/{uid}/balances`, `GET /accounts/{uid}/transactions`
(`continuation_key`, `strategy=longest`, intestazioni `Psu-*`),
`DELETE /sessions/{id}`.

Retry: solo per errori transitori (rete, timeout, 5xx) con backoff
esponenziale; MAI su 429 (limite della banca/provider: insistere peggiora).
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx
import jwt

from app.core.config import get_settings
from app.openbanking.base import (
    AuthorizationStart,
    Balance,
    ConnectionSession,
    Institution,
    NormalizedTransaction,
    ProviderAccount,
    PsuContext,
)
from app.openbanking.errors import (
    AuthorizationExpiredError,
    OpenBankingAuthError,
    OpenBankingError,
    ProviderUnavailableError,
    RateLimitedError,
)
from app.openbanking.urls import safe_provider_url

# Identificativi che il provider mette nel percorso delle richieste: solo
# caratteri innocui, altrimenti `../` o `?` cambierebbero la richiesta firmata.
_PATH_ID_RE = re.compile(r"^[A-Za-z0-9._:=-]{1,200}$")

logger = logging.getLogger("lumio.openbanking.enable_banking")

PROVIDER = "enable_banking"
_JWT_TTL_SECONDS = 3600
_MAX_ATTEMPTS = 3
# Pause tra un tentativo e il successivo (esposta a livello di modulo per i test).
_BACKOFF_SECONDS = (1.0, 3.0)
_MAX_PAGES = 100
# Tetti sui dati che arrivano dal provider (difesa da risposte anomale).
_MAX_RESPONSE_BYTES = 20 * 1024 * 1024
_MAX_AMOUNT = Decimal("1e13")
_MAX_TEXT = 2000
_MAX_SHORT_TEXT = 300
_MIN_YEAR, _MAX_YEAR = 1970, 2100
_TRANSIENT_STATUS = {500, 502, 503, 504}
_SESSION_ERROR_CODES = {"EXPIRED_SESSION", "CLOSED_SESSION", "REVOKED_SESSION", "SESSION_NOT_FOUND"}
_SKIPPED_STATUSES = {"CNCL", "RJCT", "SCHD"}
_PENDING_STATUSES = {"PDNG", "HOLD"}


def _path_id(value: str) -> str:
    if not _PATH_ID_RE.match(value):
        raise OpenBankingError("Identificativo del provider non valido", code="invalid_identifier")
    return value


def _parse_date(value: Any) -> date | None:
    if not value:
        return None
    try:
        parsed = date.fromisoformat(str(value)[:10])
    except ValueError:
        return None
    return parsed if _MIN_YEAR <= parsed.year <= _MAX_YEAR else None


def _parse_amount(value: Any) -> Decimal | None:
    # `Decimal("NaN")` e "Infinity" sono validi per Python ma non sono importi.
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError):
        return None
    if not amount.is_finite() or abs(amount) >= _MAX_AMOUNT:
        return None
    return amount


def _text(value: Any, limit: int = _MAX_SHORT_TEXT) -> str | None:
    if value is None:
        return None
    cleaned = "".join(ch for ch in str(value) if ch == "\n" or ch >= " " and ch != "\x7f").strip()
    return cleaned[:limit] or None


def normalize_transaction(raw: dict[str, Any]) -> NormalizedTransaction | None:
    """Converte una `Transaction` del provider nel formato comune.

    `None` per movimenti annullati/rifiutati/programmati o privi di importo o
    di qualunque data (non sono importabili senza inventare dati).
    """
    status_raw = str(raw.get("status") or "BOOK").upper()
    if status_raw in _SKIPPED_STATUSES:
        return None

    amount_block = raw.get("transaction_amount") or {}
    amount = _parse_amount(amount_block.get("amount"))
    currency = amount_block.get("currency")
    if amount is None or not currency:
        return None
    is_debit = str(raw.get("credit_debit_indicator") or "").upper() == "DBIT"
    amount = -abs(amount) if is_debit else abs(amount)

    booking_date = _parse_date(raw.get("booking_date"))
    value_date = _parse_date(raw.get("value_date"))
    transaction_date = _parse_date(raw.get("transaction_date")) or booking_date or value_date
    if transaction_date is None:
        return None

    # Controparte: per un'uscita e' il beneficiario, per un'entrata chi paga.
    party_key, account_key = ("creditor", "creditor_account") if is_debit else ("debtor", "debtor_account")
    counterparty_name = _text((raw.get(party_key) or {}).get("name"))
    counterparty_iban = _text((raw.get(account_key) or {}).get("iban"), 64)

    remittance = raw.get("remittance_information") or []
    if isinstance(remittance, str):
        remittance = [remittance]
    if not isinstance(remittance, list):
        remittance = []
    description = _text(" ".join(str(line).strip() for line in remittance[:50] if line and str(line).strip()), _MAX_TEXT)
    bank_code = raw.get("bank_transaction_code") or {}
    code_description = _text(bank_code.get("description") if isinstance(bank_code, dict) else None)
    if not description:
        description = _text(raw.get("note") or counterparty_name or code_description or "Movimento", _MAX_TEXT) or "Movimento"

    balance_block = raw.get("balance_after_transaction") or {}
    external_id = raw.get("entry_reference") or raw.get("transaction_id")

    return NormalizedTransaction(
        external_id=_text(external_id, 200),
        status="pending" if status_raw in _PENDING_STATUSES else "booked",
        amount=amount,
        currency=str(currency),
        transaction_date=transaction_date,
        booking_date=booking_date,
        value_date=value_date,
        description=description,
        counterparty_name=counterparty_name,
        counterparty_iban=counterparty_iban,
        balance_after=_parse_amount(balance_block.get("amount")) if balance_block else None,
        reference=_text(raw.get("reference_number"), 200),
        bank_transaction_code=code_description,
        raw=raw,
    )


class EnableBankingConnector:
    provider = PROVIDER

    def __init__(
        self,
        *,
        application_id: str,
        private_key_pem: str,
        base_url: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        settings = get_settings()
        self._application_id = application_id
        self._private_key_pem = private_key_pem
        self._base_url = (base_url or settings.open_banking_base_url).rstrip("/")
        self._timeout = settings.open_banking_http_timeout_seconds
        self._client = client

    # ---- infrastruttura -------------------------------------------------

    def _auth_header(self) -> dict[str, str]:
        now = int(time.time())
        token = jwt.encode(
            {"iss": "enablebanking.com", "aud": "api.enablebanking.com", "iat": now, "exp": now + _JWT_TTL_SECONDS},
            self._private_key_pem,
            algorithm="RS256",
            headers={"kid": self._application_id},
        )
        return {"Authorization": f"Bearer {token}"}

    @staticmethod
    def _psu_headers(psu: PsuContext | None) -> dict[str, str]:
        if psu is None:
            return {}
        headers: dict[str, str] = {}
        if psu.ip_address:
            headers["Psu-Ip-Address"] = psu.ip_address
        if psu.user_agent:
            headers["Psu-User-Agent"] = psu.user_agent
        return headers

    @staticmethod
    def _raise_for_error(response: httpx.Response) -> None:
        status_code = response.status_code
        if status_code < 400:
            return
        try:
            body = response.json()
        except ValueError:
            body = {}
        code = str(body.get("error") or body.get("code") or "") or None
        # Mai il corpo integrale nel messaggio: solo codice e stato.
        message = f"Enable Banking: HTTP {status_code}" + (f" ({code})" if code else "")
        if code in _SESSION_ERROR_CODES:
            raise AuthorizationExpiredError(message, code=code, http_status=status_code)
        if status_code == 429 or code == "ASPSP_RATE_LIMIT_EXCEEDED":
            raise RateLimitedError(message, code=code, http_status=status_code)
        if status_code in (401, 403):
            raise OpenBankingAuthError(message, code=code, http_status=status_code)
        if status_code in _TRANSIENT_STATUS or code == "ASPSP_TIMEOUT" or status_code == 408:
            raise ProviderUnavailableError(message, code=code, http_status=status_code)
        raise OpenBankingError(message, code=code, http_status=status_code)

    @staticmethod
    async def _fetch(client: httpx.AsyncClient, method: str, url: str, **kwargs: Any) -> httpx.Response:
        """Una richiesta con tetto alla dimensione della risposta: un provider
        (o chi si finge tale) non deve poter riempire la memoria del worker."""
        async with client.stream(method, url, **kwargs) as response:
            declared = response.headers.get("content-length")
            if declared and declared.isdigit() and int(declared) > _MAX_RESPONSE_BYTES:
                raise OpenBankingError("Risposta del provider troppo grande", code="response_too_large")
            body = bytearray()
            async for chunk in response.aiter_bytes():
                body.extend(chunk)
                if len(body) > _MAX_RESPONSE_BYTES:
                    raise OpenBankingError("Risposta del provider troppo grande", code="response_too_large")
            headers = {
                k: v
                for k, v in response.headers.items()
                if k.lower() not in ("content-encoding", "content-length", "transfer-encoding")
            }
            return httpx.Response(response.status_code, headers=headers, content=bytes(body))

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        psu: PsuContext | None = None,
    ) -> Any:
        last_error: OpenBankingError | None = None
        for attempt in range(_MAX_ATTEMPTS):
            if attempt:
                await asyncio.sleep(_BACKOFF_SECONDS[min(attempt - 1, len(_BACKOFF_SECONDS) - 1)])
            headers = {**self._auth_header(), **self._psu_headers(psu)}
            try:
                if self._client is not None:
                    response = await self._fetch(
                        self._client, method, self._base_url + path, params=params, json=json_body, headers=headers
                    )
                else:
                    # Nessun redirect (la risposta di un'API firmata non ha motivo di
                    # reindirizzare: seguirlo manderebbe la firma altrove) e TLS verificato.
                    async with httpx.AsyncClient(
                        timeout=self._timeout, follow_redirects=False, verify=True
                    ) as client:
                        response = await self._fetch(
                            client, method, self._base_url + path, params=params, json=json_body, headers=headers
                        )
                self._raise_for_error(response)
            except httpx.TransportError as exc:
                last_error = ProviderUnavailableError(f"Enable Banking non raggiungibile: {type(exc).__name__}")
                continue
            except ProviderUnavailableError as exc:
                last_error = exc
                continue
            if response.status_code == 204 or not response.content:
                return {}
            return response.json()
        assert last_error is not None
        raise last_error

    # ---- BankConnector ---------------------------------------------------

    async def list_institutions(self, country: str) -> list[Institution]:
        data = await self._request("GET", "/aspsps", params={"country": country.upper()})
        institutions = []
        for item in data.get("aspsps", []):
            if not item.get("name") or not item.get("country"):
                continue
            institutions.append(
                Institution(
                    name=item["name"],
                    country=item["country"],
                    logo_url=safe_provider_url(item.get("logo")),
                    psu_types=list(item.get("psu_types") or []),
                    maximum_consent_validity_seconds=item.get("maximum_consent_validity"),
                    beta=bool(item.get("beta", False)),
                )
            )
        return sorted(institutions, key=lambda i: i.name.lower())

    async def start_authorization(
        self,
        aspsp_name: str,
        aspsp_country: str,
        *,
        redirect_url: str,
        state: str,
        valid_until: datetime,
        psu_type: str = "personal",
    ) -> AuthorizationStart:
        if valid_until.tzinfo is None:
            valid_until = valid_until.replace(tzinfo=UTC)
        body = {
            "access": {
                "valid_until": valid_until.isoformat(),
                "balances": True,
                "transactions": True,
            },
            "aspsp": {"name": aspsp_name, "country": aspsp_country},
            "state": state,
            "redirect_url": redirect_url,
            "psu_type": psu_type,
        }
        data = await self._request("POST", "/auth", json_body=body)
        url = safe_provider_url(data.get("url"))
        if not url:
            raise OpenBankingError("Enable Banking non ha restituito un URL di autorizzazione valido")
        return AuthorizationStart(url=url, authorization_id=data.get("authorization_id"))

    async def complete_authorization(self, code: str) -> ConnectionSession:
        data = await self._request("POST", "/sessions", json_body={"code": code})
        session_id = data.get("session_id")
        if not session_id or not _PATH_ID_RE.match(str(session_id)):
            raise OpenBankingError("Enable Banking non ha restituito la sessione")
        accounts = []
        for acc in data.get("accounts", []):
            # Senza `uid` non si possono leggere saldi/movimenti: non e' utilizzabile.
            if not acc.get("uid") or not _PATH_ID_RE.match(str(acc["uid"])):
                continue
            accounts.append(
                ProviderAccount(
                    uid=str(acc["uid"]),
                    iban=(acc.get("account_id") or {}).get("iban"),
                    name=acc.get("name"),
                    product=acc.get("product"),
                    currency=acc.get("currency"),
                    cash_account_type=acc.get("cash_account_type"),
                )
            )
        valid_until = None
        raw_valid_until = (data.get("access") or {}).get("valid_until")
        if raw_valid_until:
            try:
                valid_until = datetime.fromisoformat(str(raw_valid_until).replace("Z", "+00:00"))
            except ValueError:
                valid_until = None
        return ConnectionSession(session_id=str(session_id), accounts=accounts, valid_until=valid_until)

    async def get_balances(self, account_uid: str, *, psu: PsuContext | None = None) -> list[Balance]:
        data = await self._request("GET", f"/accounts/{_path_id(account_uid)}/balances", psu=psu)
        balances = []
        for item in data.get("balances", []):
            block = item.get("balance_amount") or {}
            amount = _parse_amount(block.get("amount"))
            if amount is None or not block.get("currency"):
                continue
            balances.append(
                Balance(balance_type=str(item.get("balance_type") or ""), amount=amount, currency=block["currency"])
            )
        return balances

    async def get_transactions(
        self,
        account_uid: str,
        *,
        date_from: date | None = None,
        date_to: date | None = None,
        longest: bool = False,
        psu: PsuContext | None = None,
    ) -> list[NormalizedTransaction]:
        # Solo movimenti contabilizzati (BOOK): i pending non hanno un id stabile
        # garantito tra una lettura e l'altra, importarli creerebbe duplicati e
        # righe orfane. Limite dichiarato nella documentazione.
        params: dict[str, Any] = {"transaction_status": "BOOK"}
        if date_from is not None:
            params["date_from"] = date_from.isoformat()
        if date_to is not None and not longest:
            params["date_to"] = date_to.isoformat()
        if longest:
            params["strategy"] = "longest"

        result: list[NormalizedTransaction] = []
        continuation_key: str | None = None
        for _ in range(_MAX_PAGES):
            page_params = dict(params)
            if continuation_key:
                page_params["continuation_key"] = continuation_key
            data = await self._request(
                "GET", f"/accounts/{_path_id(account_uid)}/transactions", params=page_params, psu=psu
            )
            for raw in data.get("transactions", []):
                normalized = normalize_transaction(raw)
                if normalized is not None:
                    result.append(normalized)
            continuation_key = data.get("continuation_key")
            if not continuation_key:
                break
        else:
            logger.warning("get_transactions: raggiunto il limite di %d pagine", _MAX_PAGES)
        return result

    async def revoke(self, session_id: str) -> None:
        try:
            await self._request("DELETE", f"/sessions/{_path_id(session_id)}")
        except AuthorizationExpiredError:
            # Gia' chiusa/scaduta lato provider: l'obiettivo (nessuna sessione attiva) e' raggiunto.
            return
        except OpenBankingError as exc:
            if exc.http_status == 404:
                return
            raise
