import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";

import { IntegrationsSettingsPage } from "../src/features/settings/integrations/IntegrationsSettingsPage";

function renderPage(initialEntries: string[] = ["/settings/integrations"]) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={initialEntries}>
        <IntegrationsSettingsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

/** Mock fetch che risponde in base al path, non all'ordine di chiamata: la
 * pagina lancia due query in parallelo (integrazione + stato export), il
 * cui ordine reale di `fetch()` non e' garantito — a differenza delle
 * altre settings page (una sola query), qui una sequenza FIFO sarebbe
 * fragile. */
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

const CONNECTED_INTEGRATION = {
  google_account_email: "me@gmail.com",
  spreadsheet_url: "https://docs.google.com/spreadsheets/d/sheet123",
  drive_folder_name: "Finanze",
  connected_at: "2026-08-01T00:00:00Z",
  last_exported_at: "2026-08-05T10:00:00Z",
};

describe("IntegrationsSettingsPage", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("mostra l'empty state e la guida di setup quando non connesso", async () => {
    mockApi({
      "GET /integrations/google": () => jsonResponse(null),
      "GET /integrations/google/export-status": () => jsonResponse(null),
    });
    renderPage();

    expect(await screen.findByText("Google Sheets")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Connetti" })).toBeInTheDocument();
    expect(screen.getByText(/Prima di connetterti: serve un progetto Google Cloud/)).toBeInTheDocument();
  });

  it("naviga il browser sull'URL di autorizzazione al click su Connetti", async () => {
    mockApi({
      "GET /integrations/google": () => jsonResponse(null),
      "GET /integrations/google/export-status": () => jsonResponse(null),
      "GET /integrations/google/connect": () =>
        jsonResponse({ authorize_url: "https://accounts.google.com/o/oauth2/v2/auth?client_id=x" }),
    });
    // jsdom non permette di spiare `window.location.assign` direttamente
    // (proprietà non ridefinibile): si sostituisce l'intero oggetto `location`.
    const assignMock = vi.fn();
    const originalLocation = window.location;
    Object.defineProperty(window, "location", {
      configurable: true,
      value: { ...originalLocation, assign: assignMock },
    });

    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole("button", { name: "Connetti" }));

    await waitFor(() =>
      expect(assignMock).toHaveBeenCalledWith("https://accounts.google.com/o/oauth2/v2/auth?client_id=x"),
    );

    Object.defineProperty(window, "location", { configurable: true, value: originalLocation });
  });

  it("mostra lo stato connesso con email, spreadsheet e cartella", async () => {
    mockApi({
      "GET /integrations/google": () => jsonResponse(CONNECTED_INTEGRATION),
      "GET /integrations/google/export-status": () => jsonResponse(null),
    });
    renderPage();

    expect(await screen.findByText("Connesso ✓")).toBeInTheDocument();
    expect(screen.getByText("me@gmail.com")).toBeInTheDocument();
    expect(screen.getByText("Cartella: Finanze")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Apri lo spreadsheet/ })).toHaveAttribute(
      "href",
      CONNECTED_INTEGRATION.spreadsheet_url,
    );
  });

  it("mostra il prompt di scelta cartella subito dopo il redirect di connessione", async () => {
    mockApi({
      "GET /integrations/google": () => jsonResponse(CONNECTED_INTEGRATION),
      "GET /integrations/google/export-status": () => jsonResponse(null),
    });
    renderPage(["/settings/integrations?connected=1&step=choose-folder"]);

    expect(await screen.findByText("Dove vuoi salvare il file?")).toBeInTheDocument();

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Nascondi" }));
    expect(screen.queryByText("Dove vuoi salvare il file?")).not.toBeInTheDocument();
  });

  it("mostra il messaggio di errore quando il callback Google fallisce", async () => {
    mockApi({
      "GET /integrations/google": () => jsonResponse(null),
      "GET /integrations/google/export-status": () => jsonResponse(null),
    });
    renderPage(["/settings/integrations?google_error=connection_failed"]);

    expect(
      await screen.findByText("Non è stato possibile completare la connessione con Google. Riprova."),
    ).toBeInTheDocument();
  });

  it("disconnette dopo conferma nel dialog", async () => {
    const fetchMock = mockApi({
      "GET /integrations/google": () => jsonResponse(CONNECTED_INTEGRATION),
      "GET /integrations/google/export-status": () => jsonResponse(null),
      "POST /integrations/google/disconnect": () => new Response(null, { status: 204 }),
    });
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole("button", { name: "Disconnetti" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("Disconnettere Google?")).toBeInTheDocument();

    await user.click(within(dialog).getByRole("button", { name: "Disconnetti" }));

    await waitFor(() =>
      expect(fetchMock.mock.calls.some((call) => (call[1]?.method ?? "GET") === "POST")).toBe(true),
    );
  });
});
