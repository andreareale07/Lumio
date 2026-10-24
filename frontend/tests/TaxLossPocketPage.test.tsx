import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { TaxLossPocketPage } from "../src/features/tax/TaxLossPocketPage";

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
}

const ACCOUNT = { id: "acc-1", name: "Broker test" };

function pocketRow(index: number) {
  return {
    formation_date: `2025-01-${String((index % 28) + 1).padStart(2, "0")}`,
    nominal: "100.00",
    income_category: "diversi",
    perimeter: "dichiarativo",
    source: "computed",
    formed_under_ruleset_code: "IT",
    applied_ruleset_code: "IT",
    coefficient: "1",
    usable_amount: "100.00",
    conversion_reference: null,
    expires_on: "2029-12-31",
    is_expired: false,
    asset_id: null,
    remaining_amount: "100.00",
  };
}

function mockApi(rowCount: number) {
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const url = typeof input === "string" ? input : input.toString();
    if (/\/tax\/accounts\/.+\/regimes/.test(url)) return jsonResponse([{ id: "r1" }]);
    if (/\/tax\/loss-pocket\/openings/.test(url)) return jsonResponse([]);
    if (/\/tax\/loss-pocket/.test(url)) {
      return jsonResponse({
        rows: Array.from({ length: rowCount }, (_, i) => pocketRow(i)),
        totals_by_perimeter: { dichiarativo: "0" },
        remaining_by_perimeter: { dichiarativo: String(rowCount * 100) },
        residence_declared: true,
        excluded_events: [],
      });
    }
    if (/\/tax\/taxable-gains/.test(url)) {
      return jsonResponse({ rows: [], tax_due_by_perimeter: {}, remaining_pocket_by_perimeter: {} });
    }
    if (/\/accounts/.test(url)) return jsonResponse([ACCOUNT]);
    if (/\/assets/.test(url)) return jsonResponse([]);
    throw new Error(`Nessun mock per ${url}`);
  });
}

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <TaxLossPocketPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("TaxLossPocketPage — impaginazione", () => {
  afterEach(() => vi.restoreAllMocks());

  it("con molte righe mostra solo la prima pagina e permette di scorrere", async () => {
    mockApi(40);
    renderPage();

    // 15 righe per pagina: l'indicatore dice dove ci si trova su 40.
    expect(await screen.findByText(/1.{1,3}15.{1,10}40/)).toBeInTheDocument();
    expect(screen.getAllByRole("row")).toHaveLength(1 + 15); // intestazione + pagina

    fireEvent.click(screen.getAllByRole("button", { name: /successiva|next/i })[0]);
    await waitFor(() => expect(screen.getByText(/16.{1,3}30.{1,10}40/)).toBeInTheDocument());
  });

  it("con poche righe non mostra la barra di impaginazione", async () => {
    mockApi(5);
    renderPage();
    await waitFor(() => expect(screen.getAllByRole("row")).toHaveLength(1 + 5));
    expect(screen.queryByRole("navigation")).not.toBeInTheDocument();
  });
});
