import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.core.redis import redis_client
from app.db.base import async_session_factory, engine
from app.db.seed_data import SYSTEM_CATEGORIES
from app.main import app


@pytest.fixture(autouse=True)
async def _clean_tables():
    # TRUNCATE non e' soggetto a RLS (agisce a livello di tabella, non di
    # riga) quindi funziona indipendentemente da app.current_user_id. Nota:
    # troncare `workspaces` con CASCADE svuota anche `categories` per intero
    # (ha una FK su workspace_id), comprese le system category seedate dalla
    # migration — non e' possibile troncare solo le righe workspace-scoped,
    # quindi le si reinserisce subito dopo con lo stesso seed della migration.
    async with async_session_factory() as session:
        await session.execute(
            text(
                "TRUNCATE users, workspaces, workspace_members, "
                "financial_accounts, transactions, categories CASCADE"
            )
        )
        # La policy INSERT su categories richiede workspace_id NOT NULL (per
        # design: l'app non deve mai poter creare una falsa system category),
        # quindi lumio_app non puo' reinserire queste righe sotto RLS. SET
        # ROLE lumio_rls_helper (concesso a lumio_app dall'init script, vedi
        # db/postgres-init/01-create-app-role.sh) e' BYPASSRLS: stesso
        # meccanismo usato in produzione dalle funzioni SECURITY DEFINER,
        # qui applicato al reseed di dati che sono comunque immutabili per
        # l'app stessa.
        await session.execute(text("SET ROLE lumio_rls_helper"))
        for cat in SYSTEM_CATEGORIES:
            await session.execute(
                text(
                    "INSERT INTO categories (id, workspace_id, parent_id, name, code, is_system, sort_order) "
                    "VALUES (:id, NULL, :parent_id, :name, :code, true, :sort_order)"
                ),
                {
                    "id": uuid.UUID(cat["id"]),
                    "parent_id": uuid.UUID(cat["parent_id"]) if cat["parent_id"] else None,
                    "name": cat["name"],
                    "code": cat["code"],
                    "sort_order": cat["sort_order"],
                },
            )
        await session.execute(text("RESET ROLE"))
        await session.commit()
    yield


@pytest.fixture(autouse=True)
async def _reset_connection_pools():
    # pytest-asyncio apre un event loop per test; sia il pool di connessioni
    # SQLAlchemy/asyncpg sia il client redis sono singleton a livello di
    # modulo con connessioni legate al loop in cui sono state aperte. Senza
    # questa disconnessione esplicita a fine test, il test successivo (nuovo
    # loop) erediterebbe connessioni ormai morte.
    yield
    await redis_client.aclose()
    await engine.dispose()


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
