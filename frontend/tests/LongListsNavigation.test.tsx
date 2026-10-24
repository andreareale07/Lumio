import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AuthProvider } from "../src/app/providers/AuthProvider";
import { ImportsPage } from "../src/features/imports/ImportsPage";
import { TransactionTypeMappingsPage } from "../src/features/settings/transaction-types/TransactionTypeMappingsPage";
import type { ImportRecord, ImportStatus, TransactionTypeLabel } from "../src/types/api";

function renderWithProviders(ui: ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <AuthProvider>{ui}</AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function stubApi(routes: Record<string, unknown>) {
  vi.stubGlobal(
    "fetch",
    vi.fn<typeof fetch>(async (input) => {
      const url = String(input);
      const key = Object.keys(routes)
        .filter((path) => url.includes(path))
        .sort((a, b) => b.length - a.length)[0];
      const body = key ? routes[key] : null;
      // Nessuna sessione: AuthProvider si assesta su user: null.
      const status = url.includes("/auth/") ? 401 : 200;
      return new Response(JSON.stringify(status === 401 ? { detail: "no" } : body), {
        status,
        headers: { "Content-Type": "application/json" },
      });
    }),
  );
}

function makeImport(index: number, status: ImportStatus = "completed"): ImportRecord {
  return {
    id: `import-${index}`,
    workspace_id: "ws-1",
    financial_account_id: null,
    import_mapping_id: null,
    mapping_config: null,
    file_type: "csv",
    bank_id: null,
    bank_parser_id: null,
    job_id: null,
    status,
    filename: `estratto-${String(index).padStart(2, "0")}.csv`,
    file_hash: `hash-${index}`,
    file_size: 1000,
    period_start: null,
    period_end: null,
    transactions_found: 10,
    transactions_imported: 10,
    transactions_duplicate: 0,
    transactions_review_pending: 0,
    error_message: null,
    created_at: "2026-10-01T10:00:00Z",
    updated_at: "2026-10-01T10:00:00Z",
    completed_at: "2026-10-01T10:00:00Z",
    ai_classification_status: null,
    ai_transactions_total: 0,
    ai_transactions_classified: 0,
    ai_classification_error_message: null,
  };
}

function makeLabel(index: number, override: TransactionTypeLabel["override"] = null): TransactionTypeLabel {
  return {
    source_type_raw: `Etichetta ${String(index).padStart(2, "0")}`,
    total_count: 3,
    current_types: [{ transaction_type: "expense", count: 3 }],
    override,
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("Elenco import", () => {
  const ROUTES = (imports: ImportRecord[]) => ({
    "/imports": imports,
    "/accounts": [],
    "/review-summary": { pending: 0 },
    "/transactions/review-summary": { needs_review: 0, total: 0 },
  });

  it("mostra solo una pagina di import e dice dove ci si trova", async () => {
    stubApi(ROUTES(Array.from({ length: 25 }, (_, i) => makeImport(i + 1))));
    renderWithProviders(<ImportsPage />);

    expect(await screen.findByText("estratto-01.csv")).toBeInTheDocument();
    expect(screen.getByText("estratto-10.csv")).toBeInTheDocument();
    expect(screen.queryByText("estratto-11.csv")).not.toBeInTheDocument();
    expect(screen.getByText("1–10 di 25")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Successiva" }));
    expect(await screen.findByText("estratto-11.csv")).toBeInTheDocument();
    expect(screen.getByText("11–20 di 25")).toBeInTheDocument();
  });

  it("cerca per nome del file", async () => {
    stubApi(ROUTES(Array.from({ length: 25 }, (_, i) => makeImport(i + 1))));
    renderWithProviders(<ImportsPage />);
    await screen.findByText("estratto-01.csv");

    await userEvent.type(screen.getByRole("searchbox", { name: "Cerca negli import" }), "estratto-17");

    expect(await screen.findByText("estratto-17.csv")).toBeInTheDocument();
    expect(screen.queryByText("estratto-01.csv")).not.toBeInTheDocument();
    expect(screen.queryByRole("navigation", { name: "Impaginazione" })).not.toBeInTheDocument();
  });

  it("filtra per stato: i falliti o annullati", async () => {
    const imports = [
      ...Array.from({ length: 12 }, (_, i) => makeImport(i + 1)),
      { ...makeImport(13, "failed"), error_message: "File non leggibile" },
      makeImport(14, "cancelled"),
    ];
    stubApi(ROUTES(imports));
    renderWithProviders(<ImportsPage />);
    await screen.findByText("estratto-01.csv");

    await userEvent.selectOptions(screen.getByLabelText("Stato"), "failed");

    expect(await screen.findByText("estratto-13.csv")).toBeInTheDocument();
    expect(screen.getByText("estratto-14.csv")).toBeInTheDocument();
    expect(screen.queryByText("estratto-01.csv")).not.toBeInTheDocument();
  });

  it("senza risultati lo dice e offre di azzerare i filtri", async () => {
    stubApi(ROUTES(Array.from({ length: 12 }, (_, i) => makeImport(i + 1))));
    renderWithProviders(<ImportsPage />);
    await screen.findByText("estratto-01.csv");

    await userEvent.type(screen.getByRole("searchbox", { name: "Cerca negli import" }), "zzz");
    expect(await screen.findByText("Nessun import corrisponde alla ricerca.")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Azzera i filtri" }));
    expect(await screen.findByText("estratto-01.csv")).toBeInTheDocument();
  });
});

describe("Mappatura dei tipi di transazione", () => {
  const ROUTES = (labels: TransactionTypeLabel[]) => ({
    "/settings/transaction-types/parsers": ["trade_republic_pdf"],
    "/settings/transaction-types/trade_republic_pdf/labels": labels,
  });

  it("impagina le etichette e mostra il riepilogo", async () => {
    stubApi(ROUTES(Array.from({ length: 20 }, (_, i) => makeLabel(i + 1, i === 4 ? "income" : null))));
    renderWithProviders(<TransactionTypeMappingsPage />);

    expect(await screen.findByText("Etichetta 01")).toBeInTheDocument();
    expect(screen.getByText("Etichetta 08")).toBeInTheDocument();
    expect(screen.queryByText("Etichetta 09")).not.toBeInTheDocument();
    expect(screen.getByText("20 etichette, 1 con mappatura personalizzata")).toBeInTheDocument();
    expect(screen.getByText("1–8 di 20")).toBeInTheDocument();
  });

  it("il filtro mostra solo le etichette con mappatura personalizzata", async () => {
    stubApi(ROUTES(Array.from({ length: 20 }, (_, i) => makeLabel(i + 1, i === 4 || i === 15 ? "income" : null))));
    renderWithProviders(<TransactionTypeMappingsPage />);
    await screen.findByText("Etichetta 01");

    await userEvent.selectOptions(screen.getByLabelText("Mostra"), "overrides");

    expect(await screen.findByText("Etichetta 05")).toBeInTheDocument();
    expect(screen.getByText("Etichetta 16")).toBeInTheDocument();
    expect(screen.queryByText("Etichetta 01")).not.toBeInTheDocument();
  });

  it("la ricerca trova un'etichetta in mezzo a molte", async () => {
    stubApi(ROUTES(Array.from({ length: 20 }, (_, i) => makeLabel(i + 1))));
    renderWithProviders(<TransactionTypeMappingsPage />);
    await screen.findByText("Etichetta 01");

    await userEvent.type(screen.getByRole("searchbox", { name: "Cerca nelle etichette" }), "etichetta 19");

    expect(await screen.findByText("Etichetta 19")).toBeInTheDocument();
    expect(screen.queryByText("Etichetta 01")).not.toBeInTheDocument();
  });
});
