"""Traduzioni delle stringhe fisse del report Google Sheets ed egli eventi
del job di export (fetta 3, PLAN_TAXONOMY_I18N.md) — nessuna libreria i18n
lato backend (a differenza del frontend), un semplice dict `{chiave: {it,
en}}`: evita che la stessa stringa sia hardcoded due volte in due punti.

Importante: i TITOLI DEI FOGLI (tab Sheets, es. "Riepilogo") NON sono
tradotti da questo modulo — sono fissati una volta sola alla connessione
Google (`_INITIAL_SHEET_TITLES` in `app/api/v1/integrations_google.py`) e
usati come identita' stabile per indirizzare le scritture
(`_SheetBuilder.value_range()`, `range: f"{self.title}!A1"`): rinominarli
dinamicamente per ogni export romperebbe l'indirizzamento verso i tab
esistenti (identificati per nome dalle Sheets API, non per id). Solo il
CONTENUTO scritto dentro i fogli (header, KPI, note, nomi categoria, titoli
dei grafici) segue la lingua della richiesta di export.
"""

STRINGS: dict[str, dict[str, str]] = {
    "riepilogo.title": {"it": "Lumio — Riepilogo ({date_from} → {date_to})", "en": "Lumio — Summary ({date_from} → {date_to})"},
    "riepilogo.kpi_header_indicator": {"it": "Indicatore", "en": "Indicator"},
    "riepilogo.kpi_header_value": {"it": "Valore", "en": "Value"},
    "riepilogo.kpi.liquidity": {"it": "Liquidità", "en": "Liquidity"},
    "riepilogo.kpi.debt": {"it": "Debiti", "en": "Debt"},
    "riepilogo.kpi.investments": {"it": "Investimenti (valore corrente)", "en": "Investments (current value)"},
    "riepilogo.kpi.income": {"it": "Entrate periodo", "en": "Period income"},
    "riepilogo.kpi.expenses": {"it": "Uscite periodo", "en": "Period expenses"},
    "riepilogo.kpi.net_cash_flow": {"it": "Cash flow netto periodo", "en": "Period net cash flow"},
    "riepilogo.kpi.pl": {
        "it": "P&L investimenti (realizzato + non realizzato)",
        "en": "Investment P&L (realized + unrealized)",
    },
    "riepilogo.trend_header_month": {"it": "Mese", "en": "Month"},
    "riepilogo.trend_header_income": {"it": "Entrate", "en": "Income"},
    "riepilogo.trend_header_expenses": {"it": "Uscite", "en": "Expenses"},
    "riepilogo.trend_chart_title": {"it": "Entrate/Uscite mensili", "en": "Monthly Income/Expenses"},
    "riepilogo.no_transactions": {
        "it": "Nessun movimento nel periodo selezionato.",
        "en": "No transactions in the selected period.",
    },
    "riepilogo.net_worth_header_date": {"it": "Data", "en": "Date"},
    "riepilogo.net_worth_header_value": {"it": "Patrimonio netto", "en": "Net worth"},
    "riepilogo.net_worth_chart_title": {"it": "Andamento patrimonio", "en": "Net worth over time"},
    "riepilogo.no_net_worth": {
        "it": "Nessuno snapshot di patrimonio ancora disponibile.",
        "en": "No net worth snapshot available yet.",
    },
    "transazioni.header_date": {"it": "Data", "en": "Date"},
    "transazioni.header_account": {"it": "Conto", "en": "Account"},
    "transazioni.header_description": {"it": "Descrizione", "en": "Description"},
    "transazioni.header_category": {"it": "Categoria", "en": "Category"},
    "transazioni.header_type": {"it": "Tipo", "en": "Type"},
    "transazioni.header_amount": {"it": "Importo", "en": "Amount"},
    "transazioni.header_currency": {"it": "Valuta", "en": "Currency"},
    "transazioni.no_category": {"it": "Senza categoria", "en": "Uncategorized"},
    "category_sheet.header_category": {"it": "Categoria", "en": "Category"},
    "category_sheet.header_total": {"it": "Totale", "en": "Total"},
    "category_sheet.header_share": {"it": "Quota", "en": "Share"},
    "category_sheet.header_count": {"it": "N. transazioni", "en": "Transaction count"},
    "category_sheet.no_transactions": {
        "it": "Nessun movimento nel periodo selezionato.",
        "en": "No transactions in the selected period.",
    },
    "category_sheet.income_chart_title": {"it": "Entrate per categoria", "en": "Income by category"},
    "category_sheet.expense_chart_title": {"it": "Uscite per categoria", "en": "Expenses by category"},
    "portfolio.header_asset": {"it": "Asset", "en": "Asset"},
    "portfolio.header_quantity": {"it": "Quantità", "en": "Quantity"},
    "portfolio.header_avg_cost": {"it": "Costo medio", "en": "Average cost"},
    "portfolio.header_market_value": {"it": "Valore corrente", "en": "Current value"},
    "portfolio.header_unrealized_pl": {"it": "P&L non realizzato", "en": "Unrealized P&L"},
    "portfolio.header_realized_pl": {"it": "P&L realizzato", "en": "Realized P&L"},
    "portfolio.no_market_data_note": {
        "it": "Nota: prezzi di mercato non disponibili per tutte le posizioni — valorizzazione a costo storico.",
        "en": "Note: market prices not available for all positions — valued at historical cost.",
    },
    "portfolio.alloc_header_type": {"it": "Tipo asset", "en": "Asset type"},
    "portfolio.alloc_header_value": {"it": "Valore", "en": "Value"},
    "portfolio.alloc_header_share": {"it": "Quota", "en": "Share"},
    "portfolio.alloc_chart_title": {"it": "Allocazione per tipo di asset", "en": "Allocation by asset type"},
    "portfolio.perf_header_date": {"it": "Data", "en": "Date"},
    "portfolio.perf_header_market_value": {"it": "Valore di mercato", "en": "Market value"},
    "portfolio.perf_header_unrealized_pl": {"it": "P&L non realizzato", "en": "Unrealized P&L"},
    "portfolio.perf_header_realized_pl": {"it": "P&L realizzato", "en": "Realized P&L"},
    "portfolio.perf_chart_title": {"it": "Performance portfolio nel tempo", "en": "Portfolio performance over time"},
    "portfolio.no_snapshot": {
        "it": "Nessuno snapshot di portfolio ancora disponibile.",
        "en": "No portfolio snapshot available yet.",
    },
    # `Transaction.transaction_type` (bonus fix, effetto collaterale della
    # ricerca fetta 3): prima stampato RAW nell'export, mai etichettato
    # nemmeno in italiano — stessi valori/etichette di
    # `frontend/src/locales/{it,en}/enums.json::transactionType`.
    "transaction_type.expense": {"it": "Spesa", "en": "Expense"},
    "transaction_type.income": {"it": "Entrata", "en": "Income"},
    "transaction_type.transfer": {"it": "Trasferimento", "en": "Transfer"},
    "transaction_type.investment": {"it": "Investimento", "en": "Investment"},
    "transaction_type.dividend": {"it": "Dividendo", "en": "Dividend"},
    "transaction_type.interest": {"it": "Interesse", "en": "Interest"},
    "transaction_type.fee": {"it": "Commissione", "en": "Fee"},
    "transaction_type.tax": {"it": "Tassa", "en": "Tax"},
    "transaction_type.refund": {"it": "Rimborso", "en": "Refund"},
    "transaction_type.adjustment": {"it": "Rettifica", "en": "Adjustment"},
    # Stage SSE + messaggi del job (google_export_job.py) — mostrati live in
    # ExportOptionsDialog.tsx: se restassero sempre italiani, un export in
    # inglese vedrebbe un mix di lingue durante il progresso.
    "export.stage.preparing": {"it": "preparazione", "en": "preparing"},
    "export.stage.computing": {"it": "calcolo dei dati", "en": "computing data"},
    "export.stage.writing": {"it": "scrittura su Google Sheets", "en": "writing to Google Sheets"},
    "export.completed_message": {"it": "Export completato: {count} fogli aggiornati", "en": "Export completed: {count} sheets updated"},
    "export.failed_message": {
        "it": "Impossibile completare l'export su Google Sheets",
        "en": "Could not complete the Google Sheets export",
    },
    "export.reauth_required_message": {
        "it": "L'accesso a Google è stato revocato: è necessario riconnettersi",
        "en": "Access to Google has been revoked: reconnection is required",
    },
}


def t(key: str, language: str, **kwargs) -> str:
    entry = STRINGS.get(key)
    if entry is None:
        raise KeyError(f"chiave di traduzione mancante in report_i18n.py: {key!r}")
    template = entry.get(language) or entry["it"]
    return template.format(**kwargs) if kwargs else template


def transaction_type_label(value: str, language: str) -> str:
    """Fallback al valore raw per un `transaction_type` non censito (mai
    dovrebbe accadere con l'enum attuale, ma un DB puo' sempre contenere
    dati non ancora migrati) — mai sollevare per questo."""
    entry = STRINGS.get(f"transaction_type.{value}")
    if entry is None:
        return value
    return entry.get(language) or entry["it"]
