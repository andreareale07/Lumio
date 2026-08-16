import re

from app.classification.catalog import CATALOG
from app.classification.taxonomy import TAXONOMY_BY_CODE
from app.services.rules_engine import Probe
from app.services.system_classification import classify_by_pattern


def test_every_pattern_key_is_unique():
    keys = [p.key for p in CATALOG]
    assert len(keys) == len(set(keys))


def test_every_pattern_targets_an_existing_taxonomy_code():
    for pattern in CATALOG:
        assert pattern.category_code in TAXONOMY_BY_CODE, (
            f"{pattern.key}: category_code {pattern.category_code!r} non esiste nella tassonomia"
        )


def test_every_pattern_uses_a_valid_field_and_operator():
    for pattern in CATALOG:
        assert pattern.field in ("merchant", "description")
        assert pattern.operator in ("equals", "contains", "starts_with", "ends_with", "regex", "merchant_equals")


def test_short_values_must_use_word_boundary_regex():
    # Regola anti-falso-positivo non negoziabile (vedi docstring di
    # catalog.py): "contains IP" matcherebbe "TRIPADVISOR", "contains COOP"
    # matcherebbe "COOPERATIVA EDILE". Ogni pattern con value piu' corto di
    # 5 caratteri DEVE usare regex con \b...\b.
    for pattern in CATALOG:
        if len(pattern.value) < 5:
            assert pattern.operator == "regex", (
                f"{pattern.key}: value {pattern.value!r} ha meno di 5 caratteri, "
                f"deve usare operator='regex', non {pattern.operator!r}"
            )
            assert pattern.value.startswith(r"\b") and pattern.value.endswith(r"\b"), (
                f"{pattern.key}: regex {pattern.value!r} su value corto deve avere \\b...\\b"
            )


def test_short_regex_patterns_do_not_match_known_false_positive_strings():
    # I due casi esplicitamente citati nel piano di rework come esempio
    # dell'anti-pattern da evitare: verificarli concretamente, non solo per
    # costruzione della regola sopra.
    ip_pattern = next(p for p in CATALOG if p.key == "fuel.ip")
    assert re.search(ip_pattern.value, "PAGAMENTO TRIPADVISOR", re.IGNORECASE) is None
    assert re.search(ip_pattern.value, "IP STAZIONE SERVIZIO ROMA", re.IGNORECASE) is not None

    coop_pattern = next(p for p in CATALOG if p.key == "grocery.coop")
    assert re.search(coop_pattern.value, "COOPERATIVA EDILE SRL", re.IGNORECASE) is None
    assert re.search(coop_pattern.value, "COOP SUPERMERCATO", re.IGNORECASE) is not None


def test_fuel_pattern_resolves_the_user_reported_scenario():
    # Scenario riportato dall'utente: il carburante veniva classificato
    # correttamente solo DOPO aver creato a mano la categoria Trasporti.
    # Con il catalogo, "ENI STAZIONE DI SERVIZIO" risolve subito.
    row = Probe(description_raw="ENI STAZIONE DI SERVIZIO MILANO", description_normalized=None, merchant=None)
    match = classify_by_pattern(row)
    assert match is not None
    assert match.category_code == "trasporti.carburante"


def test_supermarket_pattern_resolves():
    row = Probe(description_raw="PAGAMENTO POS LIDL ITALIA SRL MILANO", description_normalized=None, merchant=None)
    match = classify_by_pattern(row)
    assert match is not None
    assert match.category_code == "alimentari.supermercato"


def test_no_match_returns_none():
    row = Probe(description_raw="Qualcosa di completamente generico", description_normalized=None, merchant=None)
    assert classify_by_pattern(row) is None


def test_disabled_key_is_skipped():
    row = Probe(description_raw="ENI STAZIONE DI SERVIZIO MILANO", description_normalized=None, merchant=None)
    assert classify_by_pattern(row, disabled_keys=frozenset({"fuel.eni"})) is None
