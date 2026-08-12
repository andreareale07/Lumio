"""Test unitari del client Sheets API (milestone 10) — httpx mockato."""
import json

import pytest

from app.integrations.google.errors import GoogleAPIError
from app.integrations.google.sheets_client import batch_update, create_spreadsheet, list_charts, write_values


async def test_create_spreadsheet_returns_id_and_url(httpx_mock):
    httpx_mock.add_response(
        url="https://sheets.googleapis.com/v4/spreadsheets",
        json={"spreadsheetId": "abc123", "spreadsheetUrl": "https://docs.google.com/spreadsheets/d/abc123"},
    )
    spreadsheet_id, url = await create_spreadsheet("token", "Lumio Finance", ["Riepilogo", "Transazioni"])
    assert spreadsheet_id == "abc123"
    assert url.endswith("abc123")
    request = httpx_mock.get_requests()[0]
    assert request.headers["authorization"] == "Bearer token"


async def test_create_spreadsheet_sends_one_tab_per_title(httpx_mock):
    httpx_mock.add_response(url="https://sheets.googleapis.com/v4/spreadsheets", json={"spreadsheetId": "abc", "spreadsheetUrl": "https://x"})
    await create_spreadsheet("token", "Lumio Finance", ["A", "B", "C"])
    body = json.loads(httpx_mock.get_requests()[0].content)
    assert [s["properties"]["title"] for s in body["sheets"]] == ["A", "B", "C"]


async def test_create_spreadsheet_error_raises_domain_exception(httpx_mock):
    httpx_mock.add_response(url="https://sheets.googleapis.com/v4/spreadsheets", status_code=403)
    with pytest.raises(GoogleAPIError):
        await create_spreadsheet("token", "Lumio Finance", ["A"])


async def test_write_values_posts_batch_update(httpx_mock):
    httpx_mock.add_response(url="https://sheets.googleapis.com/v4/spreadsheets/sheet1/values:batchUpdate", json={})
    await write_values("token", "sheet1", [{"range": "A!A1", "values": [["x"]]}])


async def test_batch_update_skips_network_call_when_no_requests():
    # Nessun httpx_mock registrato: una chiamata effettiva farebbe fallire il test.
    await batch_update("token", "sheet1", [])


async def test_batch_update_sends_requests(httpx_mock):
    httpx_mock.add_response(url="https://sheets.googleapis.com/v4/spreadsheets/sheet1:batchUpdate", json={})
    await batch_update("token", "sheet1", [{"repeatCell": {}}])


async def test_list_charts_flattens_charts_across_all_sheets_with_title_and_position(httpx_mock):
    saved_position = {"overlayPosition": {"anchorCell": {"sheetId": 0, "rowIndex": 5, "columnIndex": 8}}}
    httpx_mock.add_response(
        url="https://sheets.googleapis.com/v4/spreadsheets/sheet1?fields=sheets.charts(chartId,position,spec.title)",
        json={
            "sheets": [
                {
                    "charts": [
                        {"chartId": 111, "position": saved_position, "spec": {"title": "Entrate/Uscite mensili"}},
                        {"chartId": 222, "position": saved_position},  # senza titolo: comunque incluso
                    ]
                },
                {"charts": [{"chartId": 333, "spec": {"title": "Allocazione per tipo di asset"}}]},
                {},  # foglio senza grafici: non deve rompere il parsing
            ]
        },
    )
    charts = await list_charts("token", "sheet1")
    assert [c["chart_id"] for c in charts] == [111, 222, 333]
    assert charts[0]["title"] == "Entrate/Uscite mensili"
    assert charts[0]["position"] == saved_position
    assert charts[1]["title"] is None


async def test_list_charts_empty_when_no_charts(httpx_mock):
    httpx_mock.add_response(
        url="https://sheets.googleapis.com/v4/spreadsheets/sheet1?fields=sheets.charts(chartId,position,spec.title)",
        json={"sheets": [{}, {}]},
    )
    assert await list_charts("token", "sheet1") == []


async def test_list_charts_error_raises_domain_exception(httpx_mock):
    httpx_mock.add_response(
        url="https://sheets.googleapis.com/v4/spreadsheets/sheet1?fields=sheets.charts(chartId,position,spec.title)",
        status_code=403,
    )
    with pytest.raises(GoogleAPIError):
        await list_charts("token", "sheet1")


async def test_retries_once_on_429_then_succeeds(httpx_mock):
    httpx_mock.add_response(url="https://sheets.googleapis.com/v4/spreadsheets", status_code=429)
    httpx_mock.add_response(url="https://sheets.googleapis.com/v4/spreadsheets", json={"spreadsheetId": "retried", "spreadsheetUrl": "https://x"})
    spreadsheet_id, _ = await create_spreadsheet("token", "T", ["A"])
    assert spreadsheet_id == "retried"
    assert len(httpx_mock.get_requests()) == 2
