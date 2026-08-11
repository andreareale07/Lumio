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
 * con `mockResolvedValueOnce` in sequenza (diverso dal pattern usato in
 * `AISettingsPage.test.tsx`, dove le richieste sono seriali). */
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

const RECENT_TRANSACTION = {
  id: "t1",
  workspace_id: "w1",
  financial_account_id: "a1",
  import_id: null,
  category_id: null,
  transaction_date: "2026-08-10",
  value_date: null,
  description_raw: "SUPERMERCATO LIDL",
  description_normalized: null,
  merchant: "LIDL",
  reference: null,
  amount: "-42.50",
  currency: "EUR",
  direction: "debit",
  transaction_type: "expense",
  balance_after: null,
  status: "confirmed",
  created_at: "2026-08-10T00:00:00Z",
  updated_at: "2026-08-10T00:00:00Z",
};

describe("DashboardPage", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("mostra i KPI e le sezioni con dati reali", async () => {
    const byCategory = {
      currency: "EUR",
      direction: "expense",
      period: { date_from: "2026-08-01", date_to: "2026-08-15" },
      items: [{ category_id: "c1", name: "Alimentari", total: "150.00", share: "1", transactions_count: 2 }],
    };
    mockFetchByUrl([
      { test: /\/analytics\/summary/, response: () => jsonResponse(SUMMARY) },
      { test: /\/analytics\/cash-flow/, response: () => jsonResponse(CASH_FLOW) },
      { test: /\/analytics\/by-category/, response: () => jsonResponse(byCategory) },
      { test: /\/transactions/, response: () => jsonResponse([RECENT_TRANSACTION]) },
    ]);

    renderPage();

    expect(await screen.findByText("Liquidità")).toBeInTheDocument();
    // "Alimentari" compare sia nella tabella accessibile del ChartCard
    // (sr-only) sia nella lista visibile sotto — entrambe legittime.
    expect((await screen.findAllByText("Alimentari")).length).toBeGreaterThan(0);
    expect(await screen.findByText("LIDL")).toBeInTheDocument();
    expect(screen.getByText("Il valore delle posizioni arriva con Portfolio")).toBeInTheDocument();
  });

  it("mostra l'empty state per le spese quando il periodo non ne ha", async () => {
    const emptyCategory = {
      currency: "EUR",
      direction: "expense",
      period: { date_from: "2026-08-01", date_to: "2026-08-15" },
      items: [],
    };
    mockFetchByUrl([
      { test: /\/analytics\/summary/, response: () => jsonResponse(SUMMARY) },
      { test: /\/analytics\/cash-flow/, response: () => jsonResponse(CASH_FLOW) },
      { test: /\/analytics\/by-category/, response: () => jsonResponse(emptyCategory) },
      { test: /\/transactions/, response: () => jsonResponse([]) },
    ]);

    renderPage();

    expect(await screen.findByText("Nessuna spesa in questo periodo")).toBeInTheDocument();
    expect(await screen.findByText("Nessun movimento")).toBeInTheDocument();
  });

  it("mostra un errore con azione di recupero se la panoramica non carica", async () => {
    mockFetchByUrl([
      { test: /\/analytics\/summary/, response: () => jsonResponse({ detail: "boom" }, 500) },
      { test: /\/analytics\/cash-flow/, response: () => jsonResponse(CASH_FLOW) },
      {
        test: /\/analytics\/by-category/,
        response: () =>
          jsonResponse({
            currency: "EUR",
            direction: "expense",
            period: { date_from: "2026-08-01", date_to: "2026-08-15" },
            items: [],
          }),
      },
      { test: /\/transactions/, response: () => jsonResponse([]) },
    ]);

    renderPage();

    expect(await screen.findByText("Non siamo riusciti a caricare la panoramica.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Riprova" })).toBeInTheDocument();
  });
});
