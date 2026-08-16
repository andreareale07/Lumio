import pytest

from app.services.merchant_extraction import extract_merchant

# Table-driven su descrizioni realistiche (POS/SDD/bonifici/trade), ognuna
# con il valore atteso ESATTO — non solo "non deve fallire". Include i due
# casi esplicitamente citati come anti-pattern nel piano di rework (COOP vs
# COOPERATIVA, stesso principio gia' verificato per il catalogo pattern in
# test_catalog.py).
CASES = [
    ("PAGAMENTO POS LIDL ITALIA SRL MILANO", "Lidl"),
    ("PAGAMENTO POS ESSELUNGA SPA MILANO", "Esselunga"),
    ("AMZN MKTP IT AMAZON.IT", "Amazon"),
    ("PAGAMENTO POS ENI STAZIONE SERVIZIO ROMA", "Eni"),
    ("PAGOBANCOMAT CONAD SUPERSTORE TORINO", "Conad"),
    ("PAGAMENTO POS FARMACIA CENTRALE NAPOLI", "Farmacia"),
    ("SPOTIFY AB STOCKHOLM", "Spotify"),
    ("PAYPAL *EBAY", "Ebay"),
    ("CARTA N. 1234 NETFLIX.COM", "Netflix"),
    ("PAGAMENTO POS UBER EATS MILANO 15/03/26 14:32", "Uber Eats"),
    ("ACQUISTO CARTA GLOVO ITALY", "Glovo"),
    ("AUT. 123456 PAGAMENTO POS Q8 STAZIONE", "Q8"),
    ("PAGAMENTO POS DECATHLON ITALIA SPA VERONA", "Decathlon Italia Spa"),
    ("Bonifico SEPA a favore di terzi", "Bonifico Sepa A Favore"),
]

# Regola anti-falso-positivo (stessa del catalogo, verificata anche qui
# perche' gli alias hanno lo stesso rischio dei pattern corti): "COOP" deve
# matchare "COOP SUPERMERCATO" ma non "COOPERATIVA EDILE SRL".
FALSE_POSITIVE_CASES = [
    ("PAGAMENTO POS COOPERATIVA EDILE SRL BOLOGNA", "Cooperativa Edile Srl"),
    ("PAGAMENTO POS COOP SUPERMERCATO TORINO", "Coop"),
    ("PAGAMENTO POS TRIPADVISOR LLC", "Tripadvisor Llc"),
]

@pytest.mark.parametrize("description,expected", CASES)
def test_extract_merchant_known_cases(description, expected):
    assert extract_merchant(description) == expected


@pytest.mark.parametrize("description,expected", FALSE_POSITIVE_CASES)
def test_extract_merchant_avoids_short_alias_false_positives(description, expected):
    assert extract_merchant(description) == expected


def test_extract_merchant_empty_description_returns_none():
    assert extract_merchant("") is None


def test_extract_merchant_pure_numeric_residue_returns_none():
    # Un riferimento operazione a 5 cifre (sotto la soglia di 6 cifre delle
    # noise pattern) non deve mai essere restituito come merchant.
    assert extract_merchant("12345") is None


def test_extract_merchant_very_short_residue_returns_none():
    assert extract_merchant("AB") is None


def test_extract_merchant_never_returns_empty_or_whitespace_only():
    for description, _expected in CASES + FALSE_POSITIVE_CASES:
        result = extract_merchant(description)
        if result is not None:
            assert result.strip() != ""


def test_extract_merchant_investment_description_does_not_crash():
    # Le righe di trade/PAC non hanno un "merchant" nel senso classico (sono
    # gia' classificate deterministicamente da system_classification.py
    # tramite trade_parsing, non hanno bisogno del merchant per la
    # categoria) — qui verifichiamo solo che l'estrazione non fallisca e non
    # produca una stringa vuota.
    description = (
        "Savings plan execution IE00B4L5Y983 iShares Core MSCI World "
        "UCITS ETF, quantity: 1.5"
    )
    result = extract_merchant(description)
    assert result is None or result.strip() != ""
