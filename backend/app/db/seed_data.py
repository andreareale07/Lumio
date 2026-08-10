"""Dati di riferimento globali/di sistema, condivisi tra la migration che li
crea (0003_accounts_transactions) e i test che devono poterli ripristinare
dopo un TRUNCATE (il TRUNCATE CASCADE su `workspaces` svuota anche
`categories` per intero, comprese le righe di sistema con workspace_id NULL:
non esiste modo di troncare solo le righe workspace-scoped, perche' TRUNCATE
opera sempre sull'intera tabella).

ID fissi (non generati a runtime) cosi' che i parent_id delle sottocategorie
possano riferirli direttamente, sia nella migration che nel reseed di test.
"""

BANKS = [
    {"id": "6bb6eb78-276d-4b2f-ac63-8eef2c57d307", "code": "trade_republic", "name": "Trade Republic", "country": "DE"},
    {"id": "43137393-2b4f-4c14-b45b-2505ae0a72ec", "code": "bancoposta", "name": "BancoPosta", "country": "IT"},
    {"id": "1b2fc27e-2c5d-4163-b112-465e2b777829", "code": "fineco", "name": "Fineco", "country": "IT"},
    {"id": "a18155e5-02a3-4ee4-8974-52e0d35f6cf6", "code": "revolut", "name": "Revolut", "country": "LT"},
    {"id": "44538924-fcd9-4695-88a1-0724d4f01742", "code": "other", "name": "Altro", "country": None},
]

# SPEC §17: bank_parsers separa la banca dal parser/versione concreta.
# bank_id qui sotto e' preso direttamente dai BANKS sopra (stesso pattern:
# id fissi, non generati a runtime). Il codice del parser vive nel registro
# in app/parsers/__init__.py — questa riga traccia solo che esiste (ed e'
# attiva) una versione 1 del parser PDF per trade_republic.
BANK_PARSERS = [
    {
        "id": "1f6a5b19-3b40-4b3e-9a7b-2e0d6f1c9a44",
        "bank_id": "6bb6eb78-276d-4b2f-ac63-8eef2c57d307",  # trade_republic
        "parser_type": "trade_republic_pdf",
        "version": "1",
        "is_active": True,
    },
]

_CAT_CASA = "cdfe5c4e-13bd-42a6-8314-04df906e1669"
_CAT_ALIMENTARI = "124e2b3d-02d0-4a8b-9c5e-8b6e83bb2550"
_CAT_TEMPO_LIBERO = "fee4bffb-85f7-4ad1-bbfc-37c911978e30"
_CAT_ABBONAMENTI = "9d1ce192-c4f4-48b2-9d38-9e7412014e56"

SYSTEM_CATEGORIES = [
    {"id": _CAT_CASA, "parent_id": None, "name": "Casa", "code": "casa", "sort_order": 10},
    {"id": "dd65a3f5-0537-4d61-869c-5a7b1c04b9e5", "parent_id": _CAT_CASA, "name": "Affitto", "code": "casa.affitto", "sort_order": 11},
    {"id": "73cda961-a3b1-430c-81fb-03c0642cc842", "parent_id": _CAT_CASA, "name": "Bollette", "code": "casa.bollette", "sort_order": 12},
    {"id": "0028dc60-8d54-41c2-933c-0def7f9973c6", "parent_id": _CAT_CASA, "name": "Manutenzione", "code": "casa.manutenzione", "sort_order": 13},
    {"id": _CAT_ALIMENTARI, "parent_id": None, "name": "Alimentari", "code": "alimentari", "sort_order": 20},
    {"id": "0b4f2db6-bcbb-4401-a707-c61dcec68c35", "parent_id": _CAT_ALIMENTARI, "name": "Supermercato", "code": "alimentari.supermercato", "sort_order": 21},
    {"id": "9137698b-7626-40ee-ac62-7a20c5c009df", "parent_id": _CAT_ALIMENTARI, "name": "Mercato", "code": "alimentari.mercato", "sort_order": 22},
    {"id": _CAT_TEMPO_LIBERO, "parent_id": None, "name": "Tempo libero", "code": "tempo_libero", "sort_order": 30},
    {"id": "1e6352dc-878d-4feb-bae2-51cb21be2f4e", "parent_id": _CAT_TEMPO_LIBERO, "name": "Ristoranti", "code": "tempo_libero.ristoranti", "sort_order": 31},
    {"id": "dc0ba4a3-55d9-46ab-990b-9b73ee265eea", "parent_id": _CAT_TEMPO_LIBERO, "name": "Cinema", "code": "tempo_libero.cinema", "sort_order": 32},
    {"id": "12e31f65-feed-4bf4-96a4-128d566ed3eb", "parent_id": _CAT_TEMPO_LIBERO, "name": "Sport", "code": "tempo_libero.sport", "sort_order": 33},
    {"id": _CAT_ABBONAMENTI, "parent_id": None, "name": "Abbonamenti", "code": "abbonamenti", "sort_order": 40},
    {"id": "a8493dbc-1dc0-4875-bd1e-d7e36a220cbf", "parent_id": _CAT_ABBONAMENTI, "name": "Streaming", "code": "abbonamenti.streaming", "sort_order": 41},
    {"id": "fc21248e-72b0-4e21-9733-e6b008b8b91e", "parent_id": _CAT_ABBONAMENTI, "name": "Software", "code": "abbonamenti.software", "sort_order": 42},
]
