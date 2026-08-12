import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CategoriesSettingsPage } from "../src/features/categories/CategoriesSettingsPage";
import type { Category } from "../src/types/api";

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <CategoriesSettingsPage />
    </QueryClientProvider>,
  );
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(body === null ? null : JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const SYSTEM_CATEGORY: Category = {
  id: "casa",
  workspace_id: null,
  parent_id: null,
  name: "Casa",
  code: "casa",
  is_system: true,
  is_active: true,
  sort_order: 10,
};

const CUSTOM_CATEGORY: Category = {
  id: "hobby",
  workspace_id: "ws-1",
  parent_id: null,
  name: "Hobby",
  code: "hobby",
  is_system: false,
  is_active: true,
  sort_order: 20,
};

describe("CategoriesSettingsPage", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("mostra le categorie di sistema come sola lettura e quelle personalizzate con le azioni", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse([SYSTEM_CATEGORY, CUSTOM_CATEGORY]));

    renderPage();

    await screen.findByText("Casa");
    expect(screen.getByText("Sistema")).toBeInTheDocument();
    expect(screen.getByText("Hobby")).toBeInTheDocument();

    // La riga di sistema non deve avere azioni di modifica (il backend le rifiuterebbe con 403).
    const casaRow = screen.getByText("Casa").closest("div.rounded-xl");
    expect(casaRow).not.toBeNull();
    expect(casaRow!.textContent).not.toMatch(/Modifica|Elimina/);

    const hobbyRow = screen.getByText("Hobby").closest("div.rounded-xl");
    expect(hobbyRow).not.toBeNull();
    expect(hobbyRow!.textContent).toMatch(/Modifica/);
    expect(hobbyRow!.textContent).toMatch(/Elimina/);
  });

  it("mostra l'errore quando l'eliminazione fallisce perché la categoria è ancora in uso", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      const method = init?.method ?? "GET";
      if (method === "DELETE" && url.includes("/categories/hobby")) {
        return jsonResponse(
          { detail: "Categoria in uso da transazioni o sotto-categorie: disattivala invece di eliminarla" },
          409,
        );
      }
      return jsonResponse([CUSTOM_CATEGORY]);
    });

    const user = userEvent.setup();
    renderPage();

    await screen.findByText("Hobby");
    await user.click(screen.getByRole("button", { name: "Elimina" }));
    await user.click(screen.getByRole("dialog").querySelector("button.bg-danger") as HTMLButtonElement);

    expect(
      await screen.findByText("Categoria in uso da transazioni o sotto-categorie: disattivala invece di eliminarla"),
    ).toBeInTheDocument();
  });
});
