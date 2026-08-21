import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: true,
  reporter: "list",
  use: {
    baseURL: "http://localhost:5173",
    // Locale deterministico, stesso motivo di `tests/setup.ts` per Vitest
    // (PHASE 3 i18n): senza questo il browser di Playwright espone il
    // proprio `navigator.language` (tipicamente "en-US"), l'app sceglie
    // "en" e ogni assertion in italiano di questi E2E fallirebbe a seconda
    // della macchina su cui girano.
    locale: "it-IT",
  },
  webServer: {
    command: "npm run dev",
    url: "http://localhost:5173",
    reuseExistingServer: !process.env.CI,
    // Milestone 10: chiave fittizia per il widget Google Picker — l'E2E
    // dell'integrazione Google mocka sia il backend sia lo script Picker
    // stesso (nessuna chiamata reale a Google), ma il componente rifiuta
    // di partire del tutto senza questa variabile impostata a build/dev time.
    env: { VITE_GOOGLE_PICKER_API_KEY: "e2e-fake-picker-key" },
  },
});
