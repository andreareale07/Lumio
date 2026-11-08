import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { TransactionDetailDrawer } from "../src/features/transactions/TransactionDetailDrawer";
import type { Transaction } from "../src/types/api";
import { setDesktop } from "./matchMedia";

const transaction = {
  id: "t1",
  workspace_id: "w1",
  financial_account_id: "acc-1",
  category_id: null,
  transaction_date: "2026-08-05",
  description_raw: "Movimento di prova",
  description_normalized: "Movimento di prova",
  merchant: null,
  amount: "-10.00",
  currency: "EUR",
  direction: "debit",
  transaction_type: "expense",
  source_type_raw: null,
  import_id: null,
  created_at: "2026-08-05T00:00:00Z",
  updated_at: "2026-08-05T00:00:00Z",
} as unknown as Transaction;

function renderDrawer(onClose = vi.fn()) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <TransactionDetailDrawer transaction={transaction} onClose={onClose} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return onClose;
}

function mockFetch(deleteStatus = 204) {
  const calls: { url: string; method: string }[] = [];
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const method = (init?.method ?? "GET").toUpperCase();
    calls.push({ url: String(input), method });
    if (method === "DELETE") {
      return deleteStatus === 204
        ? new Response(null, { status: 204 })
        : new Response(JSON.stringify({ detail: "x" }), { status: deleteStatus, headers: { "Content-Type": "application/json" } });
    }
    return new Response("[]", { status: 200, headers: { "Content-Type": "application/json" } });
  });
  return calls;
}

describe("Eliminazione di un singolo movimento", () => {
  afterEach(() => vi.restoreAllMocks());

  it("chiede conferma, poi elimina e chiude il dettaglio (anche su smartphone)", async () => {
    setDesktop(false);
    const user = userEvent.setup();
    const calls = mockFetch();
    const onClose = renderDrawer();

    await user.click(screen.getByRole("button", { name: "Elimina movimento" }));
    expect(screen.getByText("Eliminare questo movimento?")).toBeInTheDocument();
    expect(calls.some((c) => c.method === "DELETE")).toBe(false); // nulla prima della conferma

    await user.click(screen.getByRole("button", { name: "Elimina" }));

    await waitFor(() => expect(onClose).toHaveBeenCalled());
    expect(calls.filter((c) => c.method === "DELETE").map((c) => c.url)).toEqual([expect.stringContaining("/transactions/t1")]);
  });

  it("annullare non elimina nulla", async () => {
    setDesktop(true);
    const user = userEvent.setup();
    const calls = mockFetch();
    const onClose = renderDrawer();

    await user.click(screen.getByRole("button", { name: "Elimina movimento" }));
    await user.click(screen.getByRole("button", { name: "Annulla" }));

    expect(calls.some((c) => c.method === "DELETE")).toBe(false);
    expect(onClose).not.toHaveBeenCalled();
    expect(screen.queryByText("Eliminare questo movimento?")).not.toBeInTheDocument();
  });

  it("se l'eliminazione fallisce mostra l'errore e lascia aperta la finestra per riprovare", async () => {
    setDesktop(true);
    const user = userEvent.setup();
    mockFetch(500);
    const onClose = renderDrawer();

    await user.click(screen.getByRole("button", { name: "Elimina movimento" }));
    await user.click(screen.getByRole("button", { name: "Elimina" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/Non è stato possibile eliminare/);
    expect(onClose).not.toHaveBeenCalled();
    expect(screen.getByText("Eliminare questo movimento?")).toBeInTheDocument();
  });
});
