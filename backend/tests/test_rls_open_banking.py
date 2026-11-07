"""Sicurezza a livello DB di `open_banking_credentials`, `bank_connections` e
`bank_connection_accounts`: le policy sono OWNER-ONLY, piu' strette del solito
`is_workspace_member` — nemmeno un altro membro DELLO STESSO workspace deve
vedere o toccare credenziali, sessioni e conti di un utente (i Terms del
provider vietano di rendere accessibile l'API a terzi).

Ogni test crea righe reali: con zero righe che matchano Postgres non invoca la
policy e un test RLS risulterebbe verde a vuoto.
"""
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.db.base import async_session_factory


async def _set_user(session, user_id: uuid.UUID) -> None:
    await session.execute(text("SELECT set_config('app.current_user_id', :uid, true)"), {"uid": str(user_id)})


async def _create_user(email: str) -> uuid.UUID:
    user_id = uuid.uuid4()
    async with async_session_factory() as session:
        await session.execute(
            text("INSERT INTO users (id, email, password_hash, display_name) VALUES (:id, :e, 'x', 'T')"),
            {"id": str(user_id), "e": email},
        )
        await session.commit()
    return user_id


async def _create_shared_workspace(owner: uuid.UUID, member: uuid.UUID) -> uuid.UUID:
    async with async_session_factory() as session:
        await _set_user(session, owner)
        workspace_id = (
            await session.execute(
                text("INSERT INTO workspaces (name, owner_user_id) VALUES ('Famiglia', :o) RETURNING id"),
                {"o": str(owner)},
            )
        ).scalar_one()
        await session.execute(
            text("INSERT INTO workspace_members (workspace_id, user_id, role) VALUES (:w, :u, 'owner')"),
            {"w": str(workspace_id), "u": str(owner)},
        )
        await session.commit()
    # L'app non consente a un utente di inserire un altro membro (la policy
    # richiede user_id = utente corrente): qui il secondo membro si aggiunge
    # con lo stesso SET ROLE lumio_rls_helper usato da tests/conftest.py per i
    # dati di sistema, solo per costruire lo scenario "due membri, un workspace".
    async with async_session_factory() as session:
        await session.execute(text("SET ROLE lumio_rls_helper"))
        await session.execute(
            text("INSERT INTO workspace_members (workspace_id, user_id, role) VALUES (:w, :u, 'member')"),
            {"w": str(workspace_id), "u": str(member)},
        )
        await session.execute(text("RESET ROLE"))
        await session.commit()
    return workspace_id


async def _seed(owner: uuid.UUID, workspace_id: uuid.UUID) -> dict[str, uuid.UUID]:
    """Credenziale + connessione + conto dell'owner."""
    async with async_session_factory() as session:
        await _set_user(session, owner)
        credential_id = (
            await session.execute(
                text(
                    "INSERT INTO open_banking_credentials (workspace_id, owner_user_id, provider, "
                    "private_key_encrypted, certificate_pem) VALUES (:w, :o, 'enable_banking', 'enc', 'cert') "
                    "RETURNING id"
                ),
                {"w": str(workspace_id), "o": str(owner)},
            )
        ).scalar_one()
        connection_id = (
            await session.execute(
                text(
                    "INSERT INTO bank_connections (workspace_id, owner_user_id, credential_id, provider, "
                    "aspsp_name, aspsp_country) VALUES (:w, :o, :c, 'enable_banking', 'Banca Test', 'IT') "
                    "RETURNING id"
                ),
                {"w": str(workspace_id), "o": str(owner), "c": str(credential_id)},
            )
        ).scalar_one()
        account_id = (
            await session.execute(
                text(
                    "INSERT INTO bank_connection_accounts (workspace_id, owner_user_id, connection_id, "
                    "provider_account_uid) VALUES (:w, :o, :c, 'uid-1') RETURNING id"
                ),
                {"w": str(workspace_id), "o": str(owner), "c": str(connection_id)},
            )
        ).scalar_one()
        await session.commit()
    return {"credential": credential_id, "connection": connection_id, "account": account_id}


_TABLES = {
    "credential": "open_banking_credentials",
    "connection": "bank_connections",
    "account": "bank_connection_accounts",
}


async def _fixture(suffix: str):
    owner = await _create_user(f"ob-owner-{suffix}@example.com")
    other = await _create_user(f"ob-other-{suffix}@example.com")
    workspace_id = await _create_shared_workspace(owner, other)
    ids = await _seed(owner, workspace_id)
    return owner, other, workspace_id, ids


@pytest.mark.parametrize("kind", list(_TABLES))
async def test_owner_can_select_own_rows(kind):
    owner, _other, _ws, ids = await _fixture(f"sel-own-{kind}")
    async with async_session_factory() as session:
        await _set_user(session, owner)
        rows = await session.execute(text(f"SELECT id FROM {_TABLES[kind]} WHERE id = :i"), {"i": str(ids[kind])})
        assert rows.first() is not None


@pytest.mark.parametrize("kind", list(_TABLES))
async def test_other_member_of_same_workspace_cannot_select(kind):
    _owner, other, _ws, ids = await _fixture(f"sel-{kind}")
    async with async_session_factory() as session:
        await _set_user(session, other)
        rows = await session.execute(text(f"SELECT id FROM {_TABLES[kind]} WHERE id = :i"), {"i": str(ids[kind])})
        assert rows.first() is None


