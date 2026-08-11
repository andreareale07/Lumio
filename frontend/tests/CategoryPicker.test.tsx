import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CategoryPicker } from "../src/features/categories/CategoryPicker";
import type { Category } from "../src/types/api";

const CATEGORIES: Category[] = [
  { id: "casa", workspace_id: null, parent_id: null, name: "Casa", code: "casa", is_system: true, is_active: true, sort_order: 10 },
  { id: "casa.bollette", workspace_id: null, parent_id: "casa", name: "Bollette", code: "casa.bollette", is_system: true, is_active: true, sort_order: 12 },
  { id: "alimentari", workspace_id: null, parent_id: null, name: "Alimentari", code: "alimentari", is_system: true, is_active: true, sort_order: 20 },
];

function renderWithClient(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

describe("CategoryPicker", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("elenca le categorie con etichetta gerarchica per le sottocategorie", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify(CATEGORIES), { status: 200, headers: { "Content-Type": "application/json" } }),
    );

    renderWithClient(<CategoryPicker />);

    await waitFor(() => expect(screen.getByRole("option", { name: "Casa › Bollette" })).toBeInTheDocument());
    expect(screen.getByRole("option", { name: "Alimentari" })).toBeInTheDocument();
  });
});
