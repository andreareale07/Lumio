"""Assembla il contenuto del report Google Sheets (milestone 10): quali
fogli, quali righe, quale formattazione e quali grafici nativi. Non tocca
mai la rete Google (quello vive in `sheets_client.py`) — riusa SEMPRE i
service esistenti (`app/services/analytics.py`,
`app/services/portfolio_analytics.py`) per i numeri, nessuna query
duplicata: questo modulo si limita ad assemblare cio' che quei service
ritornano gia' in una struttura di fogli/celle/grafici.

Decisione di prodotto (concordata con l'utente): non un dump di
transazioni, uno strumento di reportistica — un foglio Riepilogo con KPI +
trend + grafici, breakdown categorie con grafici a torta, un foglio
Portfolio con P&L per singola posizione (solo se il workspace ha posizioni
aperte). Ogni grafico e' omesso, non lasciato vuoto, se non ci sono
abbastanza dati (stesso principio della DoD M08 "ogni grafico ha un empty
state sensato, non un grafico vuoto").
"""
import uuid
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.classification.taxonomy import TAXONOMY_BY_CODE
from app.integrations.google.report_i18n import t, transaction_type_label
from app.models.category import Category
from app.models.financial_account import FinancialAccount
from app.models.transaction import Transaction
from app.services import analytics, portfolio_analytics


@dataclass
class ReportOptions:
    date_from: date
    date_to: date
    include_portfolio: bool | None = None  # None = automatico (has_holdings)
    include_charts: bool = True
    # Fetta 3 (PLAN_TAXONOMY_I18N.md): lingua del CONTENUTO scritto nei
    # fogli (header, KPI, note, nomi categoria, titoli grafici) — segue la
    # lingua UI scelta dall'utente al momento dell'export. NON i titoli dei
    # tab stessi (vedi report_i18n.py): quelli restano fissi, decisi una
    # volta sola alla connessione Google.
    language: str = "it"


@dataclass
class ReportContent:
    sheet_titles: list[str]
    value_ranges: list[dict]
    requests: list[dict]


# --- costruzione dict di richiesta Sheets API (GridRange/chart/format) ------


def _grid_range(sheet_id: int, start_row: int, end_row: int, start_col: int, end_col: int) -> dict:
    return {
        "sheetId": sheet_id,
        "startRowIndex": start_row,
        "endRowIndex": end_row,
        "startColumnIndex": start_col,
        "endColumnIndex": end_col,
    }


def _bold_header_request(sheet_id: int, row_index: int, num_columns: int) -> dict:
    return {
        "repeatCell": {
            "range": _grid_range(sheet_id, row_index, row_index + 1, 0, num_columns),
            "cell": {"userEnteredFormat": {"textFormat": {"bold": True}}},
            "fields": "userEnteredFormat.textFormat.bold",
        }
    }


def _number_format_request(sheet_id: int, start_row: int, end_row: int, col: int, fmt_type: str, pattern: str) -> dict:
    return {
        "repeatCell": {
            "range": _grid_range(sheet_id, start_row, end_row, col, col + 1),
            "cell": {"userEnteredFormat": {"numberFormat": {"type": fmt_type, "pattern": pattern}}},
            "fields": "userEnteredFormat.numberFormat",
        }
    }


def _currency_format_request(sheet_id: int, start_row: int, end_row: int, col: int, currency: str) -> dict:
    pattern = "€#,##0.00" if currency == "EUR" else f'"{currency}" #,##0.00'
    return _number_format_request(sheet_id, start_row, end_row, col, "CURRENCY", pattern)


def _percent_format_request(sheet_id: int, start_row: int, end_row: int, col: int) -> dict:
    return _number_format_request(sheet_id, start_row, end_row, col, "PERCENT", "0.0%")


def _column_chart_request(sheet_id: int, title: str, domain: dict, series: list[dict], anchor_row: int) -> dict:
    return {
        "addChart": {
            "chart": {
                "spec": {
                    "title": title,
                    "basicChart": {
                        "chartType": "COLUMN",
                        "domains": [{"domain": {"sourceRange": {"sources": [domain]}}}],
                        "series": [{"series": {"sourceRange": {"sources": [s]}}} for s in series],
                    },
                },
                "position": {
                    "overlayPosition": {"anchorCell": {"sheetId": sheet_id, "rowIndex": anchor_row, "columnIndex": 6}}
                },
            }
        }
    }


