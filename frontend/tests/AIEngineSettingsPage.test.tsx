import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AIEngineSettingsPage } from "../src/features/settings/ai-engine/AIEngineSettingsPage";
import { describeEvent, parseDetail } from "../src/features/settings/ai-engine/describeEvent";
import i18n from "../src/app/i18n";
import type { AIEngineStatus, AIRunEvent, AIRunEventList } from "../src/types/api";

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <AIEngineSettingsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

const FAILED_IMPORT = {
  import_id: "imp-1",
  filename: "estratto-marzo.csv",
  completed_at: "2026-10-24T09:00:00Z",
  ai_status: "failed" as const,
  ai_total: 40,
  ai_classified: 0,
  ai_error_message: "Provider AI non raggiungibile, classificazione interrotta",
  uncategorized_eligible: 40,
  can_retry: true,
};

function statusWith(overrides: Partial<AIEngineStatus>): AIEngineStatus {
  return {
    active_profile: { name: "Ollama locale", provider: "ollama", model: "llama3" },
    uncategorized_eligible: 40,
    errors_last_24h: 3,
    last_error_at: "2026-10-24T09:00:00Z",
    recent_imports: [FAILED_IMPORT],
    ...overrides,
  };
}

const EVENT_ERROR: AIRunEvent = {
  id: "ev-1",
  run_kind: "import_classification",
  import_id: "imp-1",
  import_filename: "estratto-marzo.csv",
  severity: "error",
  code: "job_interrupted",
  message: "provider_unreachable",
  created_at: "2026-10-24T09:00:00Z",
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

describe("describeEvent", () => {
  const t = i18n.getFixedT("it", "settings");

  it("legge i dettagli chiave=valore", () => {
    expect(parseDetail("classified=12 no_match=3 total=15")).toEqual({ classified: "12", no_match: "3", total: "15" });
  });

  it("compone una frase tradotta dal codice senza mostrare il codice grezzo", () => {
    expect(describeEvent(t, EVENT_ERROR)).toContain("provider AI non raggiungibile");
    expect(describeEvent(t, { code: "skipped_no_profile", message: "no_active_profile" })).toContain(
      "nessun profilo AI attivo",
    );
    expect(describeEvent(t, { code: "provider_error", message: "ConnectError" })).toContain("ConnectError");
    expect(
      describeEvent(t, { code: "run_completed", message: "classified=12 no_match=3 provider_errors=0 total=15" }),
    ).toContain("12 classificate");
  });

  it("per la riclassificazione usa la frase breve, senza il conteggio mancante", () => {
    const text = describeEvent(t, { code: "run_completed", message: "classified=0 provider_errors=6 total=6" });
    expect(text).toContain("0 classificate, 6 errori del provider (su 6)");
    expect(text).not.toContain("—");
  });

  it("per un codice sconosciuto ricade sul codice e il dettaglio", () => {
    expect(describeEvent(t, { code: "nuovo_codice", message: "x" })).toBe("nuovo_codice: x");
  });
});

describe("AIEngineSettingsPage", () => {
  it("mostra un import fallito con il motivo e permette di rilanciarlo", async () => {
    const fetchMock = stubApi({
      "/ai-engine/status": statusWith({}),
      "/ai-engine/events": { items: [EVENT_ERROR], total: 1 } satisfies AIRunEventList,
      "/classification/reclassify/status": null,
      "/ai-engine/imports/imp-1/retry": { ai_status: "pending", ai_total: 40 },
    });
    renderPage();

    expect(await screen.findByText("estratto-marzo.csv", { selector: "span.text-text" })).toBeInTheDocument();
    expect(screen.getByText("Provider AI non raggiungibile, classificazione interrotta")).toBeInTheDocument();
    expect(await screen.findByText(/Classificazione interrotta: provider AI non raggiungibile/)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Rilancia" }));

    await waitFor(() => {
      const posted = fetchMock.mock.calls.some(
        ([input, init]) =>
          String(input).endsWith("/ai-engine/imports/imp-1/retry") && (init as RequestInit | undefined)?.method === "POST",
      );
      expect(posted).toBe(true);
    });
  });

  it("senza profilo attivo spiega perché l'AI non parte e blocca i rilanci", async () => {
    stubApi({
      "/ai-engine/status": statusWith({
        active_profile: null,
        recent_imports: [{ ...FAILED_IMPORT, ai_status: "skipped", ai_error_message: null, can_retry: false }],
      }),
      "/ai-engine/events": { items: [], total: 0 },
      "/classification/reclassify/status": null,
    });
    renderPage();

    expect(await screen.findByText(/Nessun profilo AI attivo: l'AI non parte/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Classifica ora con l'AI" })).toBeDisabled();
    expect(screen.queryByRole("button", { name: "Rilancia" })).not.toBeInTheDocument();
    expect(await screen.findByText("Nessun evento registrato.")).toBeInTheDocument();
  });

  it("'Classifica ora' avvia la riclassificazione con AI sulle non classificate", async () => {
    const fetchMock = stubApi({
      "/ai-engine/status": statusWith({ recent_imports: [] }),
      "/ai-engine/events": { items: [], total: 0 },
      "/classification/reclassify/status": null,
      "/classification/reclassify": { job_id: "job-1" },
    });
    renderPage();

    await userEvent.click(await screen.findByRole("button", { name: "Classifica ora con l'AI" }));

    await waitFor(() => {
      const call = fetchMock.mock.calls.find(
        ([input, init]) =>
          String(input).endsWith("/classification/reclassify") && (init as RequestInit | undefined)?.method === "POST",
      );
      expect(call).toBeDefined();
      expect(JSON.parse(String((call?.[1] as RequestInit).body))).toEqual({ scope: "uncategorized", run_ai: true });
    });
  });
});
