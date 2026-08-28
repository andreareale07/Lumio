import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { TransactionsPage } from "../src/features/transactions/TransactionsPage";
import { periodForAnchor } from "../src/lib/period";

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
}

function makeTransaction(id: string, overrides: Record<string, unknown> = {}) {
  return {
    id,
    workspace_id: "w1",
    financial_account_id: "acc-1",
    category_id: null,
    transaction_date: "2026-08-05",
    description_raw: `Movimento ${id}`,
    description_normalized: `Movimento ${id}`,
    merchant: null,
    amount: "-10.00",
    currency: "EUR",
    direction: "debit",
    transaction_type: "expense",
    source_type_raw: null,
    import_id: null,
    created_at: "2026-08-05T00:00:00Z",
    updated_at: "2026-08-05T00:00:00Z",
    ...overrides,
  };
}

function renderPage(initialEntry = "/transactions") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <TransactionsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("TransactionsPage — filtro periodo", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("di default non applica alcun filtro data (mostra tutti i periodi)", async () => {
    // Regressione reale scoperta in questo slice: un default a "questo
    // mese" nasconderebbe silenziosamente un import appena fatto con date
    // diverse (rotto proprio questo scenario negli E2E import/rules-
    // golden-path). Transazioni e' una pagina di consultazione, non un
    // riepilogo: deve mostrare tutto finche' l'utente non filtra a mano.
    const requestedUrls: string[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      requestedUrls.push(url);
      if (url.includes("/transactions")) return jsonResponse([makeTransaction("t1", { transaction_date: "2020-02-01" })]);
      if (url.includes("/accounts")) return jsonResponse([]);
      if (url.includes("/categories")) return jsonResponse([]);
      return jsonResponse([]);
    });

    renderPage();
    const table = await screen.findByRole("table");
    within(table).getByText("Movimento t1");

    const txUrl = requestedUrls.find((u) => u.includes("/transactions"));
    expect(txUrl).not.toContain("date_from");
    expect(txUrl).not.toContain("date_to");
    expect(screen.getByText("Max")).toBeInTheDocument();
  });

  it("passa date_from/date_to quando l'utente attiva un filtro periodo", async () => {
    const requestedUrls: string[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      requestedUrls.push(url);
      if (url.includes("/transactions")) return jsonResponse([makeTransaction("t1")]);
      if (url.includes("/accounts")) return jsonResponse([]);
      if (url.includes("/categories")) return jsonResponse([]);
      return jsonResponse([]);
    });

    renderPage("/transactions?mode=granular&granularity=month&anchor=2026-03-01");
    const table = await screen.findByRole("table");
    within(table).getByText("Movimento t1");

    const expected = periodForAnchor("month", new Date(2026, 2, 1));
    const txUrl = requestedUrls.find((u) => u.includes("/transactions"));
    expect(txUrl).toContain(`date_from=${expected.date_from}`);
    expect(txUrl).toContain(`date_to=${expected.date_to}`);
  });

  it("cambiare periodo azzera l'offset di paginazione", async () => {
    const requestedUrls: string[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      requestedUrls.push(url);
      if (url.includes("/transactions")) {
        // 25 risultati per restare su una pagina "piena" (bottone Successivi abilitato)
        return jsonResponse(Array.from({ length: 25 }, (_, i) => makeTransaction(`t${i}`)));
      }
      if (url.includes("/accounts")) return jsonResponse([]);
      if (url.includes("/categories")) return jsonResponse([]);
      return jsonResponse([]);
    });

    const user = userEvent.setup();
    renderPage("/transactions?mode=granular&granularity=month&anchor=2026-03-01");
    const table = await screen.findByRole("table");
    within(table).getByText("Movimento t0");

    await user.click(screen.getByRole("button", { name: /Successivi/ }));
    await vi.waitFor(() => {
      expect(requestedUrls.some((u) => u.includes("/transactions") && u.includes("offset=25"))).toBe(true);
    });

    await user.click(screen.getByRole("button", { name: "Periodo precedente" }));

    await vi.waitFor(() => {
      // La richiesta con la NUOVA data puo' transitoriamente arrivare ancora
      // con l'offset vecchio (il render con `currentPeriod` aggiornato
      // precede l'effect che azzera `offset`) — quello che conta e' che
      // arrivi ANCHE una richiesta corretta con entrambi i valori nuovi.
      const afterPeriodChange = requestedUrls.filter((u) => u.includes("/transactions") && u.includes("date_from=2026-02-01"));
      expect(afterPeriodChange.some((u) => u.includes("offset=0"))).toBe(true);
    });
  });
});
