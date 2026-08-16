from app.classification.transaction_type_labels import SEMANTIC_KEYS, classify_label


def test_classifies_known_labels_across_languages():
    assert classify_label("Interessi") == "interest"
    assert classify_label("Interest") == "interest"
    assert classify_label("Zinsen") == "interest"


def test_case_and_whitespace_insensitive():
    assert classify_label("  INTEREST  ") == "interest"
    # Spazi interni multipli vengono collassati dalla normalizzazione, non
    # solo quelli iniziali/finali (etichette PDF a volte hanno spaziatura
    # irregolare per via dell'estrazione parola-per-parola).
    assert classify_label("Card   Transaction") == "card_transaction"


def test_unknown_label_returns_none_not_a_guess():
    assert classify_label("Bonifico") is None
    assert classify_label("Wire Transfer") is None


def test_every_semantic_key_has_at_least_one_label_per_covered_language():
    # Non un requisito che OGNI lingua copra OGNI chiave, ma che il set di
    # chiavi dichiarato sia effettivamente raggiungibile da almeno un'etichetta
    # — altrimenti SEMANTIC_KEYS mentirebbe su cosa il dizionario sa fare.
    from app.classification.transaction_type_labels import _LABEL_TO_SEMANTIC_KEY

    covered = set(_LABEL_TO_SEMANTIC_KEY.values())
    assert covered == set(SEMANTIC_KEYS)
