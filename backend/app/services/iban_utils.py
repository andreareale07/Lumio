"""Normalizzazione IBAN condivisa tra `transfer_recognition.py` (controparte
di un bonifico) e `account_matching.py` (IBAN del titolare estratto
dall'intestazione di un estratto conto) — stesso confronto, stessa forma
normalizzata, un solo punto invece di due copie identiche."""


def normalize_iban(iban: str) -> str:
    return iban.strip().upper().replace(" ", "")
