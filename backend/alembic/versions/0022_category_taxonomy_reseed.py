"""categories: reseed della tassonomia viva (23 radici, ~126 figli)

Revision ID: 0022_category_taxonomy_reseed
Revises: 0021_category_kind_uniqueness
Create Date: 2026-08-16

Migration SOLO dati (lo schema — colonna `kind`, trigger, indici unici — e'
gia' in 0021). Applica `app.classification.taxonomy.TAXONOMY` come UPSERT
sulle categorie di sistema (`workspace_id IS NULL`), la stessa identica
sorgente usata dal reseed di test (`tests/conftest.py`) e dalla pipeline di
classificazione — un solo posto da cui la tassonomia viene letta ovunque.

Riuso degli UUID, non rimappatura: tutte e 14 le categorie di sistema
seedate da 0003 (`app.db.seed_data.SYSTEM_CATEGORIES_V1`) sopravvivono con
lo STESSO id nella nuova tassonomia (`taxonomy.py` le referenzia per uuid
fisso, vedi il suo docstring) — l'UPSERT aggiorna solo `name`/`code`/
`parent_id`/`kind`/`sort_order` su quelle 14 righe, non le sostituisce.
Conseguenza: ZERO `UPDATE` su `transactions.category_id`, `rules.category_id`
o `classifications.category_id` — nessuna transazione/regola/classificazione
storica dell'utente cambia riferimento. Nessuna categoria di sistema viene
mai cancellata da questa migration (nessuna e' stata ritirata nel passaggio
alla nuova tassonomia: le 14 originali hanno tutte un posto nella nuova
struttura, si veda la tabella di corrispondenza nel piano di migrazione).

Le categorie CUSTOM create dai singoli workspace (workspace_id NOT NULL) non
sono toccate da questa migration in alcun modo: restano con il loro `kind`
di default ('expense', dalla ADD COLUMN di 0021) finche' l'utente non lo
corregge esplicitamente (API categorie, milestone successiva di questo
rework).

Stesso rischio RLS di 0021 (le migration girano come `lumio_app`, non
superuser, e `categories` ha FORCE ROW LEVEL SECURITY): l'UPSERT gira sotto
`SET LOCAL ROLE lumio_rls_helper`, con verifica esplicita del conteggio
finale di categorie di sistema per non fidarsi ciecamente di un "successo"
silenzioso che in realta' e' un no-op di RLS.

Ordine (due passate, per la FK di `parent_id` su se stessa): prima le radici
(`parent_id IS NULL` in entrambe le versioni, vecchia e nuova, quindi
nessuna dipendenza da altre righe), poi i figli (il cui `parent_id` punta a
un id di radice gia' presente dopo la prima passata).

Downgrade: lossy per le categorie NUOVE (cancellate, insieme a qualunque
transazione/regola/classificazione dell'utente le referenzi nel frattempo
verrebbe semplicemente scollegata via lo stesso meccanismo di remap usato
qui) — dichiarato esplicitamente, coerente con la nota di rilascio del
piano di migrazione (nessuna promessa di round-trip perfetto sui dati,
lo schema invece torna esattamente reversibile in 0021).
"""
import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from app.classification.taxonomy import TAXONOMY
from app.db.seed_data import SYSTEM_CATEGORIES_V1

# revision identifiers, used by Alembic.
revision: str = "0022_category_taxonomy_reseed"
down_revision: Union[str, None] = "0021_category_kind_uniqueness"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ROOTS = [c for c in TAXONOMY if c.parent_code is None]
_CHILDREN = [c for c in TAXONOMY if c.parent_code is not None]
_ROOT_ID_BY_CODE = {c.code: c.id for c in _ROOTS}

# Stringhe (stesso formato canonico restituito da str(asyncpg.UUID)), non
# uuid.UUID: qui servono solo per confronti Python (set difference), la
# conversione a uuid.UUID avviene SOLO al momento di legare un parametro SQL
# (vedi _params/downgrade), mai su un intero set usato per confronti.
_HISTORIC_IDS = {cat["id"] for cat in SYSTEM_CATEGORIES_V1}


def _upsert_sql(rows: list, *, with_parent: bool) -> str:
    """UPSERT su `id` (non su `code`): e' la chiave stabile che rende questa
    migration idempotente e tollerante a un DB gia' parzialmente aggiornato
    (una riesecuzione non duplica nulla, un'interruzione a meta' si puo'
    rilanciare senza pulire prima). `ON CONFLICT (code) ...` sarebbe stato
    fragile qui: il code di alcune righe storiche CAMBIA in questa stessa
    migration (es. "casa.bollette" -> "utenze"), quindi il conflitto andrebbe
    cercato sul valore NUOVO di code, non su quello con cui la riga esiste
    oggi nel DB.
    """
    parent_expr = ":parent_id_{i}" if with_parent else "NULL"
    values = []
    for i, _ in enumerate(rows):
        values.append(
            f"(:id_{i}, NULL, {parent_expr.format(i=i)}, :name_{i}, :code_{i}, :kind_{i}, true, true, :sort_order_{i})"
        )
    return (
        "INSERT INTO categories (id, workspace_id, parent_id, name, code, kind, is_system, is_active, sort_order) "
        "VALUES " + ", ".join(values) + " "
        "ON CONFLICT (id) DO UPDATE SET "
        "parent_id = EXCLUDED.parent_id, name = EXCLUDED.name, code = EXCLUDED.code, "
        "kind = EXCLUDED.kind, sort_order = EXCLUDED.sort_order, is_active = true"
    )