def _line_chart_request(sheet_id: int, title: str, domain: dict, series: dict, anchor_row: int) -> dict:
    return {
        "addChart": {
            "chart": {
                "spec": {
                    "title": title,
                    "basicChart": {
                        "chartType": "LINE",
                        "domains": [{"domain": {"sourceRange": {"sources": [domain]}}}],
                        "series": [{"series": {"sourceRange": {"sources": [series]}}}],
                    },
                },
                "position": {
                    "overlayPosition": {"anchorCell": {"sheetId": sheet_id, "rowIndex": anchor_row, "columnIndex": 6}}
                },
            }
        }
    }


def _pie_chart_request(sheet_id: int, title: str, domain: dict, series: dict, anchor_row: int) -> dict:
    return {
        "addChart": {
            "chart": {
                "spec": {
                    "title": title,
                    "pieChart": {
                        "legendPosition": "RIGHT_LEGEND",
                        "domain": {"sourceRange": {"sources": [domain]}},
                        "series": {"sourceRange": {"sources": [series]}},
                    },
                },
                "position": {
                    "overlayPosition": {"anchorCell": {"sheetId": sheet_id, "rowIndex": anchor_row, "columnIndex": 4}}
                },
            }
        }
    }


@dataclass
class _SheetBuilder:
    """Accumula righe/formattazione/grafici per UN tab, tenendo traccia
    dell'indice di riga corrente cosi' i range dei grafici si calcolano da
    soli invece di essere hardcoded (la lunghezza di ogni tabella dipende
    dai dati reali, non e' fissa)."""

    sheet_id: int
    title: str
    rows: list[list] = field(default_factory=list)
    format_requests: list[dict] = field(default_factory=list)
    chart_requests: list[dict] = field(default_factory=list)

    def add_row(self, *cells) -> int:
        self.rows.append(list(cells))
        return len(self.rows) - 1

    def add_blank_row(self) -> None:
        self.rows.append([])

    def add_table(self, headers: list[str], data_rows: list[list]) -> int:
        """Ritorna l'indice della riga di header; i dati partono alla riga successiva."""
        header_row = self.add_row(*headers)
        for row in data_rows:
            self.add_row(*row)
        self.format_requests.append(_bold_header_request(self.sheet_id, header_row, len(headers)))
        return header_row

    def value_range(self) -> dict:
        return {"range": f"{self.title}!A1", "values": self.rows}


def _to_month_label(d: date) -> str:
    return d.strftime("%Y-%m")


def _f(value) -> float:
    return float(value)


def _category_display_name(name: str, code: str | None, is_system: bool, language: str) -> str:
    """Stesso branch `is_system` di `ai_classification.py::load_category_options`
    e `frontend/src/features/categories/utils.ts::categoryDisplayName`
    (fetta 1/2): SOLO le categorie di sistema hanno una traduzione nota in
    `TAXONOMY_BY_CODE` — quelle utente restano sempre il loro `name` libero,
    indipendentemente dalla lingua dell'export."""
    if language == "en" and is_system and code is not None:
        entry = TAXONOMY_BY_CODE.get(code)
        if entry is not None and entry.name_en:
            return entry.name_en
    return name


# --- singoli fogli -----------------------------------------------------------


