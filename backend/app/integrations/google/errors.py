"""Eccezioni di dominio per l'integrazione Google Sheets (milestone 10),
stesso ruolo di `MarketDataProviderError`/`AIProviderError`: mai lasciate
propagare fino a rompere il chiamante, chi le cattura decide se e' un
errore transitorio (rete, quota) o uno stato da riflettere in UI.
"""


class GoogleAPIError(Exception):
    """Errore di comunicazione/configurazione verso le API Google (OAuth,
    Sheets, Drive)."""


class GoogleReauthRequiredError(GoogleAPIError):
    """Il refresh token non e' piu' valido (revocato dall'utente lato
    Google, o scaduto per inattivita' prolungata): l'integrazione va
    considerata disconnessa e proposta di nuovo come "Connetti", non un
    errore transitorio da ritentare in silenzio."""
