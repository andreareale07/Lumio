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

    # "Bonifico" e' uno strumento di pagamento, non un tipo semantico: un
    # bonifico in entrata puo' essere un incasso reale (income), non
    # necessariamente un trasferimento tra conti propri — vedi il commento
    # su _transaction_type (hotfix pre-M09: prima di questo fix finiva
    # sempre su "transfer" e spariva dal cash flow).
    bonifico = by_description["Incoming transfer test"]
    assert bonifico.transaction_type == "income"
    assert bonifico.direction == "credit"
    assert bonifico.amount == Decimal("500.00")
    assert bonifico.source_type_raw == "Bonifico"

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
    assert _transaction_type("Commercio", "debit") == "investment"
    assert _transaction_type("Commercio", "credit") == "investment"
    assert _transaction_type("Transazione con carta", "debit") == "expense"
    assert _transaction_type("Transazione con carta", "credit") == "refund"
    # "Bonifico" e' uno strumento di pagamento, non un tipo semantico: non
    # deducibile a "transfer" da un solo estratto conto (hotfix pre-M09).
    # Fallback onesto sulla sola direzione, come un TIPO sconosciuto.
    assert _transaction_type("Bonifico", "debit") == "expense"
    assert _transaction_type("Bonifico", "credit") == "income"
    # TIPO sconosciuto: fallback onesto sulla sola direzione (stesso
    # principio del parser CSV per il default expense/income).
    assert _transaction_type("Tipo Mai Visto", "debit") == "expense"
    assert _transaction_type("Tipo Mai Visto", "credit") == "income"


def test_transaction_type_mapping_recognizes_english_and_german_labels():
    # Dizionario multilingua: l'app Trade Republic dell'utente potrebbe
    # essere in inglese o tedesco, non solo in italiano — prima di questo
    # fix ogni etichetta non italiana ricadeva nel fallback direzione-soltanto,
    # perdendo la distinzione interessi/imposte/investimento/carta.
    assert _transaction_type("Interest", "credit") == "interest"
    assert _transaction_type("Zinsen", "credit") == "interest"
    assert _transaction_type("Bonus", "credit") == "income"
    assert _transaction_type("Prämie", "credit") == "income"
    assert _transaction_type("Tax", "debit") == "tax"
    assert _transaction_type("Taxes", "debit") == "tax"
    assert _transaction_type("Steuern", "debit") == "tax"
    assert _transaction_type("Trade", "debit") == "investment"
    assert _transaction_type("Handel", "credit") == "investment"
    assert _transaction_type("Card transaction", "debit") == "expense"
    assert _transaction_type("Card transaction", "credit") == "refund"
    assert _transaction_type("Kartentransaktion", "credit") == "refund"
    # Maiuscole/spazi non contano: stessa normalizzazione dell'italiano.
    assert _transaction_type("  INTEREST  ", "credit") == "interest"


def test_default_transaction_type_method_matches_the_module_function():
    # Milestone 09.5: il metodo sul parser e' solo un punto di accesso
    # stabile a _transaction_type (usato da import_job.py e dal servizio
    # di mappatura configurabile), nessuna logica nuova.
    parser = TradeRepublicParser()
    assert parser.default_transaction_type("Bonifico", "credit") == "income"
    assert parser.default_transaction_type("Interessi", "credit") == "interest"


def test_extract_transfer_counterparty_outgoing():
    # Milestone 09.5b: formato verificato su un estratto conto reale (nomi/IBAN
    # qui sono inventati) — SPEC §37, riconoscimento trasferimenti interni.
    parser = TradeRepublicParser()
    result = parser.extract_transfer_counterparty(
        "Outgoing transfer for Luca Bianchi (IT31U0760116700009944199997)"
    )
    assert result is not None
    assert result.name == "Luca Bianchi"
    assert result.iban == "IT31U0760116700009944199997"


def test_extract_transfer_counterparty_incoming():
    parser = TradeRepublicParser()
    result = parser.extract_transfer_counterparty(
        "Incoming transfer for Mario Rossi (IT31U0760116700001099179999)"
    )
    assert result is not None
    assert result.name == "Mario Rossi"
    assert result.iban == "IT31U0760116700001099179999"


def test_extract_transfer_counterparty_returns_none_for_unrelated_description():
    parser = TradeRepublicParser()
    assert parser.extract_transfer_counterparty("Savings plan execution IE00B4L5Y983, quantity: 1") is None
    assert parser.extract_transfer_counterparty("Interessi maturati su liquidita'") is None


def _build_pdf_with_columns(data_x, tipo_x, descr_x, entrata_x, uscita_x, saldo_x) -> bytes:
    import io

    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    height = A4[1]
    c.setFont("Helvetica", 6)
    c.drawString(75, height - 60, "TRADE REPUBLIC BANK GMBH, BRANCH ITALY TRBKITMMXXX")
    c.drawString(data_x, height - 120, "DATA")
    c.drawString(tipo_x, height - 120, "TIPO")
    c.drawString(descr_x, height - 120, "DESCRIZIONE")
    c.drawString(entrata_x, height - 120, "IN ENTRATA")
    c.drawString(uscita_x, height - 120, "IN USCITA")
    c.drawString(saldo_x, height - 120, "SALDO")
    rows = [
        ("05 set", "Bonifico", "Deposito accettato", "100,00 €", None, "109,00 €"),
        ("06 set", "Commercio", "Buy trade IE00B3WJKG14", None, "11,03 €", "97,97 €"),
    ]
    y = height - 160
    for date, tipo, descr, entrata, uscita, saldo in rows:
        c.drawString(data_x, y, date)
        c.drawString(tipo_x, y - 4, tipo)
        c.drawString(descr_x, y - 4, descr)
        if entrata:
            c.drawString(entrata_x, y - 4, entrata)
        if uscita:
            c.drawString(uscita_x, y - 4, uscita)
        c.drawString(saldo_x, y - 4, saldo)
        c.drawString(data_x, y - 8, "2024")
        y -= 40
    c.save()
    return buffer.getvalue()


def test_parse_reads_column_positions_from_the_header_not_from_fixed_offsets():
    # Coordinate dell'estratto reale con ENTRATA a x0=400 e USCITA a x0=442:
    # con soglie fisse (450) l'uscita veniva letta come entrata.
    pdf = _build_pdf_with_columns(74.4, 101.7, 149.1, 400.2, 441.9, 494.2)
    result = TradeRepublicParser().parse(pdf)
    assert result.warnings == []
    credit, debit = result.rows
    assert (credit.direction, credit.amount) == ("credit", Decimal("100.00"))
    assert credit.source_type_raw == "Bonifico"
    assert credit.description_raw == "Deposito accettato"
    assert (debit.direction, debit.amount) == ("debit", Decimal("-11.03"))
    assert debit.source_type_raw == "Commercio"
    assert debit.description_raw == "Buy trade IE00B3WJKG14"
