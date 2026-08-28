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

  // --- Dashboard: intervallo personalizzato che copre agosto 2026 ---
  // Rework UX/design slice 1: il vecchio preset "Ultimi 3 mesi" e' stato
  // sostituito dal navigatore granularita'+ancora — si usa qui la modalita'
  // "Intervallo personalizzato" con date esplicite (non un preset relativo
  // a "oggi") per restare deterministico rispetto alle date fisse del CSV
  // importato, indipendentemente da quando questo test viene eseguito.
  //
  // PHASE 5b: il navigatore periodo vive ora nel Topbar (viewport desktop
  // di default di Playwright, ≥768px) — la pagina mantiene comunque una
  // seconda copia identica ma nascosta (`md:hidden`) per il fallback
  // mobile, quindi `getByLabel`/`getByRole` senza scope trovano DUE
  // elementi con lo stesso accessible name e Playwright fallisce in strict
  // mode. Si scopa esplicitamente a `header` (il Topbar), che e' anche la
  // copia realmente visibile in questo viewport.
  const topbar = page.locator("header");
  await page.goto("/");
  await topbar.getByRole("button", { name: "Intervallo personalizzato" }).click();
  await topbar.getByLabel("Dal", { exact: true }).fill("2026-07-01");
  await topbar.getByLabel("Al", { exact: true }).fill("2026-09-30");
  await expect(page).toHaveURL(/mode=custom/);

  // Tabella accessibile del grafico Entrate/Uscite (SPEC_FE §59): fonte
  // canonica per asserire i numeri senza ambiguita' con le KPI card, che
  // mostrano gli stessi valori nello stesso formato (quindi ambigue per
  // Playwright in strict mode).
  const cashFlowTable = page.getByRole("table", { name: "Entrate e uscite per mese" });
  await expect(cashFlowTable).toContainText(/2\.?500,00\s*€/);
  await expect(cashFlowTable).toContainText(/45,30\s*€/);

  // --- Navigazione avanti/indietro: stesso dato raggiungibile spostandosi
  // di un mese alla volta, non solo con un range libero --- si parte da
  // settembre 2026 (via URL, per non dipendere dalla data reale di
  // esecuzione del test) e si torna indietro di un mese fino ad agosto.
  await page.goto("/?mode=granular&granularity=month&anchor=2026-09-01");
  await topbar.getByRole("button", { name: "Periodo precedente" }).click();
  await expect(page).toHaveURL(/anchor=2026-08-01/);
  await expect(cashFlowTable).toContainText(/2\.?500,00\s*€/);

  // --- Movimenti: stessa transazione visibile nella lista completa ---
  // La tabella mostra il merchant estratto ("Lidl", da merchant_aliases.py)
  // invece della descrizione grezza quando disponibile (Transaction.merchant,
  // pattern gia' esistente in TransactionsPage.tsx dalla milestone M01-M06,
  // rimasto dormiente finche' `merchant_extraction.py` non l'ha popolato) —
  // `description_raw` ("Supermercato Lidl") resta intatto e visibile nel
  // drawer di dettaglio, qui si verifica solo la riga in tabella.
  await page.goto("/transactions");
  await expect(page.getByText("Lidl").first()).toBeVisible();

  // --- Spese: stesso numero, pagina diversa, stesso intervallo personalizzato ---
  await page.goto("/expenses");
  await topbar.getByRole("button", { name: "Intervallo personalizzato" }).click();
  await topbar.getByLabel("Dal", { exact: true }).fill("2026-07-01");
  await topbar.getByLabel("Al", { exact: true }).fill("2026-09-30");
  await expect(page.getByRole("heading", { name: "Spese" })).toBeVisible();
  await expect(page.getByText(/45,30\s*€/).first()).toBeVisible();
});
