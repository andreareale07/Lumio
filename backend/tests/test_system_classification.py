from app.services.system_classification import (
    AI_EXCLUDED_TRANSACTION_TYPES,
    classify_by_transaction_type,
    is_ai_eligible,
)

# La stringa ESATTA riportata dall'utente: prima di questo livello, l'AI la
# classificava come "Tempo libero" o "Abbonamenti" perche' doveva scegliere
# tra le sole 14 categorie di spesa esistenti. Deve risolvere in una
# categoria Investimenti senza mai arrivare al provider AI.
_USER_REPORTED_PAC_DESCRIPTION = (
    "Savings plan execution IE00B4L5Y983 iShares III plc - iShares Core MSCI "
    "World UCITS ETF USD (Acc), quantity: 1.194268"
)


def test_user_reported_pac_resolves_to_investment_pac_category():
    code = classify_by_transaction_type("investment", _USER_REPORTED_PAC_DESCRIPTION)
    assert code == "investimenti.versamento_pac"


def test_user_reported_pac_is_never_ai_eligible():
    assert is_ai_eligible("investment") is False


def test_buy_trade_resolves_to_acquisto_titoli():
    description = "Buy trade IE00B4L5Y983 iShares Core MSCI World UCITS ETF USD (Acc), quantity: 2.5"
    assert classify_by_transaction_type("investment", description) == "investimenti.acquisto_titoli"


def test_sell_trade_resolves_to_vendita_titoli():
    description = "Sell trade IE00B4L5Y983 iShares Core MSCI World UCITS ETF USD (Acc), quantity: 2.5"
    assert classify_by_transaction_type("investment", description) == "investimenti.vendita_titoli"


def test_investment_type_without_recognizable_description_falls_back_to_generic_purchase():
    # transaction_type gia' dice "investment" ma il testo non matcha nessun
    # formato noto (parser diverso, o un formato mai osservato): categoria
    # generica di investimento, mai un'ipotesi piu' specifica non supportata.
    code = classify_by_transaction_type("investment", "Qualcosa di non riconoscibile")
    assert code == "investimenti.acquisto_titoli"


def test_description_matching_trade_pattern_wins_even_without_investment_type():
    # Copre il canale CSV / un override utente sul transaction_type: il
    # riconoscimento testuale del PAC/trade deve valere ANCHE se
    # transaction_type non e' (ancora, o piu') "investment" — doppia
    # condizione voluta (vedi docstring di system_classification.py).
    code = classify_by_transaction_type("expense", _USER_REPORTED_PAC_DESCRIPTION)
    assert code == "investimenti.versamento_pac"


def test_transfer_resolves_to_giroconto():
    assert classify_by_transaction_type("transfer", "Bonifico interno") == "trasferimenti.giroconto"


def test_dividend_resolves_to_dividendi():
    assert classify_by_transaction_type("dividend", "Dividendo ricevuto") == "entrate.dividendi"


def test_interest_resolves_to_interessi_attivi():
    assert classify_by_transaction_type("interest", "Interessi maturati") == "entrate.interessi_attivi"


def test_tax_resolves_to_tasse_root():
    assert classify_by_transaction_type("tax", "Imposta di bollo") == "tasse"


def test_fee_resolves_to_commissioni_root():
    assert classify_by_transaction_type("fee", "Canone conto") == "commissioni"


def test_refund_is_not_resolved_deterministically():
    # Un rimborso appartiene alla categoria della spesa originale (es.
    # Shopping), non a un contenitore generico "Rimborsi": forzarlo qui
    # nasconderebbe la spesa vera dalle analytics. Prosegue verso
    # pattern/AI.
    assert classify_by_transaction_type("refund", "Rimborso Amazon") is None


def test_expense_and_income_are_not_resolved_deterministically():
    assert classify_by_transaction_type("expense", "LIDL SUPERMARKET") is None
    assert classify_by_transaction_type("income", "Bonifico ricevuto") is None


def test_adjustment_is_not_resolved_deterministically():
    assert classify_by_transaction_type("adjustment", "Rettifica manuale") is None


def test_ai_excluded_types_are_never_eligible():
    for t in AI_EXCLUDED_TRANSACTION_TYPES:
        assert is_ai_eligible(t) is False


def test_expense_income_refund_adjustment_remain_ai_eligible():
    for t in ("expense", "income", "refund", "adjustment"):
        assert is_ai_eligible(t) is True
