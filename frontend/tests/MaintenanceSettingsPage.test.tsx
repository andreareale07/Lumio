import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { MaintenanceSettingsPage } from "../src/features/settings/maintenance/MaintenanceSettingsPage";
import type { JobRun, PositionsRecomputePreview } from "../src/types/api";

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MaintenanceSettingsPage />
    </QueryClientProvider>,
  );
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

const SAMPLE_CHANGE = {
  asset: "EXAMPLE CORP.",
  account: "Trade Republic",
  currency: "EUR",
  old_quantity: "0.0000000000",
  new_quantity: "0.0000000000",
  old_average_cost: "0.000000",
  new_average_cost: "0.000000",
  old_realized_pl: "999999.99",
  new_realized_pl: "-12.50",
};

const SUCCESS_RUN: JobRun = {
  status: "success",
  started_at: "2026-10-24T10:00:00Z",
  finished_at: "2026-10-24T10:00:05Z",
  message: "1 posizioni aggiornate su 12 controllate.",
  details: { checked: 12, changed: 1, truncated: false, changes: [SAMPLE_CHANGE] },
};

function stubApi(routes: Record<string, unknown>) {
  const fetchMock = vi.fn<typeof fetch>(async (input) => {
    const url = String(input);
    const match = Object.keys(routes).find((path) => url.includes(path));
    return jsonResponse(match ? routes[match] : null);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("MaintenanceSettingsPage", () => {
  it("mostra nel resoconto dell'ultima esecuzione cosa e' stato modificato", async () => {
    stubApi({ "/maintenance/positions-recompute/status": SUCCESS_RUN });
    renderPage();

    expect(await screen.findByText("EXAMPLE CORP.")).toBeInTheDocument();
    expect(screen.getByText("Trade Republic")).toBeInTheDocument();
    expect(screen.getByText(/1 posizioni aggiornate su 12 controllate/)).toBeInTheDocument();
  });

  it("una riesecuzione a vuoto continua a mostrare le ultime modifiche effettive", async () => {
    const emptyRun: JobRun = {
      ...SUCCESS_RUN,
      message: "0 posizioni aggiornate su 12 controllate.",
      details: {
        checked: 12,
        changed: 0,
        truncated: false,
        changes: [],
        previous_changes: { at: "2026-10-24T09:00:00Z", checked: 12, changed: 1, truncated: false, changes: [SAMPLE_CHANGE] },
      },
    };
    stubApi({ "/maintenance/positions-recompute/status": emptyRun });
    renderPage();

    expect(await screen.findByText(/Ultime modifiche effettive/)).toBeInTheDocument();
    expect(screen.getByText("EXAMPLE CORP.")).toBeInTheDocument();
  });

  it("senza esecuzioni precedenti non mostra nessun elenco", async () => {
    stubApi({ "/maintenance/positions-recompute/status": null });
    renderPage();

    expect(await screen.findByText("Ricalcolo posizioni")).toBeInTheDocument();
    expect(screen.queryByText("EXAMPLE CORP.")).not.toBeInTheDocument();
  });

  it("l'anteprima elenca le posizioni che cambierebbero senza avviare il job", async () => {
    const preview: PositionsRecomputePreview = { checked: 12, changed: 1, changes: [SAMPLE_CHANGE] };
    const fetchMock = stubApi({
      "/maintenance/positions-recompute/preview": preview,
      "/maintenance/positions-recompute/status": null,
    });
    renderPage();

    await userEvent.click(await screen.findByRole("button", { name: "Mostra anteprima" }));

    expect(await screen.findByText("EXAMPLE CORP.")).toBeInTheDocument();
    const methods = fetchMock.mock.calls.map(([, init]) => (init as RequestInit | undefined)?.method ?? "GET");
    expect(methods.every((method) => method === "GET")).toBe(true);
  });

  it("'Ricalcola ora' avvia il job con una POST", async () => {
    const fetchMock = stubApi({
      "/maintenance/positions-recompute/status": null,
      "/maintenance/positions-recompute": { job_id: "job-1" },
    });
    renderPage();

    await userEvent.click(await screen.findByRole("button", { name: "Ricalcola ora" }));

    await waitFor(() => {
      const posted = fetchMock.mock.calls.some(
        ([input, init]) =>
          String(input).endsWith("/maintenance/positions-recompute") &&
          (init as RequestInit | undefined)?.method === "POST",
      );
      expect(posted).toBe(true);
    });
  });
});