def _build_riepilogo(
    sheet: _SheetBuilder,
    summary: dict,
    monthly: list[dict],
    net_worth_rows: list,
    valuation,
    currency: str,
    include_charts: bool,
    language: str,
) -> None:
    sheet.add_row(
        t(
            "riepilogo.title",
            language,
            date_from=summary["period"]["date_from"],
            date_to=summary["period"]["date_to"],
        )
    )
    sheet.add_blank_row()
    kpi_start = sheet.add_row(t("riepilogo.kpi_header_indicator", language), t("riepilogo.kpi_header_value", language))
    sheet.format_requests.append(_bold_header_request(sheet.sheet_id, kpi_start, 2))
    total_pl = _f(valuation.unrealized_pl + valuation.realized_pl)
    kpi_rows = [
        (t("riepilogo.kpi.liquidity", language), _f(summary["liquidity"])),
        (t("riepilogo.kpi.debt", language), _f(summary["debt"])),
        (t("riepilogo.kpi.investments", language), _f(summary["investments"])),
        (t("riepilogo.kpi.income", language), _f(summary["income"])),
        (t("riepilogo.kpi.expenses", language), _f(summary["expenses"])),
        (t("riepilogo.kpi.net_cash_flow", language), _f(summary["net_cash_flow"])),
        (t("riepilogo.kpi.pl", language), total_pl),
    ]
    first_kpi_data_row = kpi_start + 1
    for label, value in kpi_rows:
        sheet.add_row(label, value)
    last_kpi_data_row = len(sheet.rows)
    sheet.format_requests.append(
        _currency_format_request(sheet.sheet_id, first_kpi_data_row, last_kpi_data_row, 1, currency)
    )
    sheet.add_blank_row()

    # Trend mensile entrate/uscite (cash_flow granularity=month).
    if monthly:
        trend_header_row = sheet.add_table(
            [t("riepilogo.trend_header_month", language), t("riepilogo.trend_header_income", language), t("riepilogo.trend_header_expenses", language)],
            [[_to_month_label(m["period"]), _f(m["income"]), _f(m["expenses"])] for m in monthly],
        )
        data_start = trend_header_row + 1
        data_end = data_start + len(monthly)
        sheet.format_requests.append(_currency_format_request(sheet.sheet_id, data_start, data_end, 1, currency))
        sheet.format_requests.append(_currency_format_request(sheet.sheet_id, data_start, data_end, 2, currency))
        if include_charts and len(monthly) >= 1:
            sheet.chart_requests.append(
                _column_chart_request(
                    sheet.sheet_id,
                    t("riepilogo.trend_chart_title", language),
                    _grid_range(sheet.sheet_id, data_start, data_end, 0, 1),
                    [
                        _grid_range(sheet.sheet_id, trend_header_row, data_end, 1, 2),
                        _grid_range(sheet.sheet_id, trend_header_row, data_end, 2, 3),
                    ],
                    trend_header_row,
                )
            )
    else:
        sheet.add_row(t("riepilogo.no_transactions", language))
    sheet.add_blank_row()

    # Andamento patrimonio (net worth snapshot) — solo se ne esistono gia'.
    if net_worth_rows:
        nw_header_row = sheet.add_table(
            [t("riepilogo.net_worth_header_date", language), t("riepilogo.net_worth_header_value", language)],
            [[s.snapshot_date.isoformat(), _f(s.net_worth)] for s in net_worth_rows],
        )
        data_start = nw_header_row + 1
        data_end = data_start + len(net_worth_rows)
        sheet.format_requests.append(_currency_format_request(sheet.sheet_id, data_start, data_end, 1, currency))
        if include_charts:
            sheet.chart_requests.append(
                _line_chart_request(
                    sheet.sheet_id,
                    t("riepilogo.net_worth_chart_title", language),
                    _grid_range(sheet.sheet_id, data_start, data_end, 0, 1),
                    _grid_range(sheet.sheet_id, nw_header_row, data_end, 1, 2),
                    nw_header_row,
                )
            )
    else:
        sheet.add_row(t("riepilogo.no_net_worth", language))


async def _build_transazioni(
    db: AsyncSession, sheet: _SheetBuilder, workspace_id: uuid.UUID, options: ReportOptions
) -> None:
    query = (
        select(
            Transaction.transaction_date,
            FinancialAccount.name.label("account_name"),
            Transaction.description_normalized,
            Transaction.description_raw,
            Category.name.label("category_name"),
            Category.code.label("category_code"),
            Category.is_system.label("category_is_system"),
            Transaction.transaction_type,
            Transaction.amount,
            Transaction.currency,
        )
        .join(FinancialAccount, Transaction.financial_account_id == FinancialAccount.id)
        .outerjoin(Category, Transaction.category_id == Category.id)
        .where(
            Transaction.workspace_id == workspace_id,
            Transaction.transaction_date >= options.date_from,
            Transaction.transaction_date <= options.date_to,
        )
        .order_by(Transaction.transaction_date.desc())
    )
    rows = (await db.execute(query)).all()
    language = options.language

    header_row = sheet.add_table(
        [
            t("transazioni.header_date", language),
            t("transazioni.header_account", language),
            t("transazioni.header_description", language),
            t("transazioni.header_category", language),
            t("transazioni.header_type", language),
            t("transazioni.header_amount", language),
            t("transazioni.header_currency", language),
        ],
        [
            [
                r.transaction_date.isoformat(),
                r.account_name,
                r.description_normalized or r.description_raw,
                _category_display_name(r.category_name, r.category_code, bool(r.category_is_system), language)
                if r.category_name
                else t("transazioni.no_category", language),
                transaction_type_label(r.transaction_type, language),
                _f(r.amount),
                r.currency,
            ]
            for r in rows
        ],
    )
    if rows:
        # Formato numerico semplice, non un simbolo di valuta specifico: la
        # colonna "Valuta" gia' etichetta ogni riga, e un workspace puo'
        # avere conti in valute diverse (a differenza degli altri fogli,
        # che lavorano tutti nella valuta prevalente risolta da
        # `analytics.resolve_currency`).
        data_start = header_row + 1
        data_end = data_start + len(rows)
        sheet.format_requests.append(_number_format_request(sheet.sheet_id, data_start, data_end, 5, "NUMBER", "#,##0.00"))


