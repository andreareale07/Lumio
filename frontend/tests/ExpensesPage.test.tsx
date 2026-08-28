import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ExpensesPage } from "../src/features/analytics/ExpensesPage";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

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
      <MemoryRouter initialEntries={["/expenses"]}>
        <ExpensesPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const PERIOD = { date_from: "2026-08-01", date_to: "2026-08-15" };

const SUMMARY = {
  currency: "EUR",
  period: PERIOD,
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
  period: PERIOD,
  points: [{ period: "2026-08-01", income: "2000.00", expenses: "500.00", net: "1500.00" }],
};

const BY_CATEGORY = {
  currency: "EUR",
  direction: "expense",
  period: PERIOD,
  items: [
    { category_id: "cat-alimentari", name: "Alimentari", total: "300.00", share: "0.6", transactions_count: 3 },
    { category_id: null, name: "Senza categoria", total: "200.00", share: "0.4", transactions_count: 1 },
  ],
};

const BY_MERCHANT_ALL = {
  currency: "EUR",
  direction: "expense",
  period: PERIOD,
  items: [{ merchant: "LIDL", total: "180.00", share: "0.36", transactions_count: 2 }],
};

const BY_MERCHANT_ALIMENTARI = {
  currency: "EUR",
  direction: "expense",
  period: PERIOD,
  items: [
    { merchant: "LIDL", total: "180.00", share: "0.6", transactions_count: 2 },
    { merchant: "ESSELUNGA", total: "120.00", share: "0.4", transactions_count: 1 },
  ],
};

const CATEGORY_TREND = {
  currency: "EUR",
  direction: "expense",
  granularity: "month",
  period: PERIOD,
  buckets: ["2026-08-01"],
  series: [
    { category_id: "cat-alimentari", name: "Alimentari", total: "300.00", values: ["300.00"] },
    { category_id: null, name: "Senza categoria", total: "200.00", values: ["200.00"] },
  ],
};

function baseMocks() {
  return mockFetchByUrl([
    { test: /\/analytics\/summary/, response: () => jsonResponse(SUMMARY) },
    { test: /\/analytics\/category-trend/, response: () => jsonResponse(CATEGORY_TREND) },
    { test: /\/analytics\/cash-flow/, response: () => jsonResponse(CASH_FLOW) },
    {
      test: /\/analytics\/by-merchant.*category_id=cat-alimentari/,
      response: () => jsonResponse(BY_MERCHANT_ALIMENTARI),
    },
    { test: /\/analytics\/by-merchant/, response: () => jsonResponse(BY_MERCHANT_ALL) },
    { test: /\/analytics\/by-category/, response: () => jsonResponse(BY_CATEGORY) },
    { test: /\/categories/, response: () => jsonResponse([]) },
  ]);
}

describe("ExpensesPage", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("mostra il totale spese e la variazione vs periodo precedente", async () => {
    baseMocks();
    renderPage();

    expect(await screen.findByRole("heading", { name: "Spese" })).toBeInTheDocument();
    expect(await screen.findByText(/vs periodo precedente/)).toBeInTheDocument();
  });

  it("mostra le categorie e la lista merchant complessiva", async () => {
    baseMocks();
    renderPage();

    expect((await screen.findAllByText("Alimentari")).length).toBeGreaterThan(0);
    expect((await screen.findAllByText("Senza categoria")).length).toBeGreaterThan(0);
    expect(await screen.findByText("Merchant")).toBeInTheDocument();
  });

  it("il drill-down per categoria mostra i merchant di quella categoria", async () => {
    baseMocks();
    const user = userEvent.setup();
    renderPage();

    const categoryButton = await screen.findByRole("button", { name: /Alimentari.*300,00/ });
    await user.click(categoryButton);

    expect(await screen.findByText("ESSELUNGA")).toBeInTheDocument();
  });

  it("la categoria senza id non è cliccabile (nessun drill-down)", async () => {
    baseMocks();
    renderPage();

    await screen.findAllByText("Senza categoria");
    expect(screen.queryByRole("button", { name: /Senza categoria/ })).not.toBeInTheDocument();
  });
});
