import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AuthProvider } from "../src/app/providers/AuthProvider";
import { InvestmentsOverviewPage } from "../src/features/portfolio/InvestmentsOverviewPage";
import { formatMoney } from "../src/lib/format";

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
}

// `formatMoney` (Intl.NumberFormat it-IT) separa cifra e simbolo con uno
// spazio unificatore (NBSP), non uno spazio normale — invisibile a occhio,
// ma la normalizzazione whitespace di default di @testing-library/dom lo
// collassa a spazio normale SOLO sul testo letto dal DOM, mai sulla
// stringa del matcher passata da qui: un confronto diretto contro
// l'output grezzo di `formatMoney` fallisce sempre per questo, quindi si
// normalizza allo stesso modo prima di cercarlo.
const NBSP = String.fromCharCode(160);
function money(amount: string | number, currency: string): string {
  return formatMoney(amount, currency).split(NBSP).join(" ");
}

// AssetFormDialog (renderizzato, anche se chiuso, dentro InvestmentsOverviewPage)
// legge `user?.base_currency` da AuthProvider — nessuna sessione da
// ripristinare in questi test, quindi /auth/refresh risponde 401 e
// AuthProvider si assesta su user: null (letto con optional chaining, mai
// un crash).
function mockUnauthenticated(url: string): Response | null {
  if (url.includes("/auth/refresh")) return new Response(null, { status: 401 });
  return null;
}

const VALUATION_ALL = {
  currency: "EUR",
  as_of: "2026-08-18",
  market_value: "24310.00",
  cost_basis: "22100.00",
  unrealized_pl: "2210.00",
  realized_pl: "180.00",
  has_market_data: true,
  has_holdings: true,
  has_missing_fx_rate: false,
};

const VALUATION_UNASSIGNED = {
  ...VALUATION_ALL,
  market_value: "3000.00",
  cost_basis: "2800.00",
  unrealized_pl: "200.00",
  has_holdings: true,
};

const ALLOCATION_EMPTY = {
  currency: "EUR",
  as_of: "2026-08-18",
  has_market_data: true,
  has_missing_fx_rate: false,
  by_asset_type: [{ key: "etf", label: "ETF", value: "24310.00", share: "1" }],
  by_asset: [],
  by_account: [],
  by_currency: [],
  by_strategy: [],
};

const SUMMARIES = {
  as_of: "2026-08-18",
  items: [
    {
      portfolio_id: "pf-1",
      name: "Lungo termine",
      account_count: 2,
      currency: "EUR",
      market_value: "20000.00",
      cost_basis: "18000.00",
      unrealized_pl: "2000.00",
      has_market_data: true,
      has_holdings: true,
    },
  ],
};

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <AuthProvider>
        <MemoryRouter initialEntries={["/investments"]}>
          <Routes>
            <Route path="/investments" element={<InvestmentsOverviewPage />} />
          </Routes>
        </MemoryRouter>
      </AuthProvider>
    </QueryClientProvider>,
  );
}

describe("InvestmentsOverviewPage", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("mostra i KPI aggregati, l'elenco dei portfolio e la riga Asset senza portfolio", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      if (mockUnauthenticated(url)) return mockUnauthenticated(url)!;
      if (url.includes("/portfolios/analytics/summary")) return jsonResponse(SUMMARIES);
      if (url.includes("/portfolios/analytics/valuation") && url.includes("unassigned=true")) {
        return jsonResponse(VALUATION_UNASSIGNED);
      }
      if (url.includes("/portfolios/analytics/valuation")) return jsonResponse(VALUATION_ALL);
      if (url.includes("/portfolios/analytics/allocation")) return jsonResponse(ALLOCATION_EMPTY);
      if (url.includes("/portfolios/analytics/performance")) return jsonResponse({ currency: "EUR", points: [] });
      return jsonResponse([]);
    });

    renderPage();

    // KPI del blocco condiviso (tutti i conti) — il valore aggregato
    // compare anche nella legenda "Per tipo di asset" (un solo asset type,
    // stesso importo del totale): si scopre la ricerca alla card KPI
    // stessa per evitare un match multiplo.
    const valueCard = (await screen.findByText("Valore attuale")).closest("div")!;
    expect(within(valueCard).getByText(money(VALUATION_ALL.market_value, "EUR"))).toBeInTheDocument();
    const investedCard = screen.getByText("Investito").closest("div")!;
    expect(within(investedCard).getByText(money(VALUATION_ALL.cost_basis, "EUR"))).toBeInTheDocument();

    // Riga del portfolio nominato
    const portfolioRow = (await screen.findByText("Lungo termine")).closest("a")!;
    expect(within(portfolioRow).getByText(money(SUMMARIES.items[0].market_value, "EUR"))).toBeInTheDocument();
    expect(portfolioRow).toHaveAttribute("href", "/investments/portfolios/pf-1");

    // Riga pseudo-scope "Asset senza portfolio", sempre presente
    const unassignedRow = (await screen.findByText("Asset senza portfolio")).closest("a")!;
    expect(within(unassignedRow).getByText(money(VALUATION_UNASSIGNED.market_value, "EUR"))).toBeInTheDocument();
    expect(unassignedRow).toHaveAttribute("href", "/investments/portfolios/unassigned");
  });

  it("mostra l'empty state quando non ci sono posizioni ne' portfolio", async () => {
    const emptyValuation = {
      ...VALUATION_ALL,
      cost_basis: "0.00",
      market_value: "0.00",
      unrealized_pl: "0.00",
      realized_pl: "0.00",
      has_holdings: false,
    };
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      if (mockUnauthenticated(url)) return mockUnauthenticated(url)!;
      if (url.includes("/portfolios/analytics/summary")) return jsonResponse({ as_of: "2026-08-18", items: [] });
      if (url.includes("/portfolios/analytics/valuation")) return jsonResponse(emptyValuation);
      if (url.includes("/portfolios/analytics/allocation")) return jsonResponse({ ...ALLOCATION_EMPTY, by_asset_type: [] });
      if (url.includes("/portfolios/analytics/performance")) return jsonResponse({ currency: "EUR", points: [] });
      return jsonResponse([]);
    });

    renderPage();

    await screen.findByText("Nessuna posizione qui");
    expect(screen.getByText(/Nessun portfolio ancora/)).toBeInTheDocument();
  });
});
