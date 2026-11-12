import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { RuleSuggestionCard } from "../src/features/rules/RuleSuggestionCard";
import type { Category, RuleSuggestion } from "../src/types/api";

const CATEGORY: Category = {
  id: "cat-rata",
  workspace_id: null,
  parent_id: null,
  name: "Rata mutuo",
  code: "rata_mutuo",
  kind: "expense",
  is_system: false,
  is_active: true,
  sort_order: 10,
};

const SUGGESTION: RuleSuggestion = {
  category_id: CATEGORY.id,
  occurrences: 2,
  transaction_ids: ["a", "b"],
  label: "Rata Mutuo",
  ambiguous: true,
  options: [
    {
      key: "precise",
      conditions: [
        { field: "description", operator: "contains", value: "Rata Mutuo" },
        { field: "description", operator: "contains", value: "BENEF. Reale Francesco" },
      ],
      match_mode: "all",
      would_change: 3,
      already_correct: 9,
      protected: 0,
    },
    {
      key: "recommended",
      conditions: [{ field: "description", operator: "contains", value: "Rata Mutuo" }],
      match_mode: "all",
      would_change: 3,
      already_correct: 9,
      protected: 0,
    },
    {
      key: "broad",
      conditions: [{ field: "description", operator: "contains", value: "BONIFICO SEPA" }],
      match_mode: "all",
      would_change: 13,
      already_correct: 9,
      protected: 2,
    },
  ],
};

function renderCard(onCreate = vi.fn()) {
  vi.stubGlobal(
    "fetch",
    vi.fn<typeof fetch>(
      async () => new Response(JSON.stringify([CATEGORY]), { status: 200, headers: { "Content-Type": "application/json" } }),
    ),
  );
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <RuleSuggestionCard suggestion={SUGGESTION} onCreate={onCreate} />
    </QueryClientProvider>,
  );
  return onCreate;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("RuleSuggestionCard", () => {
  it("la scheda resta compatta e le proposte si aprono in un foglio", async () => {
    renderCard();
    expect(await screen.findByText("Rata mutuo")).toBeInTheDocument();
    expect(screen.queryByRole("radio")).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Vedi proposte" }));

    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getAllByRole("radio")).toHaveLength(3);
  });

  it("segnala che il testo da solo non distingue le categorie", async () => {
    renderCard();
    await userEvent.click(await screen.findByRole("button", { name: "Vedi proposte" }));
    expect(await screen.findByText(/hanno categorie diverse/)).toBeInTheDocument();
  });

  it("preseleziona la consigliata e mostra per ognuna cosa cambia", async () => {
    renderCard();
    await userEvent.click(await screen.findByRole("button", { name: "Vedi proposte" }));
    await screen.findByRole("radiogroup");
    expect(screen.getByRole("radio", { name: /Consigliata/ })).toHaveAttribute("aria-checked", "true");
    expect(screen.getByRole("radio", { name: /Più ampia/ })).toHaveTextContent("24 movimenti: 13 cambiano, 9 già giusti, 2 protetti");
  });

  it("crea la regola con le condizioni dell'opzione scelta", async () => {
    const onCreate = renderCard();
    await userEvent.click(await screen.findByRole("button", { name: "Vedi proposte" }));
    await userEvent.click(await screen.findByRole("radio", { name: /Più precisa/ }));

    await userEvent.click(screen.getByRole("button", { name: "Crea regola" }));

    expect(onCreate).toHaveBeenCalledWith({
      conditions: SUGGESTION.options[0].conditions,
      match_mode: "all",
      category_id: CATEGORY.id,
    });
  });
});
