"""Test unitari del client Drive API (milestone 10) — httpx mockato. Le
risposte sono registrate senza filtro `url` (match generico, consumate in
ordine FIFO): evita ambiguita' sull'ordine dei query param nel confronto
URL, verificato invece leggendo `httpx_mock.get_requests()`.
"""
import pytest

from app.integrations.google.drive_client import get_folder_name, move_file_to_folder
from app.integrations.google.errors import GoogleAPIError


async def test_move_file_to_folder_sends_add_and_remove_parents(httpx_mock):
    httpx_mock.add_response(json={"parents": ["old-parent"]})  # GET parents attuali
    httpx_mock.add_response(json={})  # PATCH move

    await move_file_to_folder("token", "file1", "new-parent")

    requests = httpx_mock.get_requests()
    assert requests[0].method == "GET"
    assert requests[0].url.path == "/drive/v3/files/file1"
    assert requests[1].method == "PATCH"
    assert dict(requests[1].url.params) == {"addParents": "new-parent", "removeParents": "old-parent"}


async def test_move_file_to_folder_to_root_when_folder_id_none(httpx_mock):
    httpx_mock.add_response(json={"parents": ["old-parent"]})
    httpx_mock.add_response(json={})

    await move_file_to_folder("token", "file1", None)

    assert dict(httpx_mock.get_requests()[1].url.params) == {"addParents": "root", "removeParents": "old-parent"}


async def test_move_file_to_folder_omits_remove_parents_when_none_exist(httpx_mock):
    httpx_mock.add_response(json={"parents": []})
    httpx_mock.add_response(json={})

    await move_file_to_folder("token", "file1", "new-parent")

    assert dict(httpx_mock.get_requests()[1].url.params) == {"addParents": "new-parent"}


async def test_move_file_to_folder_error_raises_domain_exception(httpx_mock):
    httpx_mock.add_response(status_code=500)
    with pytest.raises(GoogleAPIError):
        await move_file_to_folder("token", "file1", "new-parent")


async def test_get_folder_name(httpx_mock):
    httpx_mock.add_response(url="https://www.googleapis.com/drive/v3/files/folder1?fields=name", json={"name": "Finanze"})
    assert await get_folder_name("token", "folder1") == "Finanze"


async def test_get_folder_name_error_raises_domain_exception(httpx_mock):
    httpx_mock.add_response(status_code=404)
    with pytest.raises(GoogleAPIError):
        await get_folder_name("token", "missing")
