import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { JobsSettingsPage } from "../src/features/settings/jobs/JobsSettingsPage";
import type { Job } from "../src/types/api";

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <JobsSettingsPage />
    </QueryClientProvider>,
  );
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

// Il backend (app/services/job_registry.py) non restituisce piu' testo in
// nessuna lingua per name/description/scheduleDescription/disableWarning/
// label/unit/readonly_reason, solo chiavi i18next stabili nel namespace
// "jobs" (locales/{it,en}/jobs.json) — REWORK DECISION REQUIRED "testo
// backend". Le chiavi qui sotto sono quelle REALI del registro (non
// inventate), cosi' il test verifica anche che la risoluzione i18next
// funzioni davvero, non solo che il componente passi una chiave a t().
const SCHEDULED_JOB: Job = {
  kind: "market_data_refresh",
  category: "scheduled",
  name_key: "marketDataRefresh.name",
  description_key: "marketDataRefresh.description",
  schedule_description_key: "marketDataRefresh.scheduleDescription",
  schedule_readonly_reason_key: "readonlyReason.schedule",
  disable_warning_key: "marketDataRefresh.disableWarning",
  enabled: true,
  enabled_setting_key: "jobs.market_data_refresh.enabled",
  parameters: [
    {
      label_key: "params.staleThreshold",
      unit_key: "units.seconds",
      editable: true,
      setting_key: "job_health.market_data_refresh.stale_after_seconds",
      value: 30,
      readonly_reason_key: null,
    },
  ],
};

const TRIGGERED_JOB: Job = {
  kind: "import",
  category: "triggered",
  name_key: "import.name",
  description_key: "import.description",
  schedule_description_key: null,
  schedule_readonly_reason_key: null,
  disable_warning_key: null,
  enabled: null,
  enabled_setting_key: null,
  parameters: [],
};

describe("JobsSettingsPage", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("mostra le due sezioni e risolve le chiavi i18n della card", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(jsonResponse([SCHEDULED_JOB, TRIGGERED_JOB]));
    renderPage();

    expect(await screen.findByText("Job schedulati")).toBeInTheDocument();
    expect(screen.getByText("Job innescati da un'azione")).toBeInTheDocument();
    // name_key/description_key del job risolti dal namespace "jobs".
    expect(screen.getByText("Refresh prezzi di mercato")).toBeInTheDocument();
    expect(
      screen.getByText("Scarica una quotazione aggiornata per ogni asset con un provider di mercato attivo (per workspace)."),
    ).toBeInTheDocument();
    // Cadenza e stato: interpolazione + scelta della chiave in base a `enabled`.
    expect(screen.getByText("Cadenza: Ogni giorno alle 2:00")).toBeInTheDocument();
    expect(screen.getByText("Attivo")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Disattiva" })).toBeInTheDocument();
    // label_key del parametro risolto dal namespace "jobs".
    expect(screen.getByRole("button", { name: "Modifica Soglia di stallo" })).toBeInTheDocument();
    expect(screen.getByText("Elaborazione import")).toBeInTheDocument();
  });

  it("apre il dialog informativo con i tre paragrafi e l'enfasi al posto giusto", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(jsonResponse([SCHEDULED_JOB]));
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole("button", { name: "Cosa sono le due categorie?" }));

    expect(screen.getByRole("dialog")).toHaveTextContent("Due categorie di job");
    // <Trans>: la frase resta intera e la parte in evidenza è un solo nodo.
    expect(screen.getByText("Il lucchetto")).toHaveClass("font-medium");
    expect(screen.getByRole("dialog")).toHaveTextContent(
      "girano da soli, a intervalli fissi (un cron), indipendentemente da cosa fai nell'app",
    );
    expect(screen.getByRole("dialog")).toHaveTextContent("Qui vedi solo i loro parametri operativi.");
  });

  it("interpola il nome del job (risolto dalla chiave) nel titolo della conferma di disattivazione", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(jsonResponse([SCHEDULED_JOB]));
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole("button", { name: "Disattiva" }));

    expect(screen.getByRole("dialog")).toHaveTextContent('Disattivare "Refresh prezzi di mercato"?');
    expect(screen.getByRole("button", { name: "Annulla" })).toBeInTheDocument();
  });

  it("mostra il motivo di sola lettura risolto per un parametro non editabile", async () => {
    const jobWithReadonlyParam: Job = {
      ...TRIGGERED_JOB,
      parameters: [
        {
          label_key: "params.maxExecutionTimeout",
          unit_key: "units.seconds",
          editable: false,
          setting_key: null,
          value: 120,
          readonly_reason_key: "readonlyReason.timeout",
        },
      ],
    };
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(jsonResponse([jobWithReadonlyParam]));
    renderPage();

    expect(await screen.findByText("Timeout massimo esecuzione")).toBeInTheDocument();
    expect(screen.getByTitle("Richiede il riavvio del worker per avere effetto (letto una sola volta all'avvio).")).toBeInTheDocument();
  });
});
