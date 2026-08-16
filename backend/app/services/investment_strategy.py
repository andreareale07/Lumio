"""Classificazione PAC (piano di accumulo) vs acquisto una tantum di un
movimento di investimento — rework dashboard interattivo, su richiesta
esplicita dell'utente ("teniamo in considerazione la differenza tra PAC e
investimenti/trading"). Stesso principio del dizionario multilingua
(`app/classification/transaction_type_labels.py`): un dato che oggi esiste
solo come testo libero (`InvestmentTransaction.source_type_raw`, popolato
dal parser Trade Republic — vedi `app/services/trade_parsing.py`), mai
classificato ne' aggregato da nessuna parte.

Non esaustivo per design: un'etichetta non riconosciuta (un altro parser
futuro, un movimento inserito a mano senza `source_type_raw`) ricade
onestamente su "altro" — mai un'assunzione silenziosa.
"""
from typing import Literal

InvestmentStrategy = Literal["recurring_plan", "one_off", "other"]

STRATEGY_LABELS: dict[InvestmentStrategy, str] = {
    "recurring_plan": "PAC",
    "one_off": "Una tantum",
    "other": "Altro",
}

_LABEL_TO_STRATEGY: dict[str, InvestmentStrategy] = {
    "savings plan execution": "recurring_plan",
    "buy trade": "one_off",
    "sell trade": "one_off",
}


def classify_strategy(source_type_raw: str | None) -> InvestmentStrategy:
    if source_type_raw is None:
        return "other"
    normalized = " ".join(source_type_raw.strip().lower().split())
    return _LABEL_TO_STRATEGY.get(normalized, "other")
