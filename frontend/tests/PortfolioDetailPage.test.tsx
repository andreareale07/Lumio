import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AuthProvider } from "../src/app/providers/AuthProvider";
import { PortfolioDetailPage } from "../src/features/portfolio/PortfolioDetailPage";
import { formatMoney } from "../src/lib/format";

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
}

// Stesso principio di InvestmentsOverviewPage.test.tsx: `formatMoney`
// separa cifra e simbolo con NBSP, collassato a spazio normale dalla
// normalizzazione di @testing-library/dom SOLO sul testo letto dal DOM,
// mai sulla stringa del matcher — si normalizza qui allo stesso modo.
const NBSP = String.fromCharCode(160);
function money(amount: string | number, currency: string): string {
  return formatMoney(amount, currency).split(NBSP).join(" ");
}

function mockUnauthenticated(url: string): Response | null {
  if (url.includes("/auth/refresh")) return new Response(null, { status: 401 });
  return null;
}

const VALUATION = {
  currency: "EUR",
  as_of: "2026-08-18",
  market_value: "20000.00",
  cost_basis: "18000.00",
  unrealized_pl: "2000.00",
  realized_pl: "0.00",
  has_market_data: true,
  has_holdings: true,
  has_missing_fx_rate: false,
};

const ALLOCATION = {
  currency: "EUR",
  as_of: "2026-08-18",
  has_market_data: true,
  has_missing_fx_rate: false,
  by_asset_type: [{ key: "etf", label: "ETF", value: "20000.00", share: "1" }],
  by_asset: [],
  by_account: [],
  by_currency: [],
  by_strategy: [],
};

const PORTFOLIO = {
  id: "pf-1",
  workspace_id: "ws-1",
  name: "Lungo termine",
  description: "Il nucleo del portafoglio",
  currency: "EUR",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

const POSITIONS = {
  currency: "EUR",
  as_of: "2026-08-18",
  has_market_data: true,
  has_missing_fx_rate: false,
  positions: [
    {
      position_id: "pos-1",
      asset_id: "asset-1",
      asset_label: "Vanguard FTSE All-World",
      financial_account_id: "acc-1",
      account_label: "Trade Republic",
      quantity: "10",
      average_cost: "1800.00",
      currency: "EUR",
      currency_native: "EUR",
      cost_basis: "18000.00",
      market_value: "20000.00",
      unrealized_pl: "2000.00",
      realized_pl: "0.00",
      has_market_data: true,
    },
  ],
};

const TRANSACTIONS = [
  {
    id: "txn-1",
    workspace_id: "ws-1",
    financial_account_id: "acc-1",
    asset_id: "asset-1",
    transaction_id: null,
    trade_date: "2026-01-15",
    type: "buy",
    quantity: "10",
    price: "1800.00",
    amount: "-18000.00",
    fees: "0",
    tax: "0",
    currency: "EUR",
    source_type_raw: null,
    notes: null,
  },
];

function mockScopedApi(url: string, { positions = POSITIONS, transactions = TRANSACTIONS } = {}): Response {
  const authResponse = mockUnauthenticated(url);
  if (authResponse) return authResponse;
  if (url.includes("/portfolios/analytics/valuation")) return jsonResponse(VALUATION);
  if (url.includes("/portfolios/analytics/allocation")) return jsonResponse(ALLOCATION);
  if (url.includes("/portfolios/analytics/performance")) return jsonResponse({ currency: "EUR", points: [] });
  if (url.includes("/portfolios/analytics/positions")) return jsonResponse(positions);
  if (url.includes("/investment-transactions")) return jsonResponse(transactions);
  if (url.match(/\/portfolios\/[^/]+$/)) return jsonResponse(PORTFOLIO);
  return jsonResponse([]);
}

function renderPage(portfolioId: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <AuthProvider>
        <MemoryRouter initialEntries={[`/investments/portfolios/${portfolioId}`]}>
          <Routes>
            <Route path="/investments/portfolios/:portfolioId" element={<PortfolioDetailPage />} />
          </Routes>
        </MemoryRouter>
      </AuthProvider>
    </QueryClientProvider>,
  );
}

describe("PortfolioDetailPage", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("mostra il blocco condiviso, gli asset e i movimenti di un portfolio reale", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => mockScopedApi(String(input)));

    renderPage("pf-1");

    expect(await screen.findByText("Lungo termine")).toBeInTheDocument();
    expect(screen.getByText("Il nucleo del portafoglio")).toBeInTheDocument();

    // Blocco condiviso, stesso template della Panoramica — "Andamento del
    // valore" e' univoco (a differenza di "Valore attuale"/"Rendimento",
    // che compaiono anche come intestazioni di colonna nella tabella Asset
    // sotto), quindi non rischia un match multiplo.
    await screen.findByText("Andamento del valore");

    // Elenco Asset di questo ambito — la riga compare due volte nel DOM
    // (tabella desktop + card mobile, una delle due nascosta solo via CSS),
    // quindi si usa la variante *AllBy* invece di aspettarsi un match unico.
    const assetLinks = await screen.findAllByText("Vanguard FTSE All-World");
    expect(assetLinks[0].closest("a")).toHaveAttribute("href", "/investments/assets/asset-1");
    expect(screen.getAllByText("Trade Republic").length).toBeGreaterThan(0);

    // Movimenti di questo ambito — anche qui la riga compare due volte
    // (tabella desktop + card mobile).
    expect((await screen.findAllByText("Acquisto")).length).toBeGreaterThan(0);
    expect(screen.getAllByText(`-${money("18000.00", "EUR")}`).length).toBeGreaterThan(0);
  });

  it("mostra lo pseudo-scope 'Asset senza portfolio' senza interrogare /portfolios/unassigned", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => mockScopedApi(String(input)));

    renderPage("unassigned");

    expect(await screen.findByText("Asset senza portfolio")).toBeInTheDocument();
    expect(screen.getByText("Conti non raggruppati in nessun portfolio.")).toBeInTheDocument();
    await screen.findByText("Valore attuale");
    expect((await screen.findAllByText("Vanguard FTSE All-World")).length).toBeGreaterThan(0);
  });

  it("mostra un empty state quando il portfolio non ha posizioni ne' movimenti", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) =>
      mockScopedApi(String(input), { positions: { ...POSITIONS, positions: [] }, transactions: [] }),
    );

    renderPage("pf-1");

    expect(await screen.findByText("Nessuna posizione aperta in questo ambito.")).toBeInTheDocument();
    expect(await screen.findByText("Nessun movimento")).toBeInTheDocument();
  });

  it("mostra un errore quando il portfolio non esiste", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      const authResponse = mockUnauthenticated(url);
      if (authResponse) return authResponse;
      if (url.match(/\/portfolios\/[^/]+$/)) return new Response(null, { status: 404 });
      return jsonResponse([]);
    });

    renderPage("does-not-exist");

    expect(await screen.findByText("Portfolio non trovato")).toBeInTheDocument();
  });
});
