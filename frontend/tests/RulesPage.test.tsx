import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { RulesPage } from "../src/features/rules/RulesPage";
import type { Category, JobRun, Rule } from "../src/types/api";

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <RulesPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const CATEGORY: Category = {
  id: "cat-1",
  workspace_id: null,
  parent_id: null,
  name: "Streaming",
  code: "streaming",
  kind: "expense",
  is_system: false,
  is_active: true,
  sort_order: 10,
};

function makeRules(count: number, inactive: number[] = []): Rule[] {
  return Array.from({ length: count }, (_, index) => ({
    id: `rule-${index + 1}`,
    workspace_id: "ws-1",
    name: `Regola ${String(index + 1).padStart(2, "0")}`,
    field: "description",
    operator: "contains",
    value: `testo-${index + 1}`,
    category_id: CATEGORY.id,
    priority: 100,
    is_active: !inactive.includes(index + 1),
    created_at: "2026-10-01T00:00:00Z",
    updated_at: "2026-10-01T00:00:00Z",
  }));
}

function stubApi(routes: Record<string, unknown>) {
  const fetchMock = vi.fn<typeof fetch>(async (input) => {
    const url = String(input);
    // La rotta piu' specifica vince: "/rules/suggestions" prima di "/rules".
    const key = Object.keys(routes)
      .filter((path) => url.includes(path))
      .sort((a, b) => b.length - a.length)[0];
    return new Response(JSON.stringify(key ? routes[key] : null), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

const BASE_ROUTES = {
  "/categories": [CATEGORY],
  "/rules/suggestions": [],
  "/classification/reclassify/status": null,
};

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("RulesPage", () => {
  it("mostra solo una pagina di regole e dice dove ci si trova", async () => {
    stubApi({ ...BASE_ROUTES, "/rules": makeRules(30) });
    renderPage();

    expect(await screen.findByText("Regola 01")).toBeInTheDocument();
    expect(screen.getByText("Regola 12")).toBeInTheDocument();
    expect(screen.queryByText("Regola 13")).not.toBeInTheDocument();
    expect(screen.getByText("1–12 di 30")).toBeInTheDocument();
    expect(screen.getByText("30 regole (30 attive)")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Successiva" }));

    expect(await screen.findByText("Regola 13")).toBeInTheDocument();
    expect(screen.queryByText("Regola 01")).not.toBeInTheDocument();
    expect(screen.getByText("13–24 di 30")).toBeInTheDocument();
  });

  it("non mostra l'impaginazione quando tutto sta in una pagina", async () => {
    stubApi({ ...BASE_ROUTES, "/rules": makeRules(5) });
    renderPage();

    expect(await screen.findByText("Regola 05")).toBeInTheDocument();
    expect(screen.queryByRole("navigation", { name: "Impaginazione" })).not.toBeInTheDocument();
  });

  it("la ricerca restringe l'elenco e riporta alla prima pagina", async () => {
    stubApi({ ...BASE_ROUTES, "/rules": makeRules(30) });
    renderPage();
    await screen.findByText("Regola 01");
    await userEvent.click(screen.getByRole("button", { name: "Successiva" }));
    expect(await screen.findByText("Regola 13")).toBeInTheDocument();

    await userEvent.type(screen.getByRole("searchbox", { name: "Cerca nelle regole" }), "regola 2");

    expect(await screen.findByText("Regola 20")).toBeInTheDocument();
    expect(screen.getByText("Regola 29")).toBeInTheDocument();
    expect(screen.queryByText("Regola 13")).not.toBeInTheDocument();
    expect(screen.queryByRole("navigation", { name: "Impaginazione" })).not.toBeInTheDocument();
  });

  it("il filtro per stato mostra solo le regole disattivate", async () => {
    stubApi({ ...BASE_ROUTES, "/rules": makeRules(20, [3, 17]) });
    renderPage();
    await screen.findByText("Regola 01");
    expect(screen.getByText("20 regole (18 attive)")).toBeInTheDocument();

    await userEvent.selectOptions(screen.getByLabelText("Stato"), "inactive");

    const rows = await screen.findAllByRole("listitem");
    expect(rows).toHaveLength(2);
    expect(within(rows[0]).getByText("Regola 03")).toBeInTheDocument();
    expect(within(rows[1]).getByText("Regola 17")).toBeInTheDocument();
  });

  it("senza risultati lo dice e offre di azzerare i filtri", async () => {
    stubApi({ ...BASE_ROUTES, "/rules": makeRules(20) });
    renderPage();
    await screen.findByText("Regola 01");

    await userEvent.type(screen.getByRole("searchbox", { name: "Cerca nelle regole" }), "zzz");
    expect(await screen.findByText("Nessuna regola corrisponde alla ricerca.")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Azzera i filtri" }));
    expect(await screen.findByText("Regola 01")).toBeInTheDocument();
  });

  it("l'azione 'Applica alle transazioni esistenti' sta sopra l'elenco, non in fondo", async () => {
    stubApi({ ...BASE_ROUTES, "/rules": makeRules(30) });
    renderPage();

    const firstRule = await screen.findByText("Regola 01");
    const action = screen.getByRole("button", { name: "Applica alle transazioni esistenti" });

    expect(action.compareDocumentPosition(firstRule) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("con una riclassificazione in corso mostra l'avviso con il link per seguirla in Attività", async () => {
    const running: JobRun = {
      status: "running",
      started_at: "2026-10-24T14:09:00Z",
      finished_at: null,
      message: null,
    };
    stubApi({ ...BASE_ROUTES, "/rules": makeRules(5), "/classification/reclassify/status": running });
    renderPage();

    const banner = await screen.findByRole("status");
    expect(within(banner).getByText("Riclassificazione in corso")).toBeInTheDocument();
    const link = within(banner).getByRole("link", { name: "Segui in Attività" });
    expect(link).toHaveAttribute("href", "/activity");
  });

  it("senza riclassificazioni in corso non mostra nessun avviso", async () => {
    stubApi({ ...BASE_ROUTES, "/rules": makeRules(5) });
    renderPage();

    await screen.findByText("Regola 01");
    await waitFor(() => expect(screen.queryByText("Riclassificazione in corso")).not.toBeInTheDocument());
  });

  it("l'avviso permette di interrompere la riclassificazione in corso", async () => {
    const running: JobRun = {
      status: "running",
      started_at: "2026-10-24T14:09:00Z",
      finished_at: null,
      message: null,
    };
    const fetchMock = stubApi({ ...BASE_ROUTES, "/rules": makeRules(5), "/classification/reclassify/status": running });
    renderPage();

    const banner = await screen.findByRole("status");
    await userEvent.click(within(banner).getByRole("button", { name: "Interrompi" }));

    await waitFor(() => {
      const posted = fetchMock.mock.calls.some(
        ([input, init]) =>
          String(input).endsWith("/classification/reclassify/cancel") && (init as RequestInit | undefined)?.method === "POST",
      );
      expect(posted).toBe(true);
    });
  });
});
