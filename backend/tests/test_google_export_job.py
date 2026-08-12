"""Test unitario della funzione pura che riabbina per titolo la posizione
di un grafico gia' presente nello spreadsheet — cosi' se l'utente ha
spostato manualmente un grafico (drag&drop per un layout piu' ordinato),
quella posizione sopravvive al prossimo export invece di tornare sempre
all'ancoraggio di default del report builder.
"""
from app.worker.jobs.google_export_job import _restore_chart_positions

_DEFAULT_POSITION = {"overlayPosition": {"anchorCell": {"sheetId": 0, "rowIndex": 1, "columnIndex": 6}}}
_MOVED_POSITION = {"overlayPosition": {"anchorCell": {"sheetId": 0, "rowIndex": 20, "columnIndex": 15}}}


def _chart_request(title: str) -> dict:
    return {"addChart": {"chart": {"spec": {"title": title}, "position": dict(_DEFAULT_POSITION)}}}


def test_restore_chart_positions_overrides_matching_title():
    requests = [_chart_request("Entrate/Uscite mensili")]
    positions_by_title = {"Entrate/Uscite mensili": _MOVED_POSITION}

    result = _restore_chart_positions(requests, positions_by_title)

    assert result[0]["addChart"]["chart"]["position"] == _MOVED_POSITION


def test_restore_chart_positions_keeps_default_when_no_saved_position():
    requests = [_chart_request("Un grafico nuovo mai visto prima")]

    result = _restore_chart_positions(requests, {})

    assert result[0]["addChart"]["chart"]["position"] == _DEFAULT_POSITION


def test_restore_chart_positions_ignores_non_chart_requests():
    format_request = {"repeatCell": {"range": {}}}
    requests = [format_request, _chart_request("Allocazione per tipo di asset")]
    positions_by_title = {"Allocazione per tipo di asset": _MOVED_POSITION}

    result = _restore_chart_positions(requests, positions_by_title)

    assert result[0] == format_request  # invariata
    assert result[1]["addChart"]["chart"]["position"] == _MOVED_POSITION
