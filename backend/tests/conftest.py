import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.core.redis import redis_client
from app.db.base import async_session_factory, engine
from app.main import app


@pytest.fixture(autouse=True)
async def _clean_tables():
    # TRUNCATE non e' soggetto a RLS (agisce a livello di tabella, non di
    # riga) quindi funziona indipendentemente da app.current_user_id.
    async with async_session_factory() as session:
        await session.execute(text("TRUNCATE users, workspaces, workspace_members CASCADE"))
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
