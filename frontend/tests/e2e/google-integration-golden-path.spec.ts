import { expect, test } from "@playwright/test";

// Milestone 10 — Google Sheets: OAuth reale e Google Picker non sono
// testabili in CI (richiedono credenziali/consenso umano veri), quindi
// backend e widget Picker sono entrambi mockati via intercettazione di
// rete (stesso principio degli altri E2E: login/registrazione reali via
// API, solo la parte che richiederebbe un servizio esterno e' finta).
// Login reale + registrazione via API come import-golden-path.spec.ts, ma
// con `google_enabled` forzato a true nella risposta (il backend reale di
// sviluppo potrebbe girare con GOOGLE_ENABLED=false, il default).

test("connect, scelta cartella, export con progress, cambio cartella e disconnect", async ({ page }) => {
  const email = `e2e-google-${Date.now()}@example.com`;
  const password = "correct-password-123";

  let connected = false;
  let driveFolderName: string | null = null;
  let lastExportedAt: string | null = null;

  // --- google_enabled forzato true (il backend reale di sviluppo puo'
  // girare con GOOGLE_ENABLED=false, il default) — sia sulla risposta di
  // registrazione sia su /auth/me: dopo il redirect OAuth il browser fa
  // una navigazione reale (window.location.assign), quindi l'app si
  // rimonta da zero e richiama /auth/refresh + /auth/me per ripristinare
  // la sessione. ---
  const patchTokenResponse = async (route: import("@playwright/test").Route) => {
    const response = await route.fetch();
    const body = await response.json();
    body.user.google_enabled = true;
    await route.fulfill({ status: response.status(), contentType: "application/json", body: JSON.stringify(body) });
  };
  await page.route("**/api/v1/auth/register", patchTokenResponse);
  await page.route("**/api/v1/auth/login", patchTokenResponse);
  await page.route("**/api/v1/auth/me", async (route) => {
    const response = await route.fetch();
    const body = await response.json();
    body.google_enabled = true;
    await route.fulfill({ status: response.status(), contentType: "application/json", body: JSON.stringify(body) });
  });

  // --- Stato integrazione ---
  await page.route("**/api/v1/integrations/google", async (route) => {
    if (!connected) {
      await route.fulfill({ json: null });
      return;
    }
    await route.fulfill({
      json: {
        google_account_email: "e2e-google@gmail.com",
        spreadsheet_url: "https://docs.google.com/spreadsheets/d/e2e-fake-sheet",
        drive_folder_name: driveFolderName,
        connected_at: new Date().toISOString(),
        last_exported_at: lastExportedAt,
      },
    });
  });

  // --- Connect: l'URL di autorizzazione punta DIRETTAMENTE al nostro
  // callback con un codice fittizio, saltando la vera schermata di consenso
  // Google (fuori dal nostro controllo, non e' quello che questo E2E deve
  // verificare) — una catena di due redirect cross-origin fittizi
  // (localhost -> accounts.google.com fake -> localhost) si e' rivelata
  // inaffidabile con route.fulfill() di Playwright su navigazioni top-level
  // cross-origin: il secondo hop non risultava piu' intercettabile. ---
  await page.route("**/api/v1/integrations/google/connect", async (route) => {
    await route.fulfill({
      json: {
        authorize_url: "http://localhost:5173/api/v1/integrations/google/callback?code=fake-code&state=fake-state",
      },
    });
  });

  // --- Il nostro backend "completa" la connessione ---
  await page.route("**/api/v1/integrations/google/callback**", async (route) => {
    connected = true;
    await route.fulfill({
      status: 302,
      headers: { location: "http://localhost:5173/settings/integrations?connected=1&step=choose-folder" },
    });
  });

  await page.route("**/api/v1/integrations/google/picker-token", async (route) => {
    await route.fulfill({ json: { access_token: "fake-access-token", expires_in_seconds: 3600 } });
  });

  await page.route("**/api/v1/integrations/google/folder", async (route) => {
    const payload = route.request().postDataJSON() as { folder_id: string | null; folder_name: string | null };
    driveFolderName = payload.folder_name;
    await route.fulfill({
      json: {
        google_account_email: "e2e-google@gmail.com",
        spreadsheet_url: "https://docs.google.com/spreadsheets/d/e2e-fake-sheet",
        drive_folder_name: driveFolderName,
        connected_at: new Date().toISOString(),
        last_exported_at: lastExportedAt,
      },
    });
  });

  await page.route("**/api/v1/integrations/google/export", async (route) => {
    await route.fulfill({ status: 202, json: { job_id: "fake-export-job" } });
  });

  await page.route("**/api/v1/integrations/google/export-status", async (route) => {
    if (lastExportedAt) {
      await route.fulfill({
        json: { status: "success", started_at: new Date().toISOString(), finished_at: new Date().toISOString(), message: "Export completato: 4 fogli aggiornati" },
      });
      return;
    }
    await route.fulfill({ json: null });
  });

  // --- Eventi SSE dell'export: un singolo "job.completed" basta a far
  // avanzare il dialog dallo stato "progress" a "done". ---
  await page.route("**/api/v1/integrations/google/export-events", async (route) => {
    lastExportedAt = new Date().toISOString();
    await route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body: 'event: job.completed\ndata: {"event":"job.completed","message":"Export completato: 4 fogli aggiornati"}\n\n',
    });
  });

  await page.route("**/api/v1/integrations/google/disconnect", async (route) => {
    connected = false;
    driveFolderName = null;
    lastExportedAt = null;
    await route.fulfill({ status: 204, body: "" });
  });

  // --- Google Picker: script ufficiale mockato, nessuna chiamata reale ---
  await page.route("**/apis.google.com/js/api.js", async (route) => {
    await route.fulfill({
      contentType: "application/javascript",
      body: `
        window.gapi = { load: (name, opts) => opts.callback() };
        window.google = {
          picker: {
            ViewId: { FOLDERS: "folders" },
            Action: { PICKED: "picked" },
            DocsView: function () {
              this.setSelectFolderEnabled = function () { return this; };
              this.setIncludeFolders = function () { return this; };
            },
            PickerBuilder: function () {
              let cb;
              this.addView = function () { return this; };
              this.setOAuthToken = function () { return this; };
              this.setDeveloperKey = function () { return this; };
              this.setCallback = function (callback) { cb = callback; return this; };
              this.build = function () {
                return { setVisible: function () { cb({ action: "picked", docs: [{ id: "folder-e2e", name: "Finanze E2E" }] }); } };
              };
            },
          },
        };
      `,
    });
  });

  // --- Registrazione + navigazione ---
  await page.request.post("/api/v1/auth/register", { data: { email, password, display_name: "E2E Google" } });
  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Accedi" }).click();
  await expect(page).toHaveURL(/\/accounts$/);

  // --- Voce di menu visibile (google_enabled=true) ---
  await page.getByRole("link", { name: "Integrazioni" }).click();
  await expect(page).toHaveURL(/\/settings\/integrations$/);
  await expect(page.getByText("Prima di connetterti: serve un progetto Google Cloud")).toBeVisible();

  // --- Connect (catena di redirect + reload completo della SPA: piu'
  // lento di una normale navigazione client-side) ---
  await page.getByRole("button", { name: "Connetti" }).click();
  await page.waitForURL(/\/settings\/integrations\?connected=1/, { timeout: 15_000 });
  await expect(page.getByText("Connesso ✓")).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText("Dove vuoi salvare il file?")).toBeVisible();

  // --- Scelta cartella via Picker (mockato) ---
  await page.getByRole("button", { name: "Scegli cartella" }).click();
  await expect(page.getByText("Cartella: Finanze E2E")).toBeVisible();
  await expect(page.getByText("Dove vuoi salvare il file?")).not.toBeVisible();

  // --- Export con progress ---
  await page.getByRole("button", { name: "Esporta" }).click();
  const exportDialog = page.getByRole("dialog");
  await expect(exportDialog).toBeVisible();
  await exportDialog.getByRole("button", { name: "Esporta" }).click();
  await expect(page.getByText("Export completato: 4 fogli aggiornati")).toBeVisible({ timeout: 10_000 });
  // .last(): il bottone "X" di chiusura del Dialog (stesso nome accessibile
  // "Chiudi" via aria-label) precede nel DOM il bottone "Chiudi" del footer.
  await exportDialog.getByRole("button", { name: "Chiudi" }).last().click();

  // --- Disconnect con conferma ---
  await page.getByRole("button", { name: "Disconnetti" }).click();
  const disconnectDialog = page.getByRole("dialog");
  await expect(disconnectDialog.getByText("Disconnettere Google?")).toBeVisible();
  await disconnectDialog.getByRole("button", { name: "Disconnetti" }).click();
  // { exact: true }: "Connetti" e' altrimenti una substring case-insensitive
  // di "Disconnetti" per il matcher di ruolo/nome di Playwright.
  await expect(page.getByRole("button", { name: "Connetti", exact: true })).toBeVisible();
});
