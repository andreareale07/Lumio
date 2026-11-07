"""Errori del livello Open Banking. Nessun messaggio contiene mai dati
finanziari ne' credenziali (SPEC §55): solo codice e descrizione generica."""


class OpenBankingError(Exception):
    def __init__(self, message: str, *, code: str | None = None, http_status: int | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.http_status = http_status


class OpenBankingAuthError(OpenBankingError):
    """Credenziali dell'app rifiutate dal provider (JWT/application ID non validi)."""


class AuthorizationExpiredError(OpenBankingError):
    """Sessione di consenso scaduta, chiusa o revocata: serve una nuova autorizzazione."""


class RateLimitedError(OpenBankingError):
    """Limite di richieste del provider o della banca: non ritentare subito."""


class ProviderUnavailableError(OpenBankingError):
    """Errore transitorio (timeout, 5xx, rete): ritentabile con backoff."""
