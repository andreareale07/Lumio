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
  // Rework tassonomia: CategoryPicker non e' piu' un `<select>` nativo —
  // il Combobox apre un popover con ricerca, "Streaming" e' raggruppata
  // sotto l'intestazione "Abbonamenti" invece che nella label combinata.
  // Scoped al dialog aperto (come alla riga sotto per la correzione LIDL):
  // senza scoping va in conflitto strict-mode con la checkbox sempre
  // presente di ReclassificationPanel ("...rimaste senza categoria" matcha
  // "Categoria" come sottostringa case-insensitive per Playwright).
  await page.getByRole("dialog").getByLabel("Categoria").click();
  // { exact: true }: "Streaming" e' altrimenti una substring case-insensitive
  // di "Streaming musica" (tassonomia categorie, b33af37) per il matcher di
  // ruolo/nome di Playwright.
  await page.getByRole("option", { name: "Streaming", exact: true }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Crea regola" }).click();
  await expect(page.getByText(/Descrizione contiene "netflix"/)).toBeVisible();

  // --- Import CSV ---
  // Il conto si sceglie DOPO l'upload (non piu' prima) — vedi import-golden-path.spec.ts.
  await page.goto("/imports");
  await page.getByRole("button", { name: "Importa documento" }).first().click();
  await page.locator('input[type="file"]').setInputFiles({
    name: "estratto.csv",
    mimeType: "text/csv",
    buffer: Buffer.from(CSV_CONTENT),
  });
  await page.getByRole("button", { name: "Carica" }).click();
  await page.getByLabel("Oppure scegli un conto esistente").selectOption({ label: "Conto E2E" });
  await page.getByRole("button", { name: "Conferma conto" }).click();

  await expect(page.getByRole("button", { name: "Conferma e importa" })).toBeVisible();
  await page.getByRole("button", { name: "Conferma e importa" }).click();

  await expect(page.getByText("Import completato")).toBeVisible({ timeout: 20_000 });
  // Messaggio rivisto per il Transaction Deduplication Engine (mostra sempre
  // analizzati/nuovi/duplicati/da verificare, non solo "importati").
  await expect(page.getByText(/3 movimenti analizzati/)).toBeVisible();
  await expect(page.getByText(/3 nuovi/)).toBeVisible();
  await page.getByRole("button", { name: "Visualizza movimenti" }).click();

  await expect(page).toHaveURL(/\/transactions/);
  const netflixRow = page.getByRole("row", { name: /NETFLIX/i });
  await expect(netflixRow).toContainText("Streaming");

  // --- Correzione ripetuta sulle due transazioni Lidl -> suggerimento regola ---
  // Il catalogo di pattern deterministico (rifondazione tassonomia, b33af37)
  // classifica gia' automaticamente "LIDL" come Alimentari › Supermercato
  // (`method="system"`, vedi app/classification/catalog.py) — correggerla di
  // nuovo a "Supermercato" sarebbe un no-op (nessuna Classification method=
  // "user" creata, vedi app/api/v1/transactions.py "category_corrected"),
  // quindi non farebbe mai scattare la soglia di correzioni ripetute
  // (SPEC §29). Si sceglie qui una categoria deliberatamente diversa da
  // quella assegnata dal sistema, per generare una VERA correzione utente.
  const lidlRows = page.getByRole("row", { name: /LIDL/i });
  await expect(lidlRows).toHaveCount(2);

  for (let i = 0; i < 2; i++) {
    await lidlRows.nth(i).click();
    await page.getByRole("dialog").getByLabel("Categoria").click();
    await page.getByRole("dialog").getByRole("option", { name: "Bar e caffetteria" }).click();
    await page.keyboard.press("Escape");
  }

  // Il match del suggerimento e' per merchant ("Lidl", estratto da
  // merchant_extraction.py) e non per descrizione, perche' Transaction.merchant
  // e' valorizzato (vedi GET /rules/suggestions: preferisce sempre il merchant
  // quando presente).
  await page.goto("/settings/rules");
  await expect(page.getByText(/Lidl.*2 volte/)).toBeVisible();

  await page.getByRole("button", { name: "Crea regola" }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.getByRole("dialog").getByRole("button", { name: "Crea regola" }).click();

  await expect(page.getByText(/Lidl.*2 volte/)).not.toBeVisible();
});