def _build_category_sheet(
    sheet: _SheetBuilder, rows: list[dict], currency: str, include_charts: bool, chart_title: str, language: str
) -> None:
    header_row = sheet.add_table(
        [
            t("category_sheet.header_category", language),
            t("category_sheet.header_total", language),
            t("category_sheet.header_share", language),
            t("category_sheet.header_count", language),
        ],
        [
            [
                _category_display_name(r["name"], r.get("code"), bool(r.get("is_system")), language),
                _f(r["total"]),
                _f(r["share"]),
                r["transactions_count"],
            ]
            for r in rows
        ],
    )
    if rows:
        data_start = header_row + 1
        data_end = data_start + len(rows)
        sheet.format_requests.append(_currency_format_request(sheet.sheet_id, data_start, data_end, 1, currency))
        sheet.format_requests.append(_percent_format_request(sheet.sheet_id, data_start, data_end, 2))
        if include_charts:
            sheet.chart_requests.append(
                _pie_chart_request(
                    sheet.sheet_id,
                    chart_title,
                    _grid_range(sheet.sheet_id, data_start, data_end, 0, 1),
                    _grid_range(sheet.sheet_id, data_start, data_end, 1, 2),
                    header_row,
                )
            )
    else:
        sheet.add_row(t("category_sheet.no_transactions", language))


async def _build_portfolio_sheet(
    db: AsyncSession,
    sheet: _SheetBuilder,
    workspace_id: uuid.UUID,
    currency: str,
    options: ReportOptions,
    valuation,
) -> None:
    language = options.language
    positions = (
        await portfolio_analytics.list_position_valuations(db, workspace_id, None, options.date_to, currency)
    ).items
    header_row = sheet.add_table(
        [
            t("portfolio.header_asset", language),
            t("portfolio.header_quantity", language),
            t("portfolio.header_avg_cost", language),
            t("portfolio.header_market_value", language),
            t("portfolio.header_unrealized_pl", language),
            t("portfolio.header_realized_pl", language),
        ],
        [
            [p.asset_label, _f(p.quantity), _f(p.average_cost), _f(p.market_value), _f(p.unrealized_pl), _f(p.realized_pl)]
            for p in positions
        ],
    )
    if positions:
        data_start = header_row + 1
        data_end = data_start + len(positions)
        for col in (3, 4, 5):
            sheet.format_requests.append(_currency_format_request(sheet.sheet_id, data_start, data_end, col, currency))
    if not valuation.has_market_data and positions:
        sheet.add_row(t("portfolio.no_market_data_note", language))
    sheet.add_blank_row()

    allocation = await portfolio_analytics.compute_allocation(db, workspace_id, None, options.date_to, currency)
    if allocation.by_asset_type:
        alloc_header_row = sheet.add_table(
            [t("portfolio.alloc_header_type", language), t("portfolio.alloc_header_value", language), t("portfolio.alloc_header_share", language)],
            [[i.label, _f(i.value), _f(i.share)] for i in allocation.by_asset_type],
        )
        data_start = alloc_header_row + 1
        data_end = data_start + len(allocation.by_asset_type)
        sheet.format_requests.append(_currency_format_request(sheet.sheet_id, data_start, data_end, 1, currency))
        sheet.format_requests.append(_percent_format_request(sheet.sheet_id, data_start, data_end, 2))
        if options.include_charts:
            sheet.chart_requests.append(
                _pie_chart_request(
                    sheet.sheet_id,
                    t("portfolio.alloc_chart_title", language),
                    _grid_range(sheet.sheet_id, data_start, data_end, 0, 1),
                    _grid_range(sheet.sheet_id, data_start, data_end, 1, 2),
                    alloc_header_row,
                )
            )
    sheet.add_blank_row()

    performance = await portfolio_analytics.list_portfolio_snapshots(
        db, workspace_id, None, options.date_from, options.date_to
    )
    if performance:
        perf_header_row = sheet.add_table(
            [
                t("portfolio.perf_header_date", language),
                t("portfolio.perf_header_market_value", language),
                t("portfolio.perf_header_unrealized_pl", language),
                t("portfolio.perf_header_realized_pl", language),
            ],
            [[s.snapshot_date.isoformat(), _f(s.market_value), _f(s.unrealized_pl), _f(s.realized_pl)] for s in performance],
        )
        data_start = perf_header_row + 1
        data_end = data_start + len(performance)
        for col in (1, 2, 3):
            sheet.format_requests.append(_currency_format_request(sheet.sheet_id, data_start, data_end, col, currency))
        if options.include_charts:
            sheet.chart_requests.append(
                _line_chart_request(
                    sheet.sheet_id,
                    t("portfolio.perf_chart_title", language),
                    _grid_range(sheet.sheet_id, data_start, data_end, 0, 1),
                    _grid_range(sheet.sheet_id, perf_header_row, data_end, 1, 2),
                    perf_header_row,
                )
            )
    else:
        sheet.add_row(t("portfolio.no_snapshot", language))


