import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { DashboardPage } from "../src/features/dashboard/DashboardPage";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

/** Le query della dashboard partono in parallelo: l'ordine delle chiamate
 * `fetch` non e' garantito, quindi si risponde in base all'URL invece che
 * con `mockResolvedValueOnce` in sequenza. L'ordine delle regole conta:
 * pattern piu' specifici PRIMA di quelli generici che li conterrebbero
 * come sottostringa (es. `/transactions/review-summary` prima di
 * `/transactions`). */
function mockFetchByUrl(rules: { test: RegExp; response: () => Response }[]) {
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const url = typeof input === "string" ? input : input.toString();
    const rule = rules.find((r) => r.test.test(url));
    if (!rule) throw new Error(`Nessun mock per ${url}`);
    return rule.response();
  });
}

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/"]}>
        <DashboardPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const NET_WORTH_HISTORY = {
  currency: "EUR",
  points: [
    { snapshot_date: "2026-07-16", liquidity: "900.00", debt: "0", investments: "0", net_worth: "900.00" },
    { snapshot_date: "2026-08-15", liquidity: "1000.00", debt: "0", investments: "0", net_worth: "1000.00" },
  ],
};

const REVIEW_SUMMARY_CLEAN = { total: 10, classified: 10, needs_review: 0 };

const SUMMARY = {
  currency: "EUR",
  period: { date_from: "2026-08-01", date_to: "2026-08-15" },
  comparison_period: { date_from: "2026-07-01", date_to: "2026-07-31" },
  liquidity: "1000.00",
  debt: "0",
  investments: "0",
  has_investments: false,
  income: "2000.00",
  expenses: "500.00",
  net_cash_flow: "1500.00",
  previous_income: "1800.00",
  previous_expenses: "600.00",
  previous_net_cash_flow: "1200.00",
};

const CASH_FLOW = {
  currency: "EUR",
  granularity: "month",
  period: { date_from: "2026-08-01", date_to: "2026-08-15" },
  points: [{ period: "2026-08-01", income: "2000.00", expenses: "500.00", net: "1500.00" }],
};

const VALUATION_WITH_HOLDINGS = {
  currency: "EUR",
  as_of: "2026-08-15",
  market_value: "500.00",
  cost_basis: "450.00",
  unrealized_pl: "50.00",
  realized_pl: "0.00",
  has_market_data: true,
  has_holdings: true,
};

const VALUATION_EMPTY = {
  currency: "EUR",
  as_of: "2026-08-15",
  market_value: "0.00",
  cost_basis: "0.00",
  unrealized_pl: "0.00",
  realized_pl: "0.00",
  has_market_data: true,
  has_holdings: false,
};

const ALLOCATION_WITH_ITEMS = {
  currency: "EUR",
  as_of: "2026-08-15",
  has_market_data: true,
  by_asset_type: [{ key: "etf", label: "etf", value: "500.00", share: "1.0000" }],
  by_asset: [],
  by_account: [],
};

const ALLOCATION_EMPTY = {
  currency: "EUR",
  as_of: "2026-08-15",
  has_market_data: true,
  by_asset_type: [],
  by_asset: [],
  by_account: [],
};

/** Regole "pulite" condivise da ogni test: coprono gli endpoint del blocco
 * Patrimonio + il contatore "da rivedere" in testata, sempre chiamati
 * indipendentemente dallo scenario testato (PHASE 5) — di default nessun
 * segnale, cosi' l'icona non compare a meno che un test lo sovrascriva
 * esplicitamente. Redesign FETTA 1: la Dashboard non chiama piu'
 * `/analytics/by-category` ne' `/transactions` (blocchi "Spese per
 * categoria"/"Ultimi movimenti" rimossi, ora su Spese/Entrate), quindi
 * questi mock non compaiono piu' in nessun test qui sotto. */
function baseRules() {
  return [
    { test: /\/analytics\/net-worth-history/, response: () => jsonResponse(NET_WORTH_HISTORY) },
    { test: /\/transactions\/review-summary/, response: () => jsonResponse(REVIEW_SUMMARY_CLEAN) },
  ];
}