@pytest.mark.parametrize("kind", list(_TABLES))
async def test_other_member_cannot_update(kind):
    _owner, other, _ws, ids = await _fixture(f"upd-{kind}")
    column = {"credential": "certificate_pem", "connection": "aspsp_name", "account": "name"}[kind]
    async with async_session_factory() as session:
        await _set_user(session, other)
        result = await session.execute(
            text(f"UPDATE {_TABLES[kind]} SET {column} = 'hacked' WHERE id = :i"), {"i": str(ids[kind])}
        )
        assert result.rowcount == 0


@pytest.mark.parametrize("kind", list(_TABLES))
async def test_other_member_cannot_delete(kind):
    owner, other, _ws, ids = await _fixture(f"del-{kind}")
    async with async_session_factory() as session:
        await _set_user(session, other)
        result = await session.execute(text(f"DELETE FROM {_TABLES[kind]} WHERE id = :i"), {"i": str(ids[kind])})
        assert result.rowcount == 0
    async with async_session_factory() as session:
        await _set_user(session, owner)
        assert (
            await session.execute(text(f"SELECT 1 FROM {_TABLES[kind]} WHERE id = :i"), {"i": str(ids[kind])})
        ).first() is not None


async def test_member_cannot_insert_credential_in_the_name_of_another_user():
    owner, other, ws, _ids = await _fixture("ins-spoof")
    async with async_session_factory() as session:
        await _set_user(session, other)
        with pytest.raises(DBAPIError, match="row-level security"):
            await session.execute(
                text(
                    "INSERT INTO open_banking_credentials (workspace_id, owner_user_id, provider, "
                    "private_key_encrypted, certificate_pem) VALUES (:w, :o, 'enable_banking', 'e', 'c')"
                ),
                {"w": str(ws), "o": str(owner)},
            )


async def test_user_cannot_insert_into_a_workspace_they_do_not_belong_to():
    outsider = await _create_user("ob-outsider@example.com")
    owner = await _create_user("ob-owner-ws@example.com")
    other = await _create_user("ob-other-ws@example.com")
    ws = await _create_shared_workspace(owner, other)
    async with async_session_factory() as session:
        await _set_user(session, outsider)
        with pytest.raises(DBAPIError, match="row-level security"):
            await session.execute(
                text(
                    "INSERT INTO open_banking_credentials (workspace_id, owner_user_id, provider, "
                    "private_key_encrypted, certificate_pem) VALUES (:w, :o, 'enable_banking', 'e', 'c')"
                ),
                {"w": str(ws), "o": str(outsider)},
            )


async def test_one_credential_per_user_and_provider():
    owner, _other, ws, _ids = await _fixture("unique")
    async with async_session_factory() as session:
        await _set_user(session, owner)
        with pytest.raises(DBAPIError, match="unique"):
            await session.execute(
                text(
                    "INSERT INTO open_banking_credentials (workspace_id, owner_user_id, provider, "
                    "private_key_encrypted, certificate_pem) VALUES (:w, :o, 'enable_banking', 'e', 'c')"
                ),
                {"w": str(ws), "o": str(owner)},
            )


async def test_cron_listing_function_returns_only_active_connections_across_users():
    owner, _other, _ws, ids = await _fixture("cron")
    async with async_session_factory() as session:
        await _set_user(session, owner)
        await session.execute(
            text("UPDATE bank_connections SET status = 'active' WHERE id = :i"), {"i": str(ids["connection"])}
        )
        await session.commit()
    # Nessuna identita' RLS impostata: e' proprio la condizione del cron.
    async with async_session_factory() as session:
        rows = (await session.execute(text("SELECT * FROM list_active_bank_connections()"))).all()
    assert [(r.connection_id, r.owner_user_id) for r in rows] == [(ids["connection"], owner)]


async def test_deleting_a_lumio_account_only_clears_the_mapping():
    """FK composita con SET NULL sulla sola colonna `financial_account_id`:
    il conto bancario resta (workspace_id non viene azzerato)."""
    owner, _other, ws, ids = await _fixture("setnull")
    async with async_session_factory() as session:
        await _set_user(session, owner)
        account_id = (
            await session.execute(
                text(
                    "INSERT INTO financial_accounts (workspace_id, name, account_type, currency) "
                    "VALUES (:w, 'Conto', 'checking', 'EUR') RETURNING id"
                ),
                {"w": str(ws)},
            )
        ).scalar_one()
        await session.execute(
            text("UPDATE bank_connection_accounts SET financial_account_id = :a WHERE id = :i"),
            {"a": str(account_id), "i": str(ids["account"])},
        )
        await session.commit()
    async with async_session_factory() as session:
        await _set_user(session, owner)
        await session.execute(text("DELETE FROM financial_accounts WHERE id = :a"), {"a": str(account_id)})
        await session.commit()
    async with async_session_factory() as session:
        await _set_user(session, owner)
        row = (
            await session.execute(
                text("SELECT workspace_id, financial_account_id FROM bank_connection_accounts WHERE id = :i"),
                {"i": str(ids["account"])},
            )
        ).one()
    assert row.workspace_id == ws
    assert row.financial_account_id is None
