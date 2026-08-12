"""Wrapper REST minimale su Google Sheets API v4 (httpx diretto, stesso
principio di `app/marketdata/providers/yahoo.py`: nessun SDK). Ogni
funzione prende un `access_token` gia' valido — il refresh-on-expiry vive
in `app/services/google_integration_service.py`, non qui: questo modulo
non tocca mai il DB.
"""
import httpx

from app.integrations.google.errors import GoogleAPIError
from app.integrations.google.http import raise_for_status_with_body, request_with_retry

_BASE_URL = "https://sheets.googleapis.com/v4/spreadsheets"
_TIMEOUT = 30.0


def _headers(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


async def create_spreadsheet(access_token: str, title: str, sheet_titles: list[str]) -> tuple[str, str]:
    """Crea un nuovo spreadsheet con un tab per ogni titolo in
    `sheet_titles`, in un'unica chiamata. Ritorna `(spreadsheet_id, spreadsheet_url)`."""
    body = {
        "properties": {"title": title},
        "sheets": [
            {"properties": {"sheetId": index, "title": sheet_title}}
            for index, sheet_title in enumerate(sheet_titles)
        ],
    }
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            response = await request_with_retry(
                client, "POST", _BASE_URL, headers=_headers(access_token), json=body
            )
            raise_for_status_with_body(response)
    except httpx.HTTPError as exc:
        raise GoogleAPIError(f"Creazione spreadsheet Google fallita: {exc}") from exc
    data = response.json()
    return data["spreadsheetId"], data["spreadsheetUrl"]


async def write_values(access_token: str, spreadsheet_id: str, data: list[dict]) -> None:
    """Scrive valori su piu' range/tab in un'unica chiamata batch.
    `data` e' una lista di `{"range": "Tab!A1", "values": [[...], ...]}`."""
    body = {"valueInputOption": "USER_ENTERED", "data": data}
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            response = await request_with_retry(
                client,
                "POST",
                f"{_BASE_URL}/{spreadsheet_id}/values:batchUpdate",
                headers=_headers(access_token),
                json=body,
            )
            raise_for_status_with_body(response)
    except httpx.HTTPError as exc:
        raise GoogleAPIError(f"Scrittura valori su Google Sheets fallita: {exc}") from exc


async def list_charts(access_token: str, spreadsheet_id: str) -> list[dict]:
    """Grafici nativi gia' presenti nello spreadsheet (id, titolo,
    posizione) — serve a due cose ad ogni export: (1) cancellarli prima di
    ricrearli (`addChart` non e' idempotente: chiamarlo di nuovo con la
    stessa spec ne crea uno NUOVO, a differenza della scrittura valori che
    sovrascrive semplicemente le stesse celle), (2) preservare la
    posizione se l'utente ha spostato manualmente un grafico nel foglio —
    il titolo e' l'unico identificatore stabile che sopravvive a
    cancella+ricrea, quindi il chiamante riabbina per titolo."""
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            response = await request_with_retry(
                client,
                "GET",
                _BASE_URL + f"/{spreadsheet_id}",
                headers=_headers(access_token),
                params={"fields": "sheets.charts(chartId,position,spec.title)"},
            )
            raise_for_status_with_body(response)
    except httpx.HTTPError as exc:
        raise GoogleAPIError(f"Lettura grafici Google Sheets fallita: {exc}") from exc
    data = response.json()
    return [
        {"chart_id": chart["chartId"], "title": chart.get("spec", {}).get("title"), "position": chart.get("position")}
        for sheet in data.get("sheets", [])
        for chart in sheet.get("charts", [])
    ]


async def batch_update(access_token: str, spreadsheet_id: str, requests: list[dict]) -> None:
    """Applica una lista di `requests` (grafici, formattazione, ecc.) in
    un'unica chiamata `spreadsheets.batchUpdate` — riduce il numero di
    chiamate verso la quota API rispetto a una request per volta."""
    if not requests:
        return
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            response = await request_with_retry(
                client,
                "POST",
                f"{_BASE_URL}/{spreadsheet_id}:batchUpdate",
                headers=_headers(access_token),
                json={"requests": requests},
            )
            raise_for_status_with_body(response)
    except httpx.HTTPError as exc:
        raise GoogleAPIError(f"Formattazione/grafici Google Sheets falliti: {exc}") from exc
