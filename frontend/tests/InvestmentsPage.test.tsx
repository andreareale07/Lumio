import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { InvestmentsPage } from "../src/features/portfolio/InvestmentsPage";

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/investments"]}>
        <InvestmentsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

const DEFAULT_VALUATION = {
  currency: "EUR",
  as_of: "2026-08-11",
  market_value: "0.00",
  cost_basis: "0.00",
  unrealized_pl: "0.00",
  realized_pl: "0.00",
  has_market_data: true,
  has_holdings: false,
};

const DEFAULT_ALLOCATION = {
  currency: "EUR",
  as_of: "2026-08-11",
  has_market_data: true,
  by_asset_type: [],
  by_asset: [],
  by_account: [],
};

// Le 3 rotte "/portfolios/analytics/..." condividono il prefisso con la
// generica "/portfolios" (lista per il selettore) — un semplice
// `url.includes(path)` sceglierebbe quest'ultima per substring match
// indipendentemente dall'ordine, quindi vanno risolte SEPARATAMENTE e
// PRIMA di qualunque rotta generica fornita dal singolo test (con default
// innocuo, dato che Overview — la tab iniziale — le richiede sempre al
// mount, anche nei test che non se ne occupano).
const ANALYTICS_DEFAULTS: Record<string, unknown> = {
  "/portfolios/analytics/valuation": DEFAULT_VALUATION,
  "/portfolios/analytics/allocation": DEFAULT_ALLOCATION,
  "/portfolios/analytics/performance": { currency: "EUR", points: [] },
};

function mockApiRoutes(routes: Record<string, unknown>) {
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const url = String(input);
    for (const analyticsPath of Object.keys(ANALYTICS_DEFAULTS)) {
      if (url.includes(analyticsPath)) {
        return jsonResponse(analyticsPath in routes ? routes[analyticsPath] : ANALYTICS_DEFAULTS[analyticsPath]);
      }
    }
    for (const [path, body] of Object.entries(routes)) {
      if (url.includes(path)) return jsonResponse(body);
    }
    return jsonResponse([]);
  });
}

const ASSET_VWCE = {
  id: "asset-1",
  workspace_id: "w1",
  symbol: "VWCE",
  isin: null,
  name: "Vanguard FTSE All-World",
  asset_type: "etf",
  currency: "EUR",
  notes: null,
  created_at: "2026-08-01T00:00:00Z",
  updated_at: "2026-08-01T00:00:00Z",
};

const ACCOUNT_TR = {
  id: "account-1",
  workspace_id: "w1",
  bank_id: null,
  name: "Trade Republic",
  account_type: "brokerage",
  currency: "EUR",
  account_identifier_masked: null,
  is_active: true,
  created_at: "2026-08-01T00:00:00Z",
  updated_at: "2026-08-01T00:00:00Z",
};

const POSITION_VWCE = {
  id: "pos-1",
  workspace_id: "w1",
  financial_account_id: "account-1",
  asset_id: "asset-1",
  quantity: "10.0000000000",
  average_cost: "100.000000",
  realized_pl: "0.00",
  currency: "EUR",
  created_at: "2026-08-01T00:00:00Z",
  updated_at: "2026-08-01T00:00:00Z",
};

describe("InvestmentsPage", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("mostra l'empty state quando non ci sono investimenti", async () => {
    mockApiRoutes({ "/portfolios": [], "/positions": [], "/investment-transactions": [] });
    renderPage();

    expect(await screen.findByText("Non hai ancora aggiunto investimenti")).toBeInTheDocument();
  });

  it("mostra il valore reale nel tab Overview", async () => {
    mockApiRoutes({
      "/portfolios": [],
      "/positions": [POSITION_VWCE],
      "/investment-transactions": [],
      "/portfolios/analytics/valuation": {
        currency: "EUR",
        as_of: "2026-08-11",
        market_value: "1000.00",
        cost_basis: "1000.00",
        unrealized_pl: "0.00",
        realized_pl: "0.00",
        has_market_data: false, // nessun MarketDataProvider attivo: a costo
        has_holdings: true,
      },
    });
    renderPage();

    expect(await screen.findByText("Valore a costo")).toBeInTheDocument();
    // 1000,00 € — la resa esatta di Intl.NumberFormat (separatore delle
    // migliaia, spazio non interrotto) dipende dai dati ICU dell'ambiente,
    // quindi qui non si asserisce la stringa letterale (stessa scelta delle
    // altre pagine di questo progetto).
    expect(await screen.findByText((text) => /1\.?000,00/.test(text))).toBeInTheDocument();
    expect(screen.getByText("Registra un nuovo movimento")).toBeInTheDocument();
  });

  it("elenca le posizioni nel tab Posizioni con asset e conto", async () => {
    mockApiRoutes({
      "/portfolios": [],
      "/positions": [POSITION_VWCE],
      "/investment-transactions": [],
      "/accounts": [ACCOUNT_TR],
      "/assets": [ASSET_VWCE],
    });
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole("tab", { name: "Posizioni" }));

    // La riga esiste sia nella tabella desktop sia nella card-list mobile
    // (entrambe montate in jsdom, e' Tailwind a nasconderne una a runtime
    // nel browser reale) — si scopre l'assert sulla sola tabella.
    const table = await screen.findByRole("table");
    expect(within(table).getByText("VWCE")).toBeInTheDocument();
    expect(within(table).getByText("Trade Republic")).toBeInTheDocument();
  });

  it("mostra l'empty state dei movimenti e apre il form di un nuovo movimento", async () => {
    mockApiRoutes({
      "/portfolios": [],
      "/positions": [],
      "/investment-transactions": [],
      "/accounts": [ACCOUNT_TR],
      "/assets": [ASSET_VWCE],
    });
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole("tab", { name: "Movimenti" }));
    expect(await screen.findByText("Nessun movimento")).toBeInTheDocument();

    await user.click(screen.getAllByRole("button", { name: /Nuovo movimento/ })[0]);
    expect(await screen.findByLabelText("Conto")).toBeInTheDocument();
    expect(screen.getByLabelText("Data")).toBeInTheDocument();
  });

  it("richiede un asset per un movimento di tipo acquisto", async () => {
    mockApiRoutes({
      "/portfolios": [],
      "/positions": [],
      "/investment-transactions": [],
      "/accounts": [ACCOUNT_TR],
      "/assets": [ASSET_VWCE],
    });
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole("tab", { name: "Movimenti" }));
    await user.click(screen.getAllByRole("button", { name: /Nuovo movimento/ })[0]);

    await user.selectOptions(await screen.findByLabelText("Conto"), "account-1");
    await user.type(screen.getByLabelText("Importo netto in cassa"), "-1000");
    await user.click(screen.getByRole("button", { name: "Registra movimento" }));

    expect(await screen.findByText("Seleziona un asset per questo tipo di movimento")).toBeInTheDocument();
  });

  it("mostra l'empty state dei portfolio nel tab Conti", async () => {
    mockApiRoutes({ "/portfolios": [], "/positions": [], "/investment-transactions": [] });
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole("tab", { name: "Conti" }));
    expect(await screen.findByText("Nessun portfolio")).toBeInTheDocument();
  });
});
