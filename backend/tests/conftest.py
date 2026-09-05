import shutil
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.classification.taxonomy import TAXONOMY
from app.core.config import get_settings
from app.core.redis import redis_client
from app.db.base import async_session_factory, engine
from app.main import app
from app.services.currency_catalog import SEED_CURRENCIES
from app.worker import queue as arq_queue

# Radici e figli separati una volta sola a import-time: la FK di
# `categories.parent_id` su se stessa impone due passate (i genitori devono
# gia' esistere quando si inseriscono i figli), indipendentemente da come si
# esegue l'INSERT.
_ROOTS = [c for c in TAXONOMY if c.parent_code is None]
_CHILDREN = [c for c in TAXONOMY if c.parent_code is not None]
_ROOT_ID_BY_CODE = {c.code: c.id for c in _ROOTS}


def _bulk_insert_sql(rows: list, *, parent_ids: list[str] | None) -> tuple[str, dict]:
    """Una singola INSERT multi-riga (un solo round-trip) invece di una
    INSERT per categoria: con ~180 righe di tassonomia, farla girare in un
    fixture `autouse` (quindi prima di OGNI test della suite) con una await
    per riga renderebbe l'intera suite percettibilmente piu' lenta. I
    parametri sono named e indicizzati per riga (`:id_0`, `:id_1`, ...)
    perche' SQLAlchemy `text()` non supporta liste di tuple posizionali.

    `parent_ids`: None per le radici (parent_id sempre NULL), altrimenti una
    lista parallela a `rows` con l'id del padre di ciascuna riga.
    """
    values_sql = []
    params: dict = {}
    for i, cat in enumerate(rows):
        parent_expr = f":parent_id_{i}" if parent_ids is not None else "NULL"
        values_sql.append(f"(:id_{i}, NULL, {parent_expr}, :name_{i}, :code_{i}, :kind_{i}, true, :sort_order_{i})")
        params[f"id_{i}"] = uuid.UUID(cat.id)
        params[f"name_{i}"] = cat.name
        params[f"code_{i}"] = cat.code
        params[f"kind_{i}"] = cat.kind
        params[f"sort_order_{i}"] = cat.sort_order
        if parent_ids is not None:
            params[f"parent_id_{i}"] = uuid.UUID(parent_ids[i])
    sql = (
        "INSERT INTO categories (id, workspace_id, parent_id, name, code, kind, is_system, sort_order) "
        "VALUES " + ", ".join(values_sql)
    )
    return sql, params


