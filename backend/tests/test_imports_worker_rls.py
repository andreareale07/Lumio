"""Il worker mantiene la RLS (mai BYPASSRLS): se l'identita' con cui il job
girerebbe non e' membro del workspace dell'import, la RLS deve impedire
qualunque effetto — non sollevare un'eccezione non gestita, non inserire
transazioni. Come documentato in app/worker/jobs/import_csv.py, la stessa
policy che protegge l'INSERT protegge anche la SELECT su `imports`: il job
non riesce nemmeno a leggere la riga e si ferma silenziosamente (la riga
resta 'queued', non transita a 'failed' — proprieta' di sicurezza piu' forte
di quanto serva, liveness accettata come limite noto in M04).

Si simula l'identita' "non autorizzata" passando al job l'id di un utente
del tutto estraneo al workspace (invece di rimuovere la vera membership, che
richiederebbe privilegi DELETE su workspace_members non concessi a
lumio_rls_helper per design — SELECT/INSERT sono gia' sufficienti a tutto
cio' che l'app fa oggi, vedi migration 0002): l'effetto sulla policy
is_workspace_member() e' identico.
"""
import uuid

from sqlalchemy import text

from app.db.base import async_session_factory
from app.worker.jobs.import_job import import_job


async def _set_current_user(session, user_id: uuid.UUID) -> None:
    await session.execute(
        text("SELECT set_config('app.current_user_id', :uid, true)"), {"uid": str(user_id)}
    )

CSV_SAMPLE = "data,descrizione,importo\n2026-01-15,Spesa,-10.00\n"


async def _register(client, email: str) -> str:
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "correct-password-123", "display_name": "Test"},
    )
    return response.json()["access_token"]


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _create_account(client, token: str) -> str:
    response = await client.post(
        "/api/v1/accounts",
        json={"name": "Conto", "account_type": "checking", "currency": "EUR"},
        headers=_auth_headers(token),
    )
    return response.json()["id"]


async def test_job_fails_cleanly_if_identity_is_not_a_workspace_member(client):
    token = await _register(client, "worker-rls@example.com")
    account_id = await _create_account(client, token)
    upload = await client.post(
        "/api/v1/imports",
        data={"financial_account_id": account_id},
        files={"file": ("estratto.csv", CSV_SAMPLE.encode(), "text/csv")},
        headers=_auth_headers(token),
    )
    import_id = upload.json()["import"]["id"]
    await client.post(
        f"/api/v1/imports/{import_id}/confirm",
        json={"mapping": upload.json()["preview"]["suggested_mapping"]},
        headers=_auth_headers(token),
    )
    owner = await client.get("/api/v1/auth/me", headers=_auth_headers(token))
    owner_id = owner.json()["id"]

    # Un utente del tutto estraneo (proprio workspace personale separato):
    # se il job venisse eseguito con questa identita' al posto di quella
    # dell'import, is_workspace_member(workspace_id) e' falsa esattamente
    # come lo sarebbe per un utente rimosso medio tempore dal workspace.
    outsider_token = await _register(client, "worker-rls-outsider@example.com")
    outsider = await client.get("/api/v1/auth/me", headers=_auth_headers(outsider_token))
    outsider_id = outsider.json()["id"]

    # Non deve sollevare un'eccezione non gestita: si ferma silenziosamente
    # (vedi docstring del modulo) perche' l'outsider non puo' nemmeno
    # leggere la riga import sotto RLS.
    await import_job(None, import_id, outsider_id)

    # Verifica con l'identita' del proprietario originale, che e' un membro
    # legittimo del workspace e vede quindi la riga tramite la normale RLS
    # (nessun bisogno di BYPASSRLS: ne' `imports` ne' `transactions` hanno
    # GRANT verso lumio_rls_helper, a differenza di `categories` in M03 —
    # qui non ci sono righe "di sistema" che l'app non debba poter scrivere).
    async with async_session_factory() as session:
        await _set_current_user(session, uuid.UUID(owner_id))
        status_row = (
            await session.execute(text("SELECT status FROM imports WHERE id = :iid"), {"iid": import_id})
        ).first()
        transactions_count = (
            await session.execute(
                text("SELECT count(*) FROM transactions WHERE import_id = :iid"), {"iid": import_id}
            )
        ).scalar_one()

    assert status_row.status == "queued"  # nessuna transizione: la riga non e' nemmeno leggibile
    assert transactions_count == 0
