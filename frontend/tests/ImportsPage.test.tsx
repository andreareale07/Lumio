import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ImportsPage } from "../src/features/imports/ImportsPage";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

function makeImport(id: string, overrides: Record<string, unknown> = {}) {
  return {
    id,
    workspace_id: "w1",
    financial_account_id: "acc-1",
    import_mapping_id: null,
    mapping_config: null,
    file_type: "csv",
    bank_id: null,
    bank_parser_id: null,
    job_id: null,
    status: "completed",
    filename: "estratto.csv",
    file_hash: "hash",
    file_size: 100,
    period_start: "2026-01-01",
    period_end: "2026-01-31",
    transactions_found: 2,
    transactions_imported: 2,
    error_message: null,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    completed_at: "2026-01-01T00:00:05Z",
    ...overrides,
  };
}

const ACCOUNT = { id: "acc-1", name: "Conto Test", account_type: "checking", currency: "EUR" };

function mockApiRoutes(routes: Record<string, unknown>) {
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const url = String(input);
    for (const [path, body] of Object.entries(routes)) {
      if (url.includes(path)) return jsonResponse(body);
    }
    return jsonResponse([]);
  });
}

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/imports"]}>
        <ImportsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("ImportsPage — elimina import", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("il bottone Elimina è disabilitato con tooltip solo per import in elaborazione", async () => {
    mockApiRoutes({
      "/imports": [makeImport("i1", { status: "completed" }), makeImport("i2", { status: "processing" })],
      "/accounts": [ACCOUNT],
    });
    renderPage();

    const deleteButtons = await screen.findAllByRole("button", { name: "Elimina import" });
    expect(deleteButtons).toHaveLength(2);
    expect(deleteButtons[0]).not.toBeDisabled();
    expect(deleteButtons[1]).toBeDisabled();
    expect(deleteButtons[1]).toHaveAttribute("title", expect.stringContaining("elaborazione"));
  });

  it("il dialog di conferma mostra il conteggio reale delle transazioni", async () => {
    mockApiRoutes({
      "/imports/i1/transactions-count": { transactions_count: 7 },
      "/imports": [makeImport("i1")],
      "/accounts": [ACCOUNT],
    });
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole("button", { name: "Elimina import" }));

    expect(await screen.findByText(/Verranno eliminate 7 transazioni/)).toBeInTheDocument();
  });

  it("pluralizza correttamente con una sola transazione", async () => {
    mockApiRoutes({
      "/imports/i1/transactions-count": { transactions_count: 1 },
      "/imports": [makeImport("i1")],
      "/accounts": [ACCOUNT],
    });
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole("button", { name: "Elimina import" }));

    expect(await screen.findByText(/Verrà eliminata 1 transazione/)).toBeInTheDocument();
  });

  it("click su Elimina chiama la DELETE e aggiorna la lista", async () => {
    let deleteCalled = false;
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.includes("/imports/i1/transactions-count")) return jsonResponse({ transactions_count: 0 });
      if (url.includes("/imports/i1") && init?.method === "DELETE") {
        deleteCalled = true;
        return jsonResponse({ deleted_transactions_count: 0 });
      }
      if (url.includes("/imports")) return jsonResponse(deleteCalled ? [] : [makeImport("i1")]);
      if (url.includes("/accounts")) return jsonResponse([ACCOUNT]);
      return jsonResponse([]);
    });

    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole("button", { name: "Elimina import" }));
    await user.click(await screen.findByRole("button", { name: "Elimina" }));

    expect(deleteCalled).toBe(true);
    expect(await screen.findByText("Nessuna importazione")).toBeInTheDocument();
  });

  it("un errore sulla eliminazione non chiude il dialog", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.includes("/imports/i1/transactions-count")) return jsonResponse({ transactions_count: 0 });
      if (url.includes("/imports/i1") && init?.method === "DELETE") {
        return jsonResponse({ detail: "Import in elaborazione: attendi il completamento prima di poterlo eliminare" }, 409);
      }
      if (url.includes("/imports")) return jsonResponse([makeImport("i1")]);
      if (url.includes("/accounts")) return jsonResponse([ACCOUNT]);
      return jsonResponse([]);
    });

    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole("button", { name: "Elimina import" }));
    await user.click(await screen.findByRole("button", { name: "Elimina" }));

    expect(await screen.findByText(/Import in elaborazione/)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Eliminare l'import?" })).toBeInTheDocument();
  });

  it("il viewer CSV mostra la tabella completa del file", async () => {
    mockApiRoutes({
      "/imports/i1/file-content": {
        columns: ["Data", "Importo"],
        rows: [["2026-01-01", "10.00"]],
        truncated: false,
        total_rows: 1,
      },
      "/imports": [makeImport("i1")],
      "/accounts": [ACCOUNT],
    });
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole("button", { name: "Visualizza file originale" }));

    expect(await screen.findByText("Data")).toBeInTheDocument();
    expect(screen.getByText("10.00")).toBeInTheDocument();
  });

  describe("viewer PDF (blob URL)", () => {
    beforeEach(() => {
      vi.stubGlobal("URL", {
        ...URL,
        createObjectURL: vi.fn(() => "blob:mock-url"),
        revokeObjectURL: vi.fn(),
      });
    });

    it("scarica il file come blob e lo passa a <embed>", async () => {
      vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
        const url = String(input);
        if (url.includes("/imports/i1/file")) {
          return new Response(new Blob(["%PDF-1.4"]), { status: 200 });
        }
        if (url.includes("/imports")) return jsonResponse([makeImport("i1", { file_type: "pdf" })]);
        if (url.includes("/accounts")) return jsonResponse([ACCOUNT]);
        return jsonResponse([]);
      });

      const user = userEvent.setup();
      renderPage();

      await user.click(await screen.findByRole("button", { name: "Visualizza file originale" }));

      // <embed> non ha un ruolo accessibile riconosciuto da jsdom: si
      // verifica direttamente l'attributo src sul nodo nel DOM.
      await vi.waitFor(() => {
        expect(document.querySelector("embed")).not.toBeNull();
      });
      expect(document.querySelector("embed")?.getAttribute("src")).toBe("blob:mock-url");
    });

    it("mostra un errore se il download del file falisce", async () => {
      vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
        const url = String(input);
        if (url.includes("/imports/i1/file")) return jsonResponse({ detail: "not found" }, 404);
        if (url.includes("/imports")) return jsonResponse([makeImport("i1", { file_type: "pdf" })]);
        if (url.includes("/accounts")) return jsonResponse([ACCOUNT]);
        return jsonResponse([]);
      });

      const user = userEvent.setup();
      renderPage();

      await user.click(await screen.findByRole("button", { name: "Visualizza file originale" }));

      expect(await screen.findByText(/Non siamo riusciti a caricare il file originale/)).toBeInTheDocument();
    });
  });
});
