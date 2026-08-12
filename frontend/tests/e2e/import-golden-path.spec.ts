import { expect, test } from "@playwright/test";

// Flow richiesto esplicitamente dalla Definition of Done della milestone
// 06.5 (docs/ROADMAP.md): Login → Accounts → Transactions → Import →
// Processing → Transactions aggiornate. A differenza di
// rules-golden-path.spec.ts e dashboard-golden-path.spec.ts (che passano
// entrambi da /register), qui l'utente viene creato via API e l'accesso
// avviene con un vero LOGIN — l'unico punto della suite e2e che esercita
// LoginPage — e si controllano esplicitamente gli empty state di Conti e
// Movimenti PRIMA dell'import, non solo lo stato finale popolato.

const CSV_CONTENT = [
  "data,descrizione,importo",
  "2026-02-01,Stipendio,1800.00",
  "2026-02-03,Farmacia Centrale,-15.50",
].join("\n");

test("login, empty state di conti/movimenti, import CSV reale e movimenti aggiornati", async ({ page, request }) => {
  const email = `e2e-import-${Date.now()}@example.com`;
  const password = "correct-password-123";

  const registerResponse = await request.post("/api/v1/auth/register", {
    data: { email, password, display_name: "E2E Import" },
  });
  expect(registerResponse.ok()).toBeTruthy();

  // --- Login (non registrazione: l'utente esiste gia' via API) ---
  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Accedi" }).click();
  await expect(page).toHaveURL(/\/accounts$/);

  // --- Accounts: empty state prima di creare il primo conto ---
  await expect(page.getByText("Nessun conto")).toBeVisible();
  await page.getByRole("button", { name: "Aggiungi conto" }).first().click();
  await page.getByLabel("Nome").fill("Conto E2E Import");
  await page.getByRole("button", { name: "Crea conto" }).click();
  await expect(page.getByText("Conto E2E Import")).toBeVisible();

  // --- Transactions: empty state prima di qualunque import ---
  await page.goto("/transactions");
  await expect(page.getByText("Nessun movimento")).toBeVisible();

  // --- Import CSV reale, con progress ---
  await page.goto("/imports");
  await page.getByRole("button", { name: "Importa documento" }).first().click();
  await page.getByLabel("Conto").selectOption({ label: "Conto E2E Import" });
  await page.locator('input[type="file"]').setInputFiles({
    name: "estratto.csv",
    mimeType: "text/csv",
    buffer: Buffer.from(CSV_CONTENT),
  });
  await page.getByRole("button", { name: "Carica" }).click();
  await expect(page.getByRole("button", { name: "Conferma e importa" })).toBeVisible();
  await page.getByRole("button", { name: "Conferma e importa" }).click();

  await expect(page.getByText("Import completato")).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText(/2 movimenti importati/)).toBeVisible();

  // --- Transactions aggiornate: l'empty state e' sparito, i movimenti reali ci sono ---
  await page.getByRole("button", { name: "Visualizza movimenti" }).click();
  await expect(page).toHaveURL(/\/transactions/);
  await expect(page.getByText("Nessun movimento")).not.toBeVisible();
  await expect(page.getByText("Farmacia Centrale").first()).toBeVisible();
  await expect(page.getByText("Stipendio").first()).toBeVisible();
});
