import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";

import { OpenBankingSettingsPage } from "../src/features/settings/open-banking/OpenBankingSettingsPage";

function renderPage(initialEntries: string[] = ["/settings/bank-connections"]) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={initialEntries}>
        <OpenBankingSettingsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

/** Risponde in base a metodo e percorso (non all'ordine di chiamata): la pagina
 * lancia piu' query in parallelo. Le richieste con metodo diverso da GET sono
 * tracciate per verificarne il corpo. */
function mockApi(handlers: Record<string, (body: unknown) => Response>) {
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = typeof input === "string" ? input : String(input);
    const method = (init?.method ?? "GET").toUpperCase();
    for (const [pattern, handler] of Object.entries(handlers)) {
      const [wantMethod, wantPath] = pattern.split(" ");
      if (method === wantMethod && url.endsWith(wantPath)) {
        return handler(typeof init?.body === "string" ? JSON.parse(init.body) : undefined);
      }
    }
    throw new Error(`Unhandled fetch in test: ${method} ${url}`);
  });
}

const CERT = "-----BEGIN CERTIFICATE-----\nMIIBsynthetic\n-----END CERTIFICATE-----\n";
const REDIRECT = "https://lumio.example/api/v1/open-banking/callback";

const credential = (configured: boolean) => ({
  provider: "enable_banking",
  configured,
  application_id: configured ? "app-id-synthetic-0001" : null,
  certificate_pem: CERT,
  created_at: "2026-11-06T10:00:00Z",
});

const status = (cred: ReturnType<typeof credential> | null, redirectConfigured = true) => ({
  redirect_uri: redirectConfigured ? REDIRECT : "",
  redirect_uri_configured: redirectConfigured,
  credential: cred,
});

const ACCOUNT_MAPPED = {
  id: "a1",
  name: "Conto Corrente",
  product: null,
  iban_masked: "IT60••••3456",
  currency: "EUR",
  enabled: true,
  financial_account_id: "f1",
  last_sync_at: "2026-11-05T08:00:00Z",
  transactions_imported: 42,
};
const ACCOUNT_UNMAPPED = {
  id: "a2",
  name: "Carta Prepagata",
  product: null,
  iban_masked: "IT28••••1208",
  currency: "EUR",
  enabled: false,
  financial_account_id: null,
  last_sync_at: null,
  transactions_imported: 0,
};

const connection = (overrides: Record<string, unknown> = {}) => ({
  id: "c1",
  aspsp_name: "Banca Test",
  aspsp_country: "IT",
  status: "active",
  valid_until: "2027-03-01T00:00:00Z",
  days_until_expiry: 120,
  expiring_soon: false,
  last_sync_at: "2026-11-05T08:00:00Z",
  last_error: null,
  sync_running: false,
  accounts: [ACCOUNT_MAPPED, ACCOUNT_UNMAPPED],
  ...overrides,
});

function stubLocationAssign() {
  const assignMock = vi.fn();
  const originalLocation = window.location;
  Object.defineProperty(window, "location", { configurable: true, value: { ...originalLocation, assign: assignMock } });
  return { assignMock, restore: () => Object.defineProperty(window, "location", { configurable: true, value: originalLocation }) };
}