def _params(rows: list, *, parent_ids: list[str] | None) -> dict:
    params: dict = {}
    for i, cat in enumerate(rows):
        params[f"id_{i}"] = uuid.UUID(cat.id)
        params[f"name_{i}"] = cat.name
        params[f"code_{i}"] = cat.code
        params[f"kind_{i}"] = cat.kind
        params[f"sort_order_{i}"] = cat.sort_order
        if parent_ids is not None:
            params[f"parent_id_{i}"] = uuid.UUID(parent_ids[i])
    return params


def upgrade() -> None:
    connection = op.get_bind()

    connection.execute(sa.text("SET LOCAL ROLE lumio_rls_helper"))

    # --- passata 1: radici (parent_id sempre NULL) ------------------------
    connection.execute(
        sa.text(_upsert_sql(_ROOTS, with_parent=False)),
        _params(_ROOTS, parent_ids=None),
    )

    # --- passata 2: figli (parent_id gia' risolvibile, le radici esistono) -
    child_parent_ids = [_ROOT_ID_BY_CODE[c.parent_code] for c in _CHILDREN]
    connection.execute(
        sa.text(_upsert_sql(_CHILDREN, with_parent=True)),
        _params(_CHILDREN, parent_ids=child_parent_ids),
    )

    connection.execute(sa.text("RESET ROLE"))

    # --- verifica esplicita: mai fidarsi di un "successo" silenzioso -------
    # (stesso principio del controllo in 0021: un no-op di RLS non solleva
    # errore, aggiorna/inserisce semplicemente 0 righe).
    expected_ids = {c.id for c in TAXONOMY}
    actual_ids = {
        str(row[0])
        for row in connection.execute(
            sa.text("SELECT id FROM categories WHERE is_system = true")
        ).fetchall()
    }
    missing = expected_ids - actual_ids
    if missing:
        raise RuntimeError(
            f"Reseed tassonomia non riuscito: {len(missing)} categorie di sistema attese "
            f"mancanti dopo l'UPSERT (es. {sorted(missing)[:5]}). Verificare che 'SET LOCAL "
            "ROLE lumio_rls_helper' sia stato applicato (RLS su categories puo' rendere "
            "un INSERT/UPDATE un no-op silenzioso, vedi docstring di modulo)."
        )
    missing_historic = _HISTORIC_IDS - actual_ids
    if missing_historic:
        raise RuntimeError(
            "Reseed tassonomia ha perso uno o piu' UUID storici (rottura di riferimenti "
            f"transazioni/regole/classificazioni esistenti): {missing_historic}"
        )


def downgrade() -> None:
    connection = op.get_bind()
    connection.execute(sa.text("SET LOCAL ROLE lumio_rls_helper"))

    # Le 14 storiche tornano ai valori originali di SYSTEM_CATEGORIES_V1
    # PRIMA di cancellare le categorie nuove — ordine obbligatorio, non
    # arbitrario: `categories.parent_id` e' ON DELETE CASCADE, e almeno una
    # storica (l'ex "tempo_libero.ristoranti") e' stata RIPARENTATA sotto un
    # padre NUOVO durante l'upgrade ("bar_ristoranti"). Cancellare prima i
    # padri nuovi la cancellerebbe a cascata insieme a loro, anche se il suo
    # id e' storico e andrebbe preservato — bug osservato empiricamente
    # (verificato con upgrade/downgrade/upgrade su un DB di prova: dopo il
    # downgrade restavano 13 righe storiche invece di 14). Ripristinando
    # prima il `parent_id` originale (che punta sempre a un'altra riga
    # storica, mai a una nuova) si scollega la riga dal padre nuovo PRIMA che
    # quel padre venga cancellato, quindi il CASCADE non la tocca piu'.
    # (`kind` resta quello che aveva prima di questa migration — non e' nello
    # scope del downgrade DATI, la colonna stessa sparisce solo col downgrade
    # di 0021).
    for cat in SYSTEM_CATEGORIES_V1:
        connection.execute(
            sa.text(
                "UPDATE categories SET name = :name, code = :code, "
                "parent_id = :parent_id, sort_order = :sort_order WHERE id = :id"
            ),
            {
                "id": uuid.UUID(cat["id"]),
                "name": cat["name"],
                "code": cat["code"],
                "parent_id": uuid.UUID(cat["parent_id"]) if cat["parent_id"] else None,
                "sort_order": cat["sort_order"],
            },
        )

    # Le categorie NUOVE (non presenti nel seed V1 originale) vengono
    # rimosse SOLO ora, quando nessuna riga storica dipende piu' da loro come
    # padre. Le FK di transactions/rules non hanno ondelete (NO ACTION): se
    # qualcosa le referenzia ancora, il DELETE fallisce esplicitamente invece
    # di orfanizzare silenziosamente dati applicativi.
    new_ids = [uuid.UUID(c.id) for c in TAXONOMY if c.id not in _HISTORIC_IDS]
    if new_ids:
        connection.execute(
            sa.text("DELETE FROM categories WHERE id = ANY(:ids)"),
            {"ids": new_ids},
        )

    connection.execute(sa.text("RESET ROLE"))