# --- entrypoint ---------------------------------------------------------------


async def build_report(db: AsyncSession, workspace_id: uuid.UUID, options: ReportOptions) -> ReportContent:
    currency = await analytics.resolve_currency(db, workspace_id)

    summary = await analytics.summary(db, workspace_id, currency, options.date_from, options.date_to)
    monthly = await analytics.cash_flow(db, workspace_id, currency, "month", options.date_from, options.date_to)
    net_worth_rows = await portfolio_analytics.list_net_worth_snapshots(
        db, workspace_id, options.date_from, options.date_to
    )
    income_by_category = await analytics.by_category(
        db, workspace_id, currency, "income", options.date_from, options.date_to
    )
    expense_by_category = await analytics.by_category(
        db, workspace_id, currency, "expense", options.date_from, options.date_to
    )
    valuation = await portfolio_analytics.compute_valuation(db, workspace_id, None, options.date_to, currency)

    include_portfolio = options.include_portfolio
    if include_portfolio is None:
        include_portfolio = valuation.has_holdings

    sheet_id = 0
    sheets: list[_SheetBuilder] = []

    riepilogo = _SheetBuilder(sheet_id, "Riepilogo")
    sheet_id += 1
    _build_riepilogo(riepilogo, summary, monthly, net_worth_rows, valuation, currency, options.include_charts, options.language)
    sheets.append(riepilogo)

    transazioni = _SheetBuilder(sheet_id, "Transazioni")
    sheet_id += 1
    await _build_transazioni(db, transazioni, workspace_id, options)
    sheets.append(transazioni)

    entrate = _SheetBuilder(sheet_id, "Entrate per Categoria")
    sheet_id += 1
    _build_category_sheet(
        entrate, income_by_category, currency, options.include_charts,
        t("category_sheet.income_chart_title", options.language), options.language,
    )
    sheets.append(entrate)

    uscite = _SheetBuilder(sheet_id, "Uscite per Categoria")
    sheet_id += 1
    _build_category_sheet(
        uscite, expense_by_category, currency, options.include_charts,
        t("category_sheet.expense_chart_title", options.language), options.language,
    )
    sheets.append(uscite)

    if include_portfolio:
        portfolio = _SheetBuilder(sheet_id, "Portfolio")
        sheet_id += 1
        await _build_portfolio_sheet(db, portfolio, workspace_id, currency, options, valuation)
        sheets.append(portfolio)

    return ReportContent(
        sheet_titles=[s.title for s in sheets],
        value_ranges=[s.value_range() for s in sheets],
        requests=[r for s in sheets for r in (s.format_requests + s.chart_requests)],
    )
