import uuid

from app.classification.taxonomy import CATEGORY_KINDS, TAXONOMY, TAXONOMY_BY_CODE
from app.db.seed_data import SYSTEM_CATEGORIES_V1

# I 14 UUID delle categorie di sistema esistenti prima del rework: la nuova
# tassonomia DEVE riusarli tutti (nessuna transazione/regola/classificazione
# storica dell'utente deve cambiare category_id), vedi CLAUDE.md e il piano
# di migrazione. Se questo test fallisce dopo una modifica a taxonomy.py,
# quasi certamente e' stato rigenerato un UUID che andava invece riusato.
_HISTORIC_IDS = {uuid.UUID(cat["id"]) for cat in SYSTEM_CATEGORIES_V1}


def test_all_ids_are_unique():
    ids = [c.id for c in TAXONOMY]
    assert len(ids) == len(set(ids))


def test_all_codes_are_unique():
    codes = [c.code for c in TAXONOMY]
    assert len(codes) == len(set(codes))


def test_every_parent_code_resolves_to_a_root():
    roots = {c.code for c in TAXONOMY if c.parent_code is None}
    for cat in TAXONOMY:
        if cat.parent_code is not None:
            assert cat.parent_code in roots, f"{cat.code}: parent_code {cat.parent_code!r} non esiste"
            assert cat.parent_code in roots  # e' una radice, non un altro figlio (profondita' 2)


def test_child_kind_matches_parent_kind():
    for cat in TAXONOMY:
        if cat.parent_code is not None:
            parent = TAXONOMY_BY_CODE[cat.parent_code]
            assert cat.kind == parent.kind, f"{cat.code}: kind={cat.kind!r} != kind del padre {parent.kind!r}"


def test_kind_is_always_valid():
    for cat in TAXONOMY:
        assert cat.kind in CATEGORY_KINDS


def test_child_code_is_dot_notation_of_parent():
    for cat in TAXONOMY:
        if cat.parent_code is not None:
            assert cat.code == f"{cat.parent_code}.{cat.code.split('.', 1)[1]}"
            assert cat.code.startswith(f"{cat.parent_code}.")


def test_root_code_has_no_dot():
    for cat in TAXONOMY:
        if cat.parent_code is None:
            assert "." not in cat.code


def test_child_sort_order_is_within_parent_block():
    for cat in TAXONOMY:
        if cat.parent_code is not None:
            parent = TAXONOMY_BY_CODE[cat.parent_code]
            assert parent.sort_order < cat.sort_order < parent.sort_order + 100, (
                f"{cat.code}: sort_order={cat.sort_order} fuori dal blocco del padre "
                f"({parent.sort_order}, {parent.sort_order + 100})"
            )


def test_all_historic_system_category_ids_are_reused():
    taxonomy_ids = {uuid.UUID(c.id) for c in TAXONOMY}
    missing = _HISTORIC_IDS - taxonomy_ids
    assert not missing, f"UUID storici non riusati nella nuova tassonomia: {missing}"


def test_ids_are_valid_uuids():
    for cat in TAXONOMY:
        uuid.UUID(cat.id)  # solleva ValueError se non e' un UUID valido


def test_investment_pac_category_exists():
    # Test nominato (piano step 6): la stringa esatta del PAC dell'utente deve
    # poter risolvere in una categoria Investimenti tramite il livello 2
    # (transaction_type -> categoria). Qui verifichiamo solo che la categoria
    # target esista nella tassonomia con il kind corretto.
    pac = TAXONOMY_BY_CODE["investimenti.versamento_pac"]
    assert pac.kind == "investment"
    assert pac.parent_code == "investimenti"


def test_fuel_category_exists():
    fuel = TAXONOMY_BY_CODE["trasporti.carburante"]
    assert fuel.kind == "expense"
    assert fuel.parent_code == "trasporti"
