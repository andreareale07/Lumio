"""Wrapper REST minimale su Google Drive API v3 — usato SOLO per spostare
il file gestito da Lumio nella cartella scelta dall'utente (Google Picker,
mai un path testuale libero) e per leggerne il nome. Nessuna navigazione
libera dell'albero Drive lato backend: la scelta della cartella avviene
tutta nel widget Picker lato frontend, autorizzato da un access token a
vita breve (`GET /integrations/google/picker-token`).
"""
import httpx

from app.integrations.google.errors import GoogleAPIError
from app.integrations.google.http import raise_for_status_with_body, request_with_retry

_FILES_URL = "https://www.googleapis.com/drive/v3/files"
_TIMEOUT = 15.0


def _headers(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


async def move_file_to_folder(access_token: str, file_id: str, folder_id: str | None) -> None:
    """Sposta `file_id` nella cartella `folder_id` (None = root "Il mio
    Drive"). Serve prima leggere i parent attuali per rimuoverli tutti
    (`addParents`/`removeParents` sono liste separate da virgola, non un
    semplice "sostituisci")."""
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            current = await request_with_retry(
                client,
                "GET",
                f"{_FILES_URL}/{file_id}",
                headers=_headers(access_token),
                params={"fields": "parents"},
            )
            current.raise_for_status()
            previous_parents = ",".join(current.json().get("parents", []))

            params = {"addParents": folder_id or "root"}
            if previous_parents:
                params["removeParents"] = previous_parents
            response = await request_with_retry(
                client, "PATCH", f"{_FILES_URL}/{file_id}", headers=_headers(access_token), params=params
            )
            raise_for_status_with_body(response)
    except httpx.HTTPError as exc:
        raise GoogleAPIError(f"Spostamento file su Google Drive fallito: {exc}") from exc


async def get_folder_name(access_token: str, folder_id: str) -> str:
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            response = await request_with_retry(
                client,
                "GET",
                f"{_FILES_URL}/{folder_id}",
                headers=_headers(access_token),
                params={"fields": "name"},
            )
            raise_for_status_with_body(response)
    except httpx.HTTPError as exc:
        raise GoogleAPIError(f"Lettura nome cartella Google Drive fallita: {exc}") from exc
    return response.json().get("name", "")
