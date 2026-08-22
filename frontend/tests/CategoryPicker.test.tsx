import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CategoryPicker } from "../src/features/categories/CategoryPicker";
import type { Category } from "../src/types/api";

const CATEGORIES: Category[] = [
  { id: "casa", workspace_id: null, parent_id: null, name: "Casa", code: "casa", kind: "expense", is_system: false, is_active: true, sort_order: 10 },
  { id: "casa.bollette", workspace_id: null, parent_id: "casa", name: "Bollette", code: "casa.bollette", kind: "expense", is_system: false, is_active: true, sort_order: 12 },
  { id: "alimentari", workspace_id: null, parent_id: null, name: "Alimentari", code: "alimentari", kind: "expense", is_system: false, is_active: true, sort_order: 20 },
];

function renderWithClient(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

describe("CategoryPicker", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("elenca le categorie raggruppate per padre, aprendo il popover del Combobox", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify(CATEGORIES), { status: 200, headers: { "Content-Type": "application/json" } }),
    );
    const user = userEvent.setup();

    renderWithClient(<CategoryPicker />);

    // Il trigger e' un <button> labelable: <label for> vince sul testo
    // visibile nel calcolo del nome accessibile (e' "Categoria", non il
    // placeholder "Seleziona una categoria…") — stesso motivo per cui
    // RuleFormDialog lo trova con getByLabelText, non getByRole+name.
    // Resta disabilitato finche' le categorie non sono arrivate (isLoading):
    // aspettarne l'abilitazione invece di cliccarlo subito.
    const trigger = screen.getByLabelText("Categoria");
    await waitFor(() => expect(trigger).toBeEnabled());
    await user.click(trigger);

    // "Bollette" e' figlia di "Casa": raggruppata sotto quell'intestazione,
    // non piu' come etichetta combinata "Casa › Bollette" (rework: il
    // Combobox mostra il gruppo come header, non nella label dell'opzione).
    // "Casa" compare due volte apposta: come opzione radice selezionabile
    // E come intestazione del gruppo dei suoi figli — da qui `getAllByText`.
    await waitFor(() => expect(screen.getAllByText("Casa").length).toBeGreaterThanOrEqual(2));
    expect(screen.getByRole("option", { name: "Casa" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Bollette" })).toBeInTheDocument();
    // "Alimentari" e' una radice senza figli: nessun gruppo, opzione diretta.
    expect(screen.getByRole("option", { name: "Alimentari" })).toBeInTheDocument();
  });
});
