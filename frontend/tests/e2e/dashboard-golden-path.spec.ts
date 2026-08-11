import { expect, test } from "@playwright/test";

// Scenario end-to-end della milestone 08 (Dashboard + Analytics), contro
// backend + worker arq reali (docker compose: postgres, redis, app, worker):
// registrazione → conto → import CSV reale → dashboard con KPI corretti →
// stesso numero coerente su piu' pagine → cambio periodo.
//
// L'esclusione dei trasferimenti dal cash flow (SPEC §21/§30) NON e'
// verificabile qui via CSV: l'Import Engine assegna sempre
// transaction_type "expense"/"income" in base al segno (riconoscimento
// transfer solo manuale in questa fase, vedi csv_import.py), quindi una
// riga CSV negativa non diventa mai un transfer. Quella esclusione e' gia'
// coperta da `backend/tests/test_analytics.py::test_summary_excludes_transfers_and_investments`
// con una transazione creata direttamente con transaction_type="transfer".

const CSV_CONTENT = [
  "data,descrizione,importo",
  "2026-08-01,Stipendio,2500.00",
  "2026-08-03,Supermercato Lidl,-45.30",
].join("\n");

test("import reale e KPI dashboard coerenti su piu' pagine", async ({ page }) => {
  const uniqueEmail = `e2e-dashboard-${Date.now()}@example.com`;

  await page.goto("/register");
  await page.getByLabel("Nome").fill("E2E Dashboard");
  await page.getByLabel("Email").fill(uniqueEmail);
  await page.getByLabel("Password").fill("correct-password-123");
  await page.getByRole("button", { name: "Crea account" }).click();
  await expect(page).toHaveURL(/\/accounts$/);

  // Header ed empty-state condividono lo stesso testo finche' non esiste
  // ancora nessun conto (stesso accorgimento di rules-golden-path.spec.ts).
  await page.getByRole("button", { name: "Aggiungi conto" }).first().click();
  await page.getByLabel("Nome").fill("Conto E2E Dashboard");
  await page.getByRole("button", { name: "Crea conto" }).click();
  await expect(page.getByText("Conto E2E Dashboard")).toBeVisible();

  await page.goto("/imports");
  await page.getByRole("button", { name: "Importa documento" }).first().click();
  await page.getByLabel("Conto").selectOption({ label: "Conto E2E Dashboard" });
  await page.locator('input[type="file"]').setInputFiles({
    name: "estratto.csv",
    mimeType: "text/csv",
    buffer: Buffer.from(CSV_CONTENT),
  });
  await page.getByRole("button", { name: "Carica" }).click();
  await expect(page.getByRole("button", { name: "Conferma e importa" })).toBeVisible();
  await page.getByRole("button", { name: "Conferma e importa" }).click();
  await expect(page.getByText("Import completato")).toBeVisible({ timeout: 20_000 });

  // --- Dashboard: periodo esteso a "Ultimi 3 mesi" per includere agosto ---
  await page.goto("/");
  await page.getByLabel("Periodo").selectOption("last_3_months");
  await expect(page).toHaveURL(/period=last_3_months/);

  // Tabella accessibile del grafico Entrate/Uscite (SPEC_FE §59): fonte
  // canonica per asserire i numeri senza ambiguita' con le KPI card, che
  // mostrano gli stessi valori nello stesso formato (quindi ambigue per
  // Playwright in strict mode).
  const cashFlowTable = page.getByRole("table", { name: "Entrate e uscite per mese" });
  await expect(cashFlowTable).toContainText(/2\.?500,00\s*€/);
  await expect(cashFlowTable).toContainText(/45,30\s*€/);

  // --- Movimenti: stessa transazione visibile nella lista completa ---
  await page.goto("/transactions");
  await expect(page.getByText("Supermercato Lidl").first()).toBeVisible();

  // --- Spese: stesso numero, pagina diversa ---
  await page.goto("/expenses");
  await page.getByLabel("Periodo").selectOption("last_3_months");
  await expect(page.getByRole("heading", { name: "Spese" })).toBeVisible();
  await expect(page.getByText(/45,30\s*€/).first()).toBeVisible();
});
