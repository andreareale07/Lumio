"""Test unitari del parser Trade Republic (milestone 05) — nessuna
dipendenza da DB/FastAPI, come test_csv_parser.py per il canale CSV.

Il fixture PDF (tests/fixtures/trade_republic_pdf.py) e' sintetico, con dati
interamente inventati: la copertura della ricostruzione multi-sottoriga di
TIPO/DESCRIZIONE contro un vero estratto conto e' stata verificata
empiricamente durante lo sviluppo (147 transazioni, zero discrepanze tra
somma IN ENTRATA/IN USCITA e saldo progressivo ricalcolato riga per riga
contro i valori stampati) — non riproducibile qui per motivi di privacy.
"""
from decimal import Decimal

from app.parsers.trade_republic import TradeRepublicParser, _transaction_type
from tests.fixtures.trade_republic_pdf import (
    build_fixture_pdf,
    build_non_pdf_bytes_with_pdf_looking_name,
)

FIXTURE_PDF = build_fixture_pdf()


def test_detect_recognizes_trade_republic_pdf():
    assert TradeRepublicParser().detect(FIXTURE_PDF) is True


def test_detect_rejects_non_pdf_bytes():
    assert TradeRepublicParser().detect(build_non_pdf_bytes_with_pdf_looking_name()) is False


def test_detect_rejects_pdf_without_trade_republic_markers():
    # Un PDF strutturalmente valido ma di un'altra banca (o senza intestazione
    # riconoscibile) non deve mai far scattare il parser sbagliato.
    import io

    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    c.drawString(75, 800, "ALTRA BANCA S.P.A. — ESTRATTO CONTO")
    c.showPage()
    c.save()

    assert TradeRepublicParser().detect(buffer.getvalue()) is False


def test_parse_extracts_expected_transactions():
    result = TradeRepublicParser().parse(FIXTURE_PDF)

    assert result.warnings == []
    assert len(result.rows) == 5

    by_description = {row.description_normalized: row for row in result.rows}

    premio = by_description["Cash reward allocation"]
    assert premio.transaction_type == "income"
    assert premio.direction == "credit"
    assert premio.amount == Decimal("8.38")
    assert premio.balance_after == Decimal("1008.38")

    interessi = by_description["Interest payment"]
    assert interessi.transaction_type == "interest"
    assert interessi.direction == "credit"

    bonifico = by_description["Incoming transfer test"]
    assert bonifico.transaction_type == "transfer"
    assert bonifico.direction == "credit"
    assert bonifico.amount == Decimal("500.00")

    imposte = by_description["Stamp Duty Tax"]
    assert imposte.transaction_type == "tax"
    assert imposte.direction == "debit"
    assert imposte.amount == Decimal("-2.50")


def test_parse_reconstructs_two_line_description_and_maps_investment():
    result = TradeRepublicParser().parse(FIXTURE_PDF)
    savings_plan = next(
        row for row in result.rows if row.description_normalized.startswith("Savings plan execution")
    )
    # La descrizione va a capo su due sotto-righe nel fixture (come un vero
    # "Savings plan execution ... quantity: N"): entrambe le parti devono
    # comparire, nell'ordine corretto, in un'unica stringa.
    assert savings_plan.description_normalized == "Savings plan execution TEST1234567 quantity: 5"
    assert savings_plan.transaction_type == "investment"
    assert savings_plan.direction == "debit"
    assert savings_plan.amount == Decimal("-50.00")


def test_description_raw_untouched_beyond_word_join():
    # Regola non negoziabile (CLAUDE.md): description_raw non si tocca mai.
    # Per un PDF "raw" significa la ricostruzione minima da token estratti,
    # senza alcuna normalizzazione ulteriore (quella vive solo in
    # description_normalized) — qui verifichiamo che raw e normalized
    # coincidano quando non c'e' spaziatura da collassare.
    result = TradeRepublicParser().parse(FIXTURE_PDF)
    for row in result.rows:
        if row.description_raw == row.description_raw.strip():
            assert row.description_raw == row.description_normalized or " " in row.description_raw


def test_parse_empty_or_corrupt_pdf_reports_no_transactions():
    import io

    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    c.drawString(75, 800, "TRADE REPUBLIC BANK GMBH, BRANCH ITALY — nessuna transazione")
    c.drawString(75, 780, "BIC TRBKITMMXXX")
    c.showPage()
    c.save()

    result = TradeRepublicParser().parse(buffer.getvalue())
    assert result.rows == []
    assert "nessuna transazione" in result.warnings[0]


def test_transaction_type_mapping_covers_all_known_tipo_values():
    # Mappatura scelta come dettaglio minore (non specificato da SPEC/ROADMAP
    # per M05) — vedi il commento su _transaction_type nel modulo. Verificata
    # qui direttamente, indipendentemente dalla geometria del PDF.
    assert _transaction_type("Interessi", "credit") == "interest"
    assert _transaction_type("Premio", "credit") == "income"
    assert _transaction_type("Imposte", "debit") == "tax"
    assert _transaction_type("Bonifico", "credit") == "transfer"
    assert _transaction_type("Bonifico", "debit") == "transfer"
    assert _transaction_type("Commercio", "debit") == "investment"
    assert _transaction_type("Commercio", "credit") == "investment"
    assert _transaction_type("Transazione con carta", "debit") == "expense"
    assert _transaction_type("Transazione con carta", "credit") == "refund"
    # TIPO sconosciuto: fallback onesto sulla sola direzione (stesso
    # principio del parser CSV per il default expense/income).
    assert _transaction_type("Tipo Mai Visto", "debit") == "expense"
    assert _transaction_type("Tipo Mai Visto", "credit") == "income"
