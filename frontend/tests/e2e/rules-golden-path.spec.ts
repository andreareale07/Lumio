import { expect, test } from "@playwright/test";

// Scenario principale end-to-end (SPEC_FE §89 "Integration"), contro backend
// + worker arq reali (docker compose: postgres, redis, app, worker — vedi
// istruzioni di verifica del piano): registrazione → conto → regola →
// import CSV → progress reale → transazione auto-classificata → correzione
// ripetuta → suggerimento di regola.

const CSV_CONTENT = [
  "data,descrizione,importo",
  "2026-01-15,Pagamento NETFLIX.COM,-12.99",
  "2026-01-16,Spesa LIDL Milano,-30.00",
  "2026-01-17,Spesa LIDL Milano,-25.00",
].join("\n");

test("registrazione, regola, import CSV reale e suggerimento dopo correzioni ripetute", async ({ page }) => {
  const uniqueEmail = `e2e-${Date.now()}@example.com`;

  await page.goto("/register");
  await page.getByLabel("Nome").fill("E2E Test");
  await page.getByLabel("Email").fill(uniqueEmail);
  await page.getByLabel("Password").fill("correct-password-123");
  await page.getByRole("button", { name: "Crea account" }).click();

  await expect(page).toHaveURL(/\/accounts$/);

  // --- Conto ---
  // Il bottone in header e quello dell'empty state hanno lo stesso testo
  // finche' non esiste ancora nessun conto.
  await page.getByRole("button", { name: "Aggiungi conto" }).first().click();
  await page.getByLabel("Nome").fill("Conto E2E");
  await page.getByRole("button", { name: "Crea conto" }).click();
  await expect(page.getByText("Conto E2E")).toBeVisible();

  // --- Regola (Netflix) creata PRIMA dell'import, cosi' il worker la applica ---
  await page.goto("/settings/rules");
  await page.getByRole("button", { name: "Nuova regola" }).click();
  await page.getByLabel("Nome").fill("Netflix");
  await page.getByLabel("Valore").fill("netflix");
  await page.getByLabel("Categoria").selectOption({ label: "Abbonamenti › Streaming" });
  await page.getByRole("dialog").getByRole("button", { name: "Crea regola" }).click();
  await expect(page.getByText(/Descrizione contiene "netflix"/)).toBeVisible();

  // --- Import CSV ---
  await page.goto("/imports");
  await page.getByRole("button", { name: "Importa documento" }).first().click();
  await page.getByLabel("Conto").selectOption({ label: "Conto E2E" });
  await page.locator('input[type="file"]').setInputFiles({
    name: "estratto.csv",
    mimeType: "text/csv",
    buffer: Buffer.from(CSV_CONTENT),
  });
  await page.getByRole("button", { name: "Carica" }).click();

  await expect(page.getByRole("button", { name: "Conferma e importa" })).toBeVisible();
  await page.getByRole("button", { name: "Conferma e importa" }).click();

  await expect(page.getByText("Import completato")).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText(/3 movimenti importati/)).toBeVisible();
  await page.getByRole("button", { name: "Visualizza movimenti" }).click();

  await expect(page).toHaveURL(/\/transactions/);
  const netflixRow = page.getByRole("row", { name: /NETFLIX/i });
  await expect(netflixRow).toContainText("Streaming");

  // --- Correzione ripetuta sulle due transazioni Lidl -> suggerimento regola ---
  const lidlRows = page.getByRole("row", { name: /LIDL/i });
  await expect(lidlRows).toHaveCount(2);

  for (let i = 0; i < 2; i++) {
    await lidlRows.nth(i).click();
    await page.getByRole("dialog").getByLabel("Categoria").selectOption({ label: "Alimentari › Supermercato" });
    await page.keyboard.press("Escape");
  }

  await page.goto("/settings/rules");
  await expect(page.getByText(/Spesa LIDL Milano.*2 volte/)).toBeVisible();

  await page.getByRole("button", { name: "Crea regola" }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.getByRole("dialog").getByRole("button", { name: "Crea regola" }).click();

  await expect(page.getByText(/Spesa LIDL Milano.*2 volte/)).not.toBeVisible();
});