describe("DashboardPage", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("mostra i blocchi Patrimonio e Flusso con dati reali, senza i blocchi di dettaglio rimossi dal redesign", async () => {
    mockFetchByUrl([
      ...baseRules(),
      { test: /\/analytics\/summary/, response: () => jsonResponse(SUMMARY) },
      { test: /\/analytics\/cash-flow/, response: () => jsonResponse(CASH_FLOW) },
      { test: /\/portfolios\/analytics\/valuation/, response: () => jsonResponse(VALUATION_WITH_HOLDINGS) },
      { test: /\/portfolios\/analytics\/allocation/, response: () => jsonResponse(ALLOCATION_WITH_ITEMS) },
    ]);

    renderPage();

    // Patrimonio: sempre visibile, indipendente dal periodo selezionato.
    // `findBy*` (non `getBy*`): il titolo statico "Patrimonio" compare gia'
    // al primo render, prima che i dati async delle KPI siano arrivati —
    // un `getByText` sincrono subito dopo correrebbe contro quel caricamento.
    expect(await screen.findByText("Patrimonio")).toBeInTheDocument();
    expect(await screen.findByText("Patrimonio totale")).toBeInTheDocument();
    expect(await screen.findByText("Liquidità")).toBeInTheDocument();

    // Icona "da rivedere" in testata: nessun segnale in questo scenario,
    // non compare (sostituisce il vecchio blocco "Da fare" a sezione intera).
    expect(screen.queryByText(/da rivedere/)).not.toBeInTheDocument();

    // Flusso: la tabella accessibile del grafico Entrate/Uscite e' presente.
    expect(await screen.findByRole("table", { name: "Entrate e uscite per mese" })).toBeInTheDocument();

    // Widget Portfolio (M09b): valore reale invece del vecchio placeholder.
    expect(await screen.findByText("etf")).toBeInTheDocument();
    expect(screen.getByText("Vai a Investimenti")).toBeInTheDocument();

    // Guardia di regressione (redesign FETTA 1): i blocchi "Spese per
    // categoria" e "Ultimi movimenti" sono stati rimossi dalla Dashboard —
    // ora vivono su Spese/Entrate, mai piu' qui.
    expect(screen.queryByText("Spese per categoria")).not.toBeInTheDocument();
    expect(screen.queryByText("Ultimi movimenti")).not.toBeInTheDocument();
  });

  it("mostra un'azione 'Ricalcola adesso' quando non esiste ancora nessuno snapshot di patrimonio", async () => {
    // Bug reale trovato verificando su Docker: un workspace appena creato
    // non ha ancora `net_worth_snapshots` (scritti dal cron giornaliero) —
    // il blocco Patrimonio deve mostrare un empty state con azione, mai
    // restare silenziosamente vuoto.
    mockFetchByUrl([
      { test: /\/analytics\/net-worth-history/, response: () => jsonResponse({ currency: "EUR", points: [] }) },
      { test: /\/transactions\/review-summary/, response: () => jsonResponse(REVIEW_SUMMARY_CLEAN) },
      { test: /\/analytics\/summary/, response: () => jsonResponse(SUMMARY) },
      { test: /\/analytics\/cash-flow/, response: () => jsonResponse(CASH_FLOW) },
      { test: /\/portfolios\/analytics\/valuation/, response: () => jsonResponse(VALUATION_EMPTY) },
      { test: /\/portfolios\/analytics\/allocation/, response: () => jsonResponse(ALLOCATION_EMPTY) },
    ]);

    renderPage();

    expect(await screen.findByText("Nessun dato ancora")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Ricalcola adesso" })).toBeInTheDocument();
    // Nessuna KPI di Patrimonio renderizzata quando non c'e' nessun punto.
    expect(screen.queryByText("Patrimonio totale")).not.toBeInTheDocument();
  });

  it("mostra un'icona con contatore in testata quando ci sono transazioni da rivedere", async () => {
    const reviewSummary = { total: 10, classified: 7, needs_review: 3 };
    mockFetchByUrl([
      { test: /\/analytics\/net-worth-history/, response: () => jsonResponse(NET_WORTH_HISTORY) },
      { test: /\/transactions\/review-summary/, response: () => jsonResponse(reviewSummary) },
      { test: /\/analytics\/summary/, response: () => jsonResponse(SUMMARY) },
      { test: /\/analytics\/cash-flow/, response: () => jsonResponse(CASH_FLOW) },
      { test: /\/portfolios\/analytics\/valuation/, response: () => jsonResponse(VALUATION_EMPTY) },
      { test: /\/portfolios\/analytics\/allocation/, response: () => jsonResponse(ALLOCATION_EMPTY) },
    ]);

    renderPage();

    const link = await screen.findByRole("link", { name: "3 transazioni da rivedere" });
    expect(link).toHaveAttribute("href", "/transactions?review=1");
  });

  it("mostra l'empty state degli investimenti quando il workspace non ne ha ancora", async () => {
    mockFetchByUrl([
      ...baseRules(),
      { test: /\/analytics\/summary/, response: () => jsonResponse(SUMMARY) },
      { test: /\/analytics\/cash-flow/, response: () => jsonResponse(CASH_FLOW) },
      { test: /\/portfolios\/analytics\/valuation/, response: () => jsonResponse(VALUATION_EMPTY) },
      { test: /\/portfolios\/analytics\/allocation/, response: () => jsonResponse(ALLOCATION_EMPTY) },
    ]);

    renderPage();

    expect(await screen.findByText("Non hai ancora aggiunto investimenti")).toBeInTheDocument();
  });

  it("mostra un errore con azione di recupero se il flusso del periodo non carica", async () => {
    mockFetchByUrl([
      ...baseRules(),
      { test: /\/analytics\/summary/, response: () => jsonResponse({ detail: "boom" }, 500) },
      { test: /\/analytics\/cash-flow/, response: () => jsonResponse(CASH_FLOW) },
      { test: /\/portfolios\/analytics\/valuation/, response: () => jsonResponse(VALUATION_EMPTY) },
      { test: /\/portfolios\/analytics\/allocation/, response: () => jsonResponse(ALLOCATION_EMPTY) },
    ]);

    renderPage();

    // Il blocco Patrimonio carica correttamente (net-worth-history separata
    // da /analytics/summary): un solo ErrorState, quello del Flusso.
    expect(await screen.findByText("Patrimonio totale")).toBeInTheDocument();
    expect(await screen.findByText("Non siamo riusciti a caricare la panoramica.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Riprova" })).toBeInTheDocument();
  });
});
