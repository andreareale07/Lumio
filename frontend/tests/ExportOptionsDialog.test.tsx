import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ExportOptionsDialog } from "../src/features/settings/integrations/ExportOptionsDialog";
import type { GoogleIntegration } from "../src/types/api";

const INTEGRATION: GoogleIntegration = {
  google_account_email: "me@gmail.com",
  spreadsheet_url: "https://docs.google.com/spreadsheets/d/sheet123",
  drive_folder_name: "Finanze",
  connected_at: "2026-08-01T00:00:00Z",
  last_exported_at: null,
};

function renderDialog() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ExportOptionsDialog open onClose={() => {}} integration={INTEGRATION} />
    </QueryClientProvider>,
  );
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

function mockApi(handlers: Record<string, () => Response>) {
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = typeof input === "string" ? input : String(input);
    const method = (init?.method ?? "GET").toUpperCase();
    for (const [pattern, handler] of Object.entries(handlers)) {
      const [wantMethod, wantPath] = pattern.split(" ");
      if (method === wantMethod && url.endsWith(wantPath)) return handler();
    }
    throw new Error(`Unhandled fetch in test: ${method} ${url}`);
  });
}

describe("ExportOptionsDialog", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("mostra la cartella corrente e un range date precompilato", async () => {
    mockApi({ "GET /integrations/google/export-status": () => jsonResponse(null) });
    renderDialog();

    expect(await screen.findByText("Finanze")).toBeInTheDocument();
    expect((screen.getByLabelText("Dal") as HTMLInputElement).value).not.toBe("");
    expect((screen.getByLabelText("Al") as HTMLInputElement).value).not.toBe("");
  });

  it("invia il payload atteso con il default 'automatico' per il portfolio", async () => {
    const fetchMock = mockApi({
      "GET /integrations/google/export-status": () => jsonResponse(null),
      "POST /integrations/google/export": () => jsonResponse({ job_id: "job-1" }, 202),
      "GET /integrations/google/export-events": () => new Response(null, { status: 200 }),
    });
    const user = userEvent.setup();
    renderDialog();

    await user.click(await screen.findByRole("button", { name: "Esporta" }));

    await waitFor(() =>
      expect(fetchMock.mock.calls.some((call) => String(call[0]).endsWith("/integrations/google/export"))).toBe(
        true,
      ),
    );
    const exportCall = fetchMock.mock.calls.find((call) => String(call[0]).endsWith("/integrations/google/export"));
    const body = JSON.parse(exportCall?.[1]?.body as string);
    expect(body.include_portfolio).toBeNull();
    expect(body.include_charts).toBe(true);
    // Fetta 3 (PLAN_TAXONOMY_I18N.md): la lingua UI corrente viaggia nella
    // richiesta di export — default italiano nei test (locale non forzato).
    expect(body.language).toBe("it");
  });

  it("cambia la scelta del foglio Portfolio in 'Includi sempre'", async () => {
    mockApi({
      "GET /integrations/google/export-status": () => jsonResponse(null),
      "POST /integrations/google/export": () => jsonResponse({ job_id: "job-1" }, 202),
      "GET /integrations/google/export-events": () => new Response(null, { status: 200 }),
    });
    const fetchMock = vi.mocked(globalThis.fetch);
    const user = userEvent.setup();
    renderDialog();

    await user.selectOptions(await screen.findByLabelText("Foglio Portfolio"), "yes");
    await user.click(screen.getByRole("button", { name: "Esporta" }));

    await waitFor(() =>
      expect(fetchMock.mock.calls.some((call) => String(call[0]).endsWith("/integrations/google/export"))).toBe(
        true,
      ),
    );
    const exportCall = fetchMock.mock.calls.find((call) => String(call[0]).endsWith("/integrations/google/export"));
    const body = JSON.parse(exportCall?.[1]?.body as string);
    expect(body.include_portfolio).toBe(true);
  });
});
