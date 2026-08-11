import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { TransactionTypeMappingsPage } from "../src/features/settings/transaction-types/TransactionTypeMappingsPage";

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <TransactionTypeMappingsPage />
    </QueryClientProvider>,
  );
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

// Le chiavi PIU' SPECIFICHE (con suffisso "/Bonifico") vanno elencate PRIMA
// di quelle generiche ("/labels"): la substring match risolve al primo
// percorso che compare come sottostringa dell'URL, stesso principio gia'
// documentato in InvestmentsPage.test.tsx.
function mockApiRoutes(routes: Record<string, unknown>) {
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const url = String(input);
    for (const [path, body] of Object.entries(routes)) {
      if (url.includes(path)) return jsonResponse(body);
    }
    return jsonResponse([]);
  });
}

const BONIFICO_LABEL = {
  source_type_raw: "Bonifico",
  total_count: 3,
  current_types: [
    { transaction_type: "income", count: 2 },
    { transaction_type: "expense", count: 1 },
  ],
  override: null,
};

describe("TransactionTypeMappingsPage", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("mostra l'empty state quando non c'e' ancora nessun import PDF", async () => {
    mockApiRoutes({ "/settings/transaction-types/parsers": [] });
    renderPage();

    expect(await screen.findByText("Nessuna etichetta ancora")).toBeInTheDocument();
  });

  it("elenca le etichette osservate con il riepilogo dei tipi attuali", async () => {
    mockApiRoutes({
      "/settings/transaction-types/parsers": ["trade_republic_pdf"],
      "/settings/transaction-types/trade_republic_pdf/labels": [BONIFICO_LABEL],
    });
    renderPage();

    expect(await screen.findByText("Bonifico")).toBeInTheDocument();
    expect(screen.getByText(/3 transazioni/)).toBeInTheDocument();
    expect(screen.getByText(/Entrata \(2\)/)).toBeInTheDocument();
    expect(screen.getByText(/Spesa \(1\)/)).toBeInTheDocument();
    expect(screen.queryByText("Override attivo")).not.toBeInTheDocument();
  });

  it("mostra il badge 'Override attivo' quando esiste una regola salvata", async () => {
    mockApiRoutes({
      "/settings/transaction-types/parsers": ["trade_republic_pdf"],
      "/settings/transaction-types/trade_republic_pdf/labels": [{ ...BONIFICO_LABEL, override: "transfer" }],
    });
    renderPage();

    expect(await screen.findByText("Override attivo")).toBeInTheDocument();
  });

  it("salva un override e mostra il risultato della rimappatura retroattiva", async () => {
    mockApiRoutes({
      "/settings/transaction-types/trade_republic_pdf/labels/Bonifico": {
        source_type_raw: "Bonifico",
        transaction_type: "transfer",
        reapply: { updated: 2, skipped: 1 },
      },
      "/settings/transaction-types/parsers": ["trade_republic_pdf"],
      "/settings/transaction-types/trade_republic_pdf/labels": [BONIFICO_LABEL],
    });
    const user = userEvent.setup();
    renderPage();

    await screen.findByText("Bonifico");
    await user.selectOptions(screen.getByLabelText('Tipo per "Bonifico"'), "transfer");
    await user.click(screen.getByRole("button", { name: "Salva" }));

    expect(
      await screen.findByText("2 transazioni aggiornate, 1 lasciate intatte perché modificate a mano."),
    ).toBeInTheDocument();
  });

  it("rimuove l'override quando l'utente clicca 'Rimuovi override'", async () => {
    mockApiRoutes({
      "/settings/transaction-types/trade_republic_pdf/labels/Bonifico": null,
      "/settings/transaction-types/parsers": ["trade_republic_pdf"],
      "/settings/transaction-types/trade_republic_pdf/labels": [{ ...BONIFICO_LABEL, override: "transfer" }],
    });
    const user = userEvent.setup();
    renderPage();

    await screen.findByText("Override attivo");
    await user.click(screen.getByRole("button", { name: "Rimuovi override" }));

    // Nessun crash / nessun errore mostrato: la DELETE e' andata a buon
    // fine (mock 200 con corpo null, coerente col 204 reale via apiClient).
    expect(screen.queryByText(/non siamo riusciti/i)).not.toBeInTheDocument();
  });
});
