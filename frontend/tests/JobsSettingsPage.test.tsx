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

// `name`/`description`/`schedule_description`/`disable_warning` e le label dei
// parametri arrivano dal backend (app/services/job_registry.py) e restano in
// italiano anche cambiando lingua nel frontend: qui si verificano solo le
// stringhe di cui il frontend è proprietario.
const SCHEDULED_JOB: Job = {
  kind: "fx_refresh",
  category: "scheduled",
  name: "Aggiornamento tassi di cambio",
  description: "Scarica i tassi mancanti verso la valuta di riferimento.",
  schedule_description: "Ogni giorno alle 2:00",
  schedule_readonly_reason: null,
  disable_warning: "I totali in valuta diversa resteranno fermi all'ultimo tasso noto.",
  enabled: true,
  enabled_setting_key: "fx_refresh_enabled",
  parameters: [
    { label: "Soglia di stallo", unit: "minuti", editable: true, setting_key: "fx_stale_minutes", value: 30, readonly_reason: null },
  ],
};

const TRIGGERED_JOB: Job = {
  kind: "import_parse",
  category: "triggered",
  name: "Parsing degli import",
  description: "Legge il file caricato ed estrae i movimenti.",
  schedule_description: null,
  schedule_readonly_reason: null,
  disable_warning: null,
  enabled: null,
  enabled_setting_key: null,
  parameters: [],
};

describe("JobsSettingsPage", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("mostra le due sezioni e le etichette tradotte della card", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(jsonResponse([SCHEDULED_JOB, TRIGGERED_JOB]));
    renderPage();

    expect(await screen.findByText("Job schedulati")).toBeInTheDocument();
    expect(screen.getByText("Job innescati da un'azione")).toBeInTheDocument();
    // Cadenza e stato: interpolazione + scelta della chiave in base a `enabled`.
    expect(screen.getByText("Cadenza: Ogni giorno alle 2:00")).toBeInTheDocument();
    expect(screen.getByText("Attivo")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Disattiva" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Modifica Soglia di stallo" })).toBeInTheDocument();
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

  it("interpola il nome del job nel titolo della conferma di disattivazione", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(jsonResponse([SCHEDULED_JOB]));
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole("button", { name: "Disattiva" }));

    expect(screen.getByRole("dialog")).toHaveTextContent('Disattivare "Aggiornamento tassi di cambio"?');
    expect(screen.getByRole("button", { name: "Annulla" })).toBeInTheDocument();
  });
});
