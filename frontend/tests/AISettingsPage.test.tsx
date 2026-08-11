import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AISettingsPage } from "../src/features/settings/ai/AISettingsPage";

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <AISettingsPage />
    </QueryClientProvider>,
  );
}

function mockFetchSequence(...responses: Response[]) {
  const fetchMock = vi.spyOn(globalThis, "fetch");
  responses.forEach((response) => fetchMock.mockResolvedValueOnce(response));
  return fetchMock;
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

const OLLAMA_PROFILE = {
  id: "p1",
  name: "Ollama locale",
  provider: "ollama",
  endpoint: "http://ollama:11434",
  model: "gemma3:4b",
  api_key_set: false,
  is_active: true,
  created_at: "2026-08-01T00:00:00Z",
  updated_at: "2026-08-01T00:00:00Z",
};

describe("AISettingsPage", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("mostra l'empty state quando non ci sono profili", async () => {
    mockFetchSequence(jsonResponse([]));
    renderPage();

    expect(await screen.findByText("Nessun profilo AI")).toBeInTheDocument();
  });

  it("mostra i profili esistenti con lo stato attivo", async () => {
    mockFetchSequence(jsonResponse([OLLAMA_PROFILE]));
    renderPage();

    expect(await screen.findByText("Ollama locale")).toBeInTheDocument();
    expect(screen.getByText("Attivo")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Disattiva" })).toBeInTheDocument();
  });

  it("apre il dialog di creazione con il provider selezionabile", async () => {
    mockFetchSequence(jsonResponse([]));
    const user = userEvent.setup();
    renderPage();

    await screen.findByText("Nessun profilo AI");
    await user.click(screen.getAllByRole("button", { name: "Nuovo profilo" })[0]);

    expect(await screen.findByLabelText("Nome")).toBeInTheDocument();
    const providerSelect = screen.getByLabelText("Provider") as HTMLSelectElement;
    expect(providerSelect).not.toBeDisabled();
  });

  it("richiede una API key per creare un profilo OpenAI", async () => {
    mockFetchSequence(jsonResponse([]));
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getAllByRole("button", { name: "Nuovo profilo" })[0]);
    await user.type(await screen.findByLabelText("Nome"), "OpenAI prod");
    await user.selectOptions(screen.getByLabelText("Provider"), "openai");
    await user.click(screen.getByRole("button", { name: "Crea profilo" }));

    expect(await screen.findByText("Inserisci una API key")).toBeInTheDocument();
  });

  it("crea un profilo Ollama valido e invia il payload atteso", async () => {
    const created = { ...OLLAMA_PROFILE, is_active: false };
    const fetchMock = mockFetchSequence(jsonResponse([]), jsonResponse(created, 201), jsonResponse([created]));
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getAllByRole("button", { name: "Nuovo profilo" })[0]);
    await user.type(await screen.findByLabelText("Nome"), "Ollama locale");
    await user.type(screen.getByLabelText("Endpoint"), "http://ollama:11434");
    await user.type(screen.getByLabelText("Modello"), "gemma3:4b");
    await user.click(screen.getByRole("button", { name: "Crea profilo" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
    const [url, options] = fetchMock.mock.calls[1];
    expect(url).toContain("/settings/ai/profiles");
    expect(options?.method).toBe("POST");
    const body = JSON.parse(options?.body as string);
    expect(body).toEqual({
      name: "Ollama locale",
      provider: "ollama",
      endpoint: "http://ollama:11434",
      model: "gemma3:4b",
    });
  });

  it("permette di aggiornare l'elenco modelli prima di aver scelto un modello", async () => {
    const fetchMock = mockFetchSequence(
      jsonResponse([]),
      jsonResponse({ success: true, models: ["gemma3:4b", "llama3.1:8b"], message: "2 modelli trovati." }),
    );
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getAllByRole("button", { name: "Nuovo profilo" })[0]);
    await user.type(await screen.findByLabelText("Endpoint"), "http://ollama:11434");
    // Nessun modello ancora scelto: "Aggiorna elenco" non deve bloccarsi
    // sulla validazione "Inserisci il modello" (regressione: in una prima
    // versione il click passava per handleSubmit, che valida l'intero
    // form prima di lasciare partire la richiesta).
    await user.click(screen.getByRole("button", { name: "Aggiorna elenco" }));

    expect(await screen.findByText("2 modelli trovati.")).toBeInTheDocument();
    expect(screen.queryByText("Inserisci il modello")).not.toBeInTheDocument();
    const [url] = fetchMock.mock.calls[1];
    expect(url).toContain("/settings/ai/models");
  });

  it("nel dialog di modifica il provider non è selezionabile", async () => {
    mockFetchSequence(jsonResponse([OLLAMA_PROFILE]));
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole("button", { name: "Modifica" }));

    const providerSelect = await screen.findByLabelText("Provider");
    expect(providerSelect).toBeDisabled();
  });

  it("attiva un profilo non attivo", async () => {
    const inactiveProfile = { ...OLLAMA_PROFILE, is_active: false };
    const fetchMock = mockFetchSequence(
      jsonResponse([inactiveProfile]),
      jsonResponse({ ...inactiveProfile, is_active: true }),
      jsonResponse([{ ...inactiveProfile, is_active: true }]),
    );
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole("button", { name: "Attiva" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
    const [url, options] = fetchMock.mock.calls[1];
    expect(url).toContain(`/settings/ai/profiles/${inactiveProfile.id}/activate`);
    expect(options?.method).toBe("POST");
  });
});
