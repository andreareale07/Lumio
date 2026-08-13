import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AccountDetailPage } from "../src/features/accounts/AccountDetailPage";

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
}

const ACCOUNT = {
  id: "acc-1",
  workspace_id: "w1",
  bank_id: null,
  name: "Conto Test",
  account_type: "checking",
  currency: "EUR",
  account_identifier_masked: null,
  is_active: true,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

const BALANCES = {
  currency: "EUR",
  as_of: "2026-08-13",
  accounts: [{ financial_account_id: "acc-1", name: "Conto Test", account_type: "checking", balance: "1000.00" }],
  liquidity_total: "1000.00",
  debt_total: "0.00",
  investment_total: "0.00",
  has_investments: false,
};

function emptyAnalyticsPeriod(body: Record<string, unknown>) {
  return jsonResponse({
    currency: "EUR",
    period: { date_from: "2026-01-01", date_to: "2026-08-31" },
    ...body,
  });
}

function LocationDisplay() {
  const location = useLocation();
  return <div data-testid="location">{location.search}</div>;
}

function renderPage(initialEntry: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <Routes>
          <Route path="/accounts/:accountId" element={<AccountDetailPage />} />
        </Routes>
        <LocationDisplay />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("AccountDetailPage — tab Analytics", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("preserva tab=analytics nell'URL quando si naviga il periodo, e passa sempre financial_account_id alle query di trend", async () => {
    const requestedUrls: string[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      requestedUrls.push(url);
      if (url.includes("/analytics/balances")) return jsonResponse(BALANCES);
      if (url.includes("/analytics/balance-history")) return emptyAnalyticsPeriod({ granularity: "month", points: [] });
      if (url.includes("/analytics/cash-flow")) return emptyAnalyticsPeriod({ granularity: "month", points: [] });
      if (url.includes("/analytics/by-category")) return emptyAnalyticsPeriod({ items: [] });
      if (url.includes("/accounts")) return jsonResponse([ACCOUNT]);
      if (url.includes("/transactions")) return jsonResponse([]);
      return jsonResponse([]);
    });

    const user = userEvent.setup();
    renderPage("/accounts/acc-1?tab=analytics");

    await screen.findByText("Saldo nel tempo");

    await user.click(screen.getByRole("button", { name: "Periodo precedente" }));

    // tab=analytics deve sopravvivere alla navigazione del periodo — il
    // navigator vive DENTRO il tab e condivide gli stessi search params
    // (bug segnalato nel piano: setSearchParams non deve resettare `tab`).
    const search = await screen.findByTestId("location");
    expect(search.textContent).toContain("tab=analytics");
    expect(search.textContent).toContain("granularity=month");

    const trendUrls = requestedUrls.filter(
      (u) => u.includes("/analytics/balance-history") || u.includes("/analytics/cash-flow"),
    );
    expect(trendUrls.length).toBeGreaterThan(0);
    expect(trendUrls.every((u) => u.includes("financial_account_id=acc-1"))).toBe(true);
  });
});