describe("OpenBankingSettingsPage", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("senza credenziali guida la configurazione dal passo 1 e non offre ancora di collegare una banca", async () => {
    mockApi({
      "GET /open-banking": () => jsonResponse(status(null)),
      "GET /open-banking/connections": () => jsonResponse([]),
    });
    renderPage();

    expect(await screen.findByText("Passo 1 di 3")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Genera certificato" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Collega una banca" })).not.toBeInTheDocument();
    expect(screen.getByText(/Il servizio gratuito di Enable Banking è per uso personale/)).toBeInTheDocument();
  });

  it("genera il certificato e lo mostra (mai la chiave privata)", async () => {
    let generated = false;
    mockApi({
      "GET /open-banking": () => jsonResponse(status(generated ? credential(false) : null)),
      "GET /open-banking/connections": () => jsonResponse([]),
      "POST /open-banking/credentials": () => {
        generated = true;
        return jsonResponse(credential(false), 201);
      },
    });
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole("button", { name: "Genera certificato" }));

    const certificate = await screen.findByLabelText("Certificato (parte pubblica)");
    expect((certificate as HTMLTextAreaElement).value).toContain("BEGIN CERTIFICATE");
    expect(document.body.textContent).not.toContain("PRIVATE KEY");
    // Il passo 2 (una schermata per passo) mostra l'indirizzo di ritorno da registrare, identico a quello del server.
    await user.click(screen.getByRole("button", { name: "Avanti" }));
    expect(await screen.findByText("Passo 2 di 3")).toBeInTheDocument();
    expect(screen.getByText(REDIRECT)).toBeInTheDocument();
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "2");
  });

  it("valida l'application ID prima di salvarlo e poi lo invia al server", async () => {
    const put = vi.fn(() => jsonResponse(credential(true)));
    mockApi({
      "GET /open-banking": () => jsonResponse(status(credential(false))),
      "GET /open-banking/connections": () => jsonResponse([]),
      "PUT /open-banking/credentials/application-id": put,
    });
    const user = userEvent.setup();
    renderPage();

    // Il certificato esiste gia': si riparte dal passo 2 e si arriva al 3 con "Fatto, avanti".
    expect(await screen.findByText("Passo 2 di 3")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Fatto, avanti" }));
    const input = await screen.findByLabelText("Application ID");
    await user.type(input, "no good!");
    await user.click(screen.getByRole("button", { name: "Salva" }));
    expect(await screen.findByText(/L'ID non sembra valido/)).toBeInTheDocument();
    expect(put).not.toHaveBeenCalled();

    await user.clear(input);
    await user.type(input, "app-id-synthetic-0001");
    await user.click(screen.getByRole("button", { name: "Salva" }));
    await waitFor(() => expect(put).toHaveBeenCalledWith({ application_id: "app-id-synthetic-0001" }));
  });

  it("si puo' tornare indietro tra i passi senza perdere il contesto", async () => {
    mockApi({
      "GET /open-banking": () => jsonResponse(status(credential(false))),
      "GET /open-banking/connections": () => jsonResponse([]),
    });
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole("button", { name: "Fatto, avanti" }));
    expect(await screen.findByText("Passo 3 di 3")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Indietro" }));
    expect(await screen.findByText("Passo 2 di 3")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Indietro" }));
    expect(await screen.findByText("Passo 1 di 3")).toBeInTheDocument();
    expect(screen.getByLabelText("Certificato (parte pubblica)")).toBeInTheDocument();
  });

  it("avvisa se l'indirizzo di ritorno non e' configurato sul server", async () => {
    mockApi({
      "GET /open-banking": () => jsonResponse(status(credential(true), false)),
      "GET /open-banking/connections": () => jsonResponse([]),
    });
    renderPage();
    expect(await screen.findByText("Indirizzo di ritorno non configurato")).toBeInTheDocument();
    expect(screen.getByText(/OPEN_BANKING_REDIRECT_URI/)).toBeInTheDocument();
  });

  it("configurato e senza banche: empty state con l'azione per collegarne una", async () => {
    mockApi({
      "GET /open-banking": () => jsonResponse(status(credential(true))),
      "GET /open-banking/connections": () => jsonResponse([]),
    });
    renderPage();
    expect(await screen.findByText("Nessuna banca collegata")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Collega una banca" }).length).toBeGreaterThan(0);
  });

  it("cerca la banca per nome e porta il browser sul sito della banca dopo il riepilogo", async () => {
    const start = vi.fn(() => jsonResponse({ authorize_url: "https://bank.example/auth?s=1" }));
    mockApi({
      "GET /open-banking": () => jsonResponse(status(credential(true))),
      "GET /open-banking/connections": () => jsonResponse([]),
      "GET /open-banking/institutions?country=IT": () =>
        jsonResponse([
          { name: "Banca Alfa", country: "IT", logo_url: null, beta: false, maximum_consent_validity_days: 180 },
          { name: "Banca Beta", country: "IT", logo_url: null, beta: true, maximum_consent_validity_days: 90 },
        ]),
      "POST /open-banking/connections": start,
    });
    const { assignMock, restore } = stubLocationAssign();
    const user = userEvent.setup();
    renderPage();

    await user.click((await screen.findAllByRole("button", { name: "Collega una banca" }))[0]);
    const dialog = await screen.findByRole("dialog");
    expect(await within(dialog).findByText("Banca Alfa")).toBeInTheDocument();
    expect(within(dialog).getByText("2 banche disponibili")).toBeInTheDocument();

    await user.type(within(dialog).getByLabelText("Cerca la tua banca"), "beta");
    expect(within(dialog).queryByText("Banca Alfa")).not.toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: /Banca Beta/ }));

    // Riepilogo prima di lasciare Lumio: nessuna credenziale in Lumio, sola lettura, durata del consenso, revoca.
    expect(await within(dialog).findByText(/Lumio non le vede mai/)).toBeInTheDocument();
    expect(within(dialog).getByText(/sola lettura/)).toBeInTheDocument();
    expect(within(dialog).getByText(/al massimo 90 giorni/)).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "Vai alla banca" }));

    await waitFor(() => expect(assignMock).toHaveBeenCalledWith("https://bank.example/auth?s=1"));
    expect(start).toHaveBeenCalledWith({ aspsp_name: "Banca Beta", aspsp_country: "IT", psu_type: "personal" });
    restore();
  });

  it("mostra la banca collegata con stato, conti, ultima sincronizzazione e conteggio importati", async () => {
    mockApi({
      "GET /open-banking": () => jsonResponse(status(credential(true))),
      "GET /open-banking/connections": () => jsonResponse([connection()]),
    });
    renderPage();

    expect(await screen.findByText("Banca Test")).toBeInTheDocument();
    // Una sola riga di stato sotto il nome: icona + testo, non solo colore.
    expect(screen.getByText(/^Aggiornata /)).toBeInTheDocument();
    expect(screen.getByText("Conto Corrente")).toBeInTheDocument();
    expect(screen.getByText("42 movimenti importati")).toBeInTheDocument();
    expect(screen.getByText(/Ultima sincronizzazione:/)).toBeInTheDocument();
    expect(screen.getByText(/giorni rimasti/)).toBeInTheDocument();
    // Lo stato dell'importazione e' un interruttore accessibile con testo, non solo colore.
    expect(screen.getByRole("switch", { name: "Importazione attiva" })).toBeChecked();
    expect(screen.getByRole("button", { name: "Importa questo conto" })).toBeInTheDocument();
  });

  it("con piu' banche l'elenco e' compatto: si apre da sola solo quella che richiede un rinnovo", async () => {
    mockApi({
      "GET /open-banking": () => jsonResponse(status(credential(true))),
      "GET /open-banking/connections": () =>
        jsonResponse([
          connection({ id: "c1", aspsp_name: "Banca Alfa" }),
          connection({ id: "c2", aspsp_name: "Banca Beta", expiring_soon: true, days_until_expiry: 2 }),
        ]),
    });
    const user = userEvent.setup();
    renderPage();

    const alfa = await screen.findByRole("button", { name: /Banca Alfa/ });
    const beta = screen.getByRole("button", { name: /Banca Beta/ });
    expect(alfa).toHaveAttribute("aria-expanded", "false");
    expect(beta).toHaveAttribute("aria-expanded", "true");
    expect(screen.getAllByRole("button", { name: "Sincronizza ora" })).toHaveLength(1);

    await user.click(alfa);
    expect(alfa).toHaveAttribute("aria-expanded", "true");
    expect(screen.getAllByRole("button", { name: "Sincronizza ora" })).toHaveLength(2);
  });

  it("sincronizza ora: accoda il job e mostra l'avanzamento", async () => {
    const sync = vi.fn(() => jsonResponse({ status: "queued" }, 202));
    mockApi({
      "GET /open-banking": () => jsonResponse(status(credential(true))),
      "GET /open-banking/connections": () => jsonResponse([connection()]),
      "POST /open-banking/connections/c1/sync": sync,
    });
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole("button", { name: "Sincronizza ora" }));

    await waitFor(() => expect(sync).toHaveBeenCalled());
    expect(await screen.findByText("Sincronizzazione in corso…")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sincronizza ora" })).toBeDisabled();
  });

  it("senza conti attivi la sincronizzazione e' disabilitata e dice perche'", async () => {
    mockApi({
      "GET /open-banking": () => jsonResponse(status(credential(true))),
      "GET /open-banking/connections": () => jsonResponse([connection({ accounts: [ACCOUNT_UNMAPPED] })]),
    });
    renderPage();

    expect(await screen.findByRole("button", { name: "Sincronizza ora" })).toBeDisabled();
    expect(screen.getByText("Attiva almeno un conto per poter sincronizzare.")).toBeInTheDocument();
    expect(screen.getByText("Scegli quali conti importare in Lumio.")).toBeInTheDocument();
  });

  it("abbina un conto della banca a un nuovo conto Lumio e ne attiva l'importazione", async () => {
    const patch = vi.fn(() => jsonResponse({ ...ACCOUNT_UNMAPPED, financial_account_id: "f9", enabled: true }));
    mockApi({
      "GET /open-banking": () => jsonResponse(status(credential(true))),
      "GET /open-banking/connections": () => jsonResponse([connection()]),
      "GET /accounts": () => jsonResponse([{ id: "f1", name: "Principale", currency: "EUR" }]),
      "PATCH /open-banking/connections/c1/accounts/a2": patch,
    });
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole("button", { name: "Importa questo conto" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByRole("option", { name: "Crea un nuovo conto" })).toBeInTheDocument();
    expect(within(dialog).getByRole("option", { name: "Principale (EUR)" })).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "Importa" }));

    await waitFor(() => expect(patch).toHaveBeenCalledTimes(2));
    expect(patch).toHaveBeenNthCalledWith(1, { create_account: true });
    expect(patch).toHaveBeenNthCalledWith(2, { enabled: true });
  });

  it("l'autorizzazione in scadenza mostra un avviso e il rinnovo riparte dalla stessa banca", async () => {
    const start = vi.fn(() => jsonResponse({ authorize_url: "https://bank.example/renew" }));
    mockApi({
      "GET /open-banking": () => jsonResponse(status(credential(true))),
      "GET /open-banking/connections": () =>
        jsonResponse([connection({ expiring_soon: true, days_until_expiry: 3 })]),
      "POST /open-banking/connections": start,
    });
    const { assignMock, restore } = stubLocationAssign();
    const user = userEvent.setup();
    renderPage();

    // La riga di stato diventa il pulsante per agire.
    expect(await screen.findByText("Scade tra 3 giorni")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Rinnova autorizzazione" }));

    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("Collega Banca Test")).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "Vai alla banca" }));
    await waitFor(() => expect(assignMock).toHaveBeenCalledWith("https://bank.example/renew"));
    expect(start).toHaveBeenCalledWith({ aspsp_name: "Banca Test", aspsp_country: "IT", psu_type: "personal" });
    restore();
  });

  it("un'autorizzazione scaduta non offre la sincronizzazione ma solo il rinnovo", async () => {
    mockApi({
      "GET /open-banking": () => jsonResponse(status(credential(true))),
      "GET /open-banking/connections": () => jsonResponse([connection({ status: "expired", days_until_expiry: -2 })]),
    });
    renderPage();

    expect(await screen.findByText("Autorizzazione scaduta")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Sincronizza ora" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Rinnova autorizzazione" })).toBeInTheDocument();
  });

  it("traduce l'ultimo errore di sincronizzazione senza mostrare il codice tecnico", async () => {
    mockApi({
      "GET /open-banking": () => jsonResponse(status(credential(true))),
      "GET /open-banking/connections": () => jsonResponse([connection({ last_error: "rate_limited" })]),
    });
    renderPage();
    expect(await screen.findByText(/La banca ha limitato le richieste/)).toBeInTheDocument();
    expect(screen.queryByText("rate_limited")).not.toBeInTheDocument();
  });

  it("un errore di sincronizzazione appare nella riga di stato con l'azione Riprova", async () => {
    const sync = vi.fn(() => jsonResponse({ status: "queued" }, 202));
    mockApi({
      "GET /open-banking": () => jsonResponse(status(credential(true))),
      "GET /open-banking/connections": () => jsonResponse([connection({ last_error: "rate_limited" })]),
      "POST /open-banking/connections/c1/sync": sync,
    });
    const user = userEvent.setup();
    renderPage();

    const retry = await screen.findByRole("button", { name: /Limite della banca/ });
    await user.click(retry);
    await waitFor(() => expect(sync).toHaveBeenCalled());
  });

  it("scollega mostrando l'impatto: di default i movimenti restano, con pari evidenza tra le due scelte", async () => {
    const remove = vi.fn(() => jsonResponse({ deleted_transactions: 0, revoked_at_bank: true }));
    mockApi({
      "GET /open-banking": () => jsonResponse(status(credential(true))),
      "GET /open-banking/connections": () => jsonResponse([connection()]),
      "DELETE /open-banking/connections/c1": remove,
    });
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole("button", { name: "Scollega" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("Scollegare Banca Test?")).toBeInTheDocument();
    expect(within(dialog).getByText(/L'autorizzazione viene revocata presso la banca/)).toBeInTheDocument();
    expect(within(dialog).getByText("42 movimenti già importati restano in Lumio.")).toBeInTheDocument();
    expect(within(dialog).getByRole("checkbox", { name: /Elimina anche i movimenti importati/ })).not.toBeChecked();
    expect(within(dialog).getByRole("button", { name: "Annulla" })).toBeInTheDocument();
    expect(remove).not.toHaveBeenCalled();

    await user.click(within(dialog).getByRole("button", { name: "Scollega" }));
    await waitFor(() => expect(remove).toHaveBeenCalled());
    expect(await screen.findByText("Banca Test scollegata.")).toBeInTheDocument();
  });

  it("con la casella attiva avvisa che e' irreversibile e chiede di eliminare anche i movimenti", async () => {
    const urls: string[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      const method = (init?.method ?? "GET").toUpperCase();
      if (method === "DELETE") {
        urls.push(url);
        return jsonResponse({ deleted_transactions: 42, revoked_at_bank: false });
      }
      if (url.endsWith("/open-banking/connections")) return jsonResponse([connection()]);
      return jsonResponse(status(credential(true)));
    });
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole("button", { name: "Scollega" }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("checkbox", { name: /Elimina anche i movimenti importati/ }));

    expect(within(dialog).getByText("42 movimenti importati da questa banca verranno eliminati.")).toBeInTheDocument();
    expect(within(dialog).getByText(/Non si può annullare/)).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "Scollega ed elimina" }));

    await waitFor(() => expect(urls).toEqual([expect.stringContaining("/open-banking/connections/c1?delete_data=true")]));
    const notice = await screen.findByRole("status");
    expect(notice).toHaveTextContent("Banca Test scollegata. 42 movimenti eliminati.");
    expect(notice).toHaveTextContent("revocare il consenso presso la banca");
  });

  it("se lo scollegamento viene rifiutato il foglio resta aperto con il motivo", async () => {
    mockApi({
      "GET /open-banking": () => jsonResponse(status(credential(true))),
      "GET /open-banking/connections": () => jsonResponse([connection()]),
      "DELETE /open-banking/connections/c1?delete_data=true": () =>
        jsonResponse({ detail: "Importazione in corso: attendi il completamento prima di eliminare i movimenti" }, 409),
    });
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole("button", { name: "Scollega" }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("checkbox", { name: /Elimina anche i movimenti importati/ }));
    await user.click(within(dialog).getByRole("button", { name: "Scollega ed elimina" }));

    expect(await within(dialog).findByRole("alert")).toHaveTextContent("Importazione in corso");
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("al ritorno dalla banca mostra l'esito: successo e errore", async () => {
    mockApi({
      "GET /open-banking": () => jsonResponse(status(credential(true))),
      "GET /open-banking/connections": () => jsonResponse([connection()]),
    });
    const { unmount } = renderPage(["/settings/bank-connections?connected=c1"]);
    expect(await screen.findByText(/Banca collegata\. Ora scegli quali conti importare/)).toBeInTheDocument();
    unmount();

    renderPage(["/settings/bank-connections?error=authorization_denied"]);
    expect(await screen.findByText(/annullato o negato dalla banca/)).toBeInTheDocument();
  });

  it("errore di caricamento: messaggio con possibilita' di riprovare", async () => {
    mockApi({
      "GET /open-banking": () => jsonResponse({ detail: "boom" }, 500),
      "GET /open-banking/connections": () => jsonResponse([]),
    });
    renderPage();
    expect(await screen.findByText("Non siamo riusciti a caricare lo stato dei conti bancari.")).toBeInTheDocument();
  });
});
