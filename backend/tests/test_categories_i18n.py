"""Copertura i18n della tassonomia categorie (PLAN_TAXONOMY_I18N.md): ogni
`code` in TAXONOMY deve avere una chiave corrispondente in ENTRAMBI i file
locale frontend, cosi' una categoria di sistema aggiunta in futuro senza
traduzione fallisce qui invece di comparire come chiave grezza in UI. Stesso
spirito di test_catalog.py::test_every_pattern_targets_an_existing_taxonomy_code.
"""
import json
from pathlib import Path

from app.classification.taxonomy import TAXONOMY

REPO_ROOT = Path(__file__).resolve().parents[2]
IT_CATEGORIES_JSON = REPO_ROOT / "frontend" / "src" / "locales" / "it" / "categories.json"
EN_CATEGORIES_JSON = REPO_ROOT / "frontend" / "src" / "locales" / "en" / "categories.json"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_every_taxonomy_code_has_an_italian_translation():
    it_keys = _load(IT_CATEGORIES_JSON)
    for category in TAXONOMY:
        assert category.code in it_keys, (
            f"{category.code}: manca la chiave in locales/it/categories.json"
        )
        assert it_keys[category.code] == category.name, (
            f"{category.code}: locales/it/categories.json ({it_keys[category.code]!r}) "
            f"non combacia con TAXONOMY.name ({category.name!r})"
        )


def test_every_taxonomy_code_has_an_english_translation():
    en_keys = _load(EN_CATEGORIES_JSON)
    for category in TAXONOMY:
        assert category.name_en, f"{category.code}: TAXONOMY.name_en mancante"
        assert category.code in en_keys, (
            f"{category.code}: manca la chiave in locales/en/categories.json"
        )
        assert en_keys[category.code] == category.name_en, (
            f"{category.code}: locales/en/categories.json ({en_keys[category.code]!r}) "
            f"non combacia con TAXONOMY.name_en ({category.name_en!r})"
        )


def test_no_taxonomy_code_collides_with_an_existing_ui_chrome_key():
    # Le chiavi tassonomia (es. "casa", "casa.affitto") vivono come proprieta'
    # TOP-LEVEL piatte nello stesso file delle chiavi UI-chrome esistenti
    # (fields, editDialog, ecc., vedi utils.ts::categoryDisplayName) — una
    # collisione di nome renderebbe irraggiungibile una delle due.
    chrome_keys = {"fields", "noParentOption", "kindInheritedNote", "sortOrderHint", "validation", "editDialog", "createDialog", "picker", "uncategorized"}
    taxonomy_codes = {c.code for c in TAXONOMY}
    assert not (chrome_keys & taxonomy_codes)
