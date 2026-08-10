"""Genera un PDF sintetico che riproduce il layout (a colonne, senza righe di
tabella disegnate) degli estratti conto Trade Republic, con dati interamente
inventati — nessun dato reale dell'utente finisce nel repository.

Ogni transazione occupa 3 sotto-righe come nel template reale (la colonna
DATA va sempre a capo su due righe, "01 mag" / "2026"; TIPO, DESCRIZIONE e
gli importi stanno sulla sotto-riga centrale, salvo la DESCRIZIONE che puo'
andare a capo sulla terza come per un "Savings plan execution" reale). Le
coordinate x (colonne DATA/TIPO/DESCRIZIONE/importi) e lo scarto verticale
tra sotto-righe ricadono dentro le soglie usate da
`app.parsers.trade_republic` (verificate empiricamente sull'estratto conto
reale durante lo sviluppo, non riproducibile qui per motivi di privacy).

Nota deliberata: qui TIPO sta sempre su una riga sola (nessun fixture
riproduce "Transazione con carta" a cavallo di due sotto-righe come nel PDF
reale) — quella ricostruzione multi-sottoriga e' gia' stata verificata
esaustivamente contro il PDF reale (84 occorrenze, zero discrepanze); qui
serve solo un fixture leggibile per testare meccanica generale e mappatura
TIPO->transaction_type, quest'ultima comunque testata anche direttamente
(vedi test_trade_republic_parser.py::test_transaction_type_mapping).
"""
import io

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

_FONT = ("Helvetica", 9)
_ROW_HEIGHT = 30.0
_SUBLINE = 5.0

_COL_DATA_X = 75.0
_COL_TIPO_X = 105.0
_COL_DESCR_X = 250.0
_COL_ENTRATA_X = 430.0
_COL_USCITA_X = 470.0
_COL_SALDO_X = 520.0


def _draw_row(
    c,
    y: float,
    day: str,
    month: str,
    tipo: str,
    descr_line1: str,
    descr_line2: str | None,
    entrata: str | None,
    uscita: str | None,
    saldo: str,
) -> None:
    c.drawString(_COL_DATA_X, y, f"{day} {month}")
    c.drawString(_COL_TIPO_X, y - _SUBLINE, tipo)
    c.drawString(_COL_DESCR_X, y - _SUBLINE, descr_line1)
    if entrata is not None:
        c.drawString(_COL_ENTRATA_X, y - _SUBLINE, entrata)
    if uscita is not None:
        c.drawString(_COL_USCITA_X, y - _SUBLINE, uscita)
    c.drawString(_COL_SALDO_X, y - _SUBLINE, saldo)
    c.drawString(_COL_DATA_X, y - 2 * _SUBLINE, "2026")
    if descr_line2 is not None:
        c.drawString(_COL_DESCR_X, y - 2 * _SUBLINE, descr_line2)


def build_fixture_pdf() -> bytes:
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    _, height = A4
    c.setFont(*_FONT)

    c.drawString(75, height - 60, "TRADE REPUBLIC BANK GMBH, BRANCH ITALY SPACES GAE AULENTI")
    c.drawString(75, height - 75, "IBAN IT00X0000000000000000000000 BIC TRBKITMMXXX")

    c.drawString(_COL_DATA_X, height - 120, "DATA")
    c.drawString(_COL_TIPO_X, height - 120, "TIPO")
    c.drawString(_COL_DESCR_X, height - 120, "DESCRIZIONE")
    c.drawString(_COL_ENTRATA_X, height - 120, "IN ENTRATA")
    c.drawString(_COL_USCITA_X, height - 120, "IN USCITA")
    c.drawString(_COL_SALDO_X, height - 120, "SALDO")

    y = height - 160

    _draw_row(c, y, "01", "mag", "Premio", "Cash reward allocation", None, "8,38", None, "1.008,38")
    y -= _ROW_HEIGHT

    _draw_row(c, y, "02", "mag", "Interessi", "Interest payment", None, "5,00", None, "1.013,38")
    y -= _ROW_HEIGHT

    _draw_row(
        c, y, "03", "mag", "Commercio",
        "Savings plan execution TEST1234567",
        "quantity: 5",
        None, "50,00", "963,38",
    )
    y -= _ROW_HEIGHT

    _draw_row(c, y, "04", "mag", "Bonifico", "Incoming transfer test", None, "500,00", None, "1.463,38")
    y -= _ROW_HEIGHT

    _draw_row(c, y, "05", "mag", "Imposte", "Stamp Duty Tax", None, None, "2,50", "1.460,88")
    y -= _ROW_HEIGHT

    c.showPage()
    c.save()
    return buffer.getvalue()


def build_non_pdf_bytes_with_pdf_looking_name() -> bytes:
    """Contenuto chiaramente binario (magic byte PNG) senza alcuna relazione
    con un PDF — usato per verificare che rinominarlo con estensione `.pdf`
    non basti a farlo accettare (DoD milestone 05): la classificazione del
    canale si basa sul CONTENUTO (magic byte `%PDF-`), mai sul nome file
    dichiarato dal client, quindi questo finisce comunque respinto come
    "non riconosciuto" indipendentemente da come viene chiamato l'upload."""
    return b"\x89PNG\r\n\x1a\n" + b"finto pdf, in realta' un binario qualunque" * 5