@pytest.fixture(autouse=True)
async def _clean_tables():
    # TRUNCATE non e' soggetto a RLS (agisce a livello di tabella, non di
    # riga) quindi funziona indipendentemente da app.current_user_id. Nota:
    # troncare `workspaces` con CASCADE svuota anche `categories`/`currencies`
    # per intero (entrambe hanno una FK su workspace_id, `fx_rates` a
    # cascata da `currencies`), comprese le righe di sistema seedate dalla
    # migration — non e' possibile troncare solo le righe workspace-scoped,
    # quindi le si reinseriscono subito dopo con la stessa fonte viva usata
    # dalla migration di produzione (`app/classification/taxonomy.py` per le
    # categorie, `app/services/currency_catalog.py` per le valute).
    async with async_session_factory() as session:
        await session.execute(
            text(
                "TRUNCATE users, workspaces, workspace_members, "
                "financial_accounts, transactions, categories, currencies, fx_rates, "
                "imports, import_mappings, rules, classifications, ai_profiles, "
                "assets, portfolios, portfolio_accounts, investment_transactions, positions, "
                "market_data_profiles, asset_prices, portfolio_snapshots, net_worth_snapshots, "
                "job_runs, transaction_type_mappings, financial_account_iban_history, "
                "transaction_dedup_decisions, transaction_review_items, "
                "detection_overrides, "
                "workspace_tax_residences, financial_account_tax_regimes, "
                "asset_tax_classifications, tax_loss_opening_balances, "
                "tax_realized_event_overrides, "
                "google_integrations, audit_log CASCADE"
            )
        )
        # La policy INSERT su categories/currencies richiede workspace_id NOT
        # NULL (per design: l'app non deve mai poter creare una falsa riga di
        # sistema), quindi lumio_app non puo' reinserire queste righe sotto
        # RLS. SET ROLE lumio_rls_helper (concesso a lumio_app dall'init
        # script, vedi db/postgres-init/01-create-app-role.sh) e' BYPASSRLS:
        # stesso meccanismo usato in produzione dalle funzioni SECURITY
        # DEFINER, qui applicato al reseed di dati che sono comunque
        # immutabili per l'app stessa. I trigger `enforce_category_kind`/
        # `check_category_code_not_shadowing_system` (migration 0021)
        # restano attivi durante questo INSERT: e' voluto, verificano che il
        # seed stesso sia internamente coerente (kind ereditato, nessun code
        # duplicato) tanto quanto lo farebbero su un INSERT applicativo.
        await session.execute(text("SET ROLE lumio_rls_helper"))

        roots_sql, roots_params = _bulk_insert_sql(_ROOTS, parent_ids=None)
        await session.execute(text(roots_sql), roots_params)

        child_parent_ids = [_ROOT_ID_BY_CODE[c.parent_code] for c in _CHILDREN]
        children_sql, children_params = _bulk_insert_sql(_CHILDREN, parent_ids=child_parent_ids)
        await session.execute(text(children_sql), children_params)

        # Reseed valute di sistema — deve avvenire PRIMA che un test crei un
        # workspace: `workspaces.base_currency` ha un default 'EUR' con FK su
        # `currencies.code`, che a questo punto e' stata appena svuotata.
        currency_values_sql = ", ".join(
            f"(:code_{i}, NULL, :name_{i}, :symbol_{i}, :digits_{i}, true)"
            for i in range(len(SEED_CURRENCIES))
        )
        currency_params = {}
        for i, c in enumerate(SEED_CURRENCIES):
            currency_params[f"code_{i}"] = c.code
            currency_params[f"name_{i}"] = c.name
            currency_params[f"symbol_{i}"] = c.symbol
            currency_params[f"digits_{i}"] = c.decimal_digits
        await session.execute(
            text(
                "INSERT INTO currencies (code, workspace_id, name, symbol, decimal_digits, is_system) "
                "VALUES " + currency_values_sql
            ),
            currency_params,
        )

        await session.execute(text("RESET ROLE"))
        await session.commit()
    yield


@pytest.fixture(autouse=True)
async def _reset_connection_pools():
    # pytest-asyncio apre un event loop per test; sia il pool di connessioni
    # SQLAlchemy/asyncpg sia il client redis (incluso quello di arq, usato
    # per accodare i job dal router imports) sono singleton a livello di
    # modulo con connessioni legate al loop in cui sono state aperte. Senza
    # questa disconnessione esplicita a fine test, il test successivo (nuovo
    # loop) erediterebbe connessioni ormai morte.
    #
    # La pulizia degli effetti collaterali di storage/Redis degli import
    # (milestone 04) vive qui apposta, PRIMA di aclose()/dispose(), invece
    # che in un fixture autouse separato: pytest ordina i fixture autouse
    # senza dipendenze esplicite in ordine ALFABETICO per nome (non per
    # ordine di dichiarazione nel file — verificato empiricamente), quindi
    # un fixture separato rischiava di essere smontato dopo che redis_client
    # era gia' stato chiuso, a seconda solo di come si chiamava.
    yield
    storage_root = get_settings().storage_path
    shutil.rmtree(f"{storage_root}/workspaces", ignore_errors=True)
    async for key in redis_client.scan_iter(match="lumio:jobs:*"):
        await redis_client.delete(key)
    # Contatori del rate limiter (app/core/rate_limit.py, chiave "LIMITS:...",
    # libreria `limits`): senza reset, i tanti register/login di test diversi
    # nello stesso processo (stessa IP 127.0.0.1) esaurirebbero il limite
    # reale e romperebbero test che non hanno nulla a che fare col rate
    # limiting stesso.
    async for key in redis_client.scan_iter(match="LIMITS:*"):
        await redis_client.delete(key)
    # Live-quote (docs/SPEC_STOCK_PRICE.md, app/services/live_quote_service.py):
    # stesso motivo dei prefissi sopra, altrimenti una quote/lock scritta da
    # un test resterebbe visibile (entro il suo TTL) al test successivo.
    async for key in redis_client.scan_iter(match="market:quote:*"):
        await redis_client.delete(key)
    await redis_client.aclose()
    await engine.dispose()
    if arq_queue._pool is not None:
        await arq_queue._pool.aclose()
        arq_queue._pool = None


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
