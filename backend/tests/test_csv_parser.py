from decimal import Decimal

from app.services.csv_import import ColumnsConfig, MappingConfig, detect_mapping, parse_rows


def test_single_signed_amount_negative_is_debit():
    config = MappingConfig(
        columns=ColumnsConfig(transaction_date="data", description_raw="descrizione", amount="importo"),
    )
    text = "data,descrizione,importo\n2026-01-15,Supermercato,-42.50\n2026-01-16,Stipendio,1500.00\n"

    rows, warnings = parse_rows(text, config)

    assert warnings == []
    assert len(rows) == 2
    assert rows[0].amount == Decimal("-42.50")
    assert rows[0].direction == "debit"
    assert rows[0].transaction_type == "expense"
    assert rows[1].amount == Decimal("1500.00")
    assert rows[1].direction == "credit"
    assert rows[1].transaction_type == "income"


def test_description_raw_is_never_altered():
    config = MappingConfig(
        columns=ColumnsConfig(transaction_date="data", description_raw="descrizione", amount="importo"),
    )
    raw_description = "  PAGAMENTO   POS   ESERCIZIO   123  "
    text = f"data,descrizione,importo\n2026-01-15,{raw_description},-10.00\n"

    rows, _warnings = parse_rows(text, config)

    assert rows[0].description_raw == raw_description
    # Solo la versione normalizzata collassa gli spazi.
    assert rows[0].description_normalized == "PAGAMENTO POS ESERCIZIO 123"


def test_italian_decimal_comma_and_thousands_dot():
    # Delimitatore `;`, non `,`: un CSV con virgola come decimale non puo'
    # usare la virgola anche come delimitatore di campo.
    config = MappingConfig(
        delimiter=";",
        decimal_separator=",",
        thousands_separator=".",
        columns=ColumnsConfig(transaction_date="data", description_raw="descrizione", amount="importo"),
    )
    text = "data;descrizione;importo\n2026-01-15;Bonifico;-1.234,56\n"

    rows, warnings = parse_rows(text, config)

    assert warnings == []
    assert rows[0].amount == Decimal("-1234.56")


def test_custom_date_format():
    config = MappingConfig(
        date_format="%d/%m/%Y",
        columns=ColumnsConfig(transaction_date="data", description_raw="descrizione", amount="importo"),
    )
    text = "data,descrizione,importo\n15/01/2026,Spesa,-5.00\n"

    rows, warnings = parse_rows(text, config)

    assert warnings == []
    assert rows[0].transaction_date.isoformat() == "2026-01-15"


def test_separate_debit_credit_columns():
    config = MappingConfig(
        amount_mode="separate_debit_credit",
        columns=ColumnsConfig(
            transaction_date="data",
            description_raw="descrizione",
            amount_debit="dare",
            amount_credit="avere",
        ),
    )
    text = "data,descrizione,dare,avere\n2026-01-15,Spesa,42.50,\n2026-01-16,Stipendio,,1500.00\n"

    rows, warnings = parse_rows(text, config)

    assert warnings == []
    assert rows[0].amount == Decimal("-42.50")
    assert rows[0].direction == "debit"
    assert rows[1].amount == Decimal("1500.00")
    assert rows[1].direction == "credit"


def test_separate_debit_credit_row_with_neither_is_a_warning_not_a_crash():
    config = MappingConfig(
        amount_mode="separate_debit_credit",
        columns=ColumnsConfig(
            transaction_date="data",
            description_raw="descrizione",
            amount_debit="dare",
            amount_credit="avere",
        ),
    )
    text = "data,descrizione,dare,avere\n2026-01-15,Spesa senza importo,,\n"

    rows, warnings = parse_rows(text, config)

    assert rows == []
    assert len(warnings) == 1
    assert "riga 2" in warnings[0]
    # Il warning non deve contenere il contenuto della riga (SPEC §55).
    assert "Spesa senza importo" not in warnings[0]


def test_single_absolute_with_direction_marker():
    config = MappingConfig(
        amount_mode="single_absolute_with_direction",
        columns=ColumnsConfig(
            transaction_date="data",
            description_raw="descrizione",
            amount="importo",
            direction="tipo",
        ),
    )
    text = "data,descrizione,importo,tipo\n2026-01-15,Spesa,42.50,Dare\n2026-01-16,Entrata,10.00,Avere\n"

    rows, warnings = parse_rows(text, config)

    assert warnings == []
    assert rows[0].amount == Decimal("-42.50")
    assert rows[0].direction == "debit"
    assert rows[1].amount == Decimal("10.00")
    assert rows[1].direction == "credit"


def test_malformed_date_is_skipped_with_warning():
    config = MappingConfig(
        columns=ColumnsConfig(transaction_date="data", description_raw="descrizione", amount="importo"),
    )
    text = (
        "data,descrizione,importo\n"
        "not-a-date,Spesa rotta,-10.00\n"
        "2026-01-16,Spesa valida,-5.00\n"
    )

    rows, warnings = parse_rows(text, config)

    assert len(rows) == 1
    assert rows[0].description_raw == "Spesa valida"
    assert len(warnings) == 1
    assert "riga 2" in warnings[0]
    assert "Spesa rotta" not in warnings[0]


def test_skip_rows_ignores_leading_junk_lines():
    config = MappingConfig(
        skip_rows=2,
        columns=ColumnsConfig(transaction_date="data", description_raw="descrizione", amount="importo"),
    )
    text = (
        "Estratto conto gennaio 2026\n"
        "IBAN: IT00X0000000000000000000000\n"
        "data,descrizione,importo\n"
        "2026-01-15,Spesa,-10.00\n"
    )

    rows, warnings = parse_rows(text, config)

    assert warnings == []
    assert len(rows) == 1


def test_amount_mode_validation_rejects_missing_columns():
    import pytest

    with pytest.raises(ValueError, match="single_signed richiede"):
        MappingConfig(
            amount_mode="single_signed",
            columns=ColumnsConfig(transaction_date="data", description_raw="descrizione"),
        )


def test_detect_mapping_recognizes_italian_headers_and_semicolon_delimiter():
    sample = (
        "Data;Descrizione;Importo\n"
        "15/01/2026;Supermercato;-42,50\n"
        "16/01/2026;Stipendio;1500,00\n"
    )

    mapping = detect_mapping(sample)

    assert mapping.delimiter == ";"
    assert mapping.decimal_separator == ","
    assert mapping.date_format == "%d/%m/%Y"
    assert mapping.columns.transaction_date == "Data"
    assert mapping.columns.description_raw == "Descrizione"
    assert mapping.columns.amount == "Importo"
    assert mapping.amount_mode == "single_signed"


def test_detect_mapping_recognizes_separate_debit_credit_columns():
    sample = "Data,Descrizione,Dare,Avere\n2026-01-15,Spesa,42.50,\n2026-01-16,Entrata,,10.00\n"

    mapping = detect_mapping(sample)

    assert mapping.amount_mode == "separate_debit_credit"
    assert mapping.columns.amount_debit == "Dare"
    assert mapping.columns.amount_credit == "Avere"


def test_detect_mapping_produces_a_config_that_parses_its_own_sample():
    sample = (
        "Data;Descrizione;Importo\n"
        "15/01/2026;Supermercato;-42,50\n"
        "16/01/2026;Stipendio;1500,00\n"
    )

    mapping = detect_mapping(sample)
    rows, warnings = parse_rows(sample, mapping)

    assert warnings == []
    assert len(rows) == 2
    assert rows[0].amount == Decimal("-42.50")
