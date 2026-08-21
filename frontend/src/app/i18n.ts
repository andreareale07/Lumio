import i18n from "i18next";
import { initReactI18next } from "react-i18next";

import accountsEn from "../locales/en/accounts.json";
import categoriesEn from "../locales/en/categories.json";
import commonEn from "../locales/en/common.json";
import dashboardEn from "../locales/en/dashboard.json";
import enumsEn from "../locales/en/enums.json";
import importsEn from "../locales/en/imports.json";
import jobsEn from "../locales/en/jobs.json";
import navigationEn from "../locales/en/navigation.json";
import portfolioEn from "../locales/en/portfolio.json";
import rulesEn from "../locales/en/rules.json";
import transactionsEn from "../locales/en/transactions.json";
import settingsEn from "../locales/en/settings.json";
import accountsIt from "../locales/it/accounts.json";
import categoriesIt from "../locales/it/categories.json";
import commonIt from "../locales/it/common.json";
import dashboardIt from "../locales/it/dashboard.json";
import enumsIt from "../locales/it/enums.json";
import importsIt from "../locales/it/imports.json";
import jobsIt from "../locales/it/jobs.json";
import navigationIt from "../locales/it/navigation.json";
import portfolioIt from "../locales/it/portfolio.json";
import rulesIt from "../locales/it/rules.json";
import transactionsIt from "../locales/it/transactions.json";
import settingsIt from "../locales/it/settings.json";

// Fondamenta i18n (SPEC_FE_REDESIGN §22-32, PHASE 3): SOLO l'infrastruttura
// + il primo caso reale migrato (Navigation/Settings Hub, stessa priorita'
// indicata dallo spec per la migrazione completa in PHASE 4). Nessuna
// libreria i18n esisteva prima in questo repo (verificato nell'audit).
export const SUPPORTED_LOCALES = ["it", "en"] as const;
export type SupportedLocale = (typeof SUPPORTED_LOCALES)[number];
export const DEFAULT_LOCALE: SupportedLocale = "it";

const STORAGE_KEY = "lumio-locale";

// Namespace caricati staticamente (bundle piccolo, nessun backend HTTP/
// lazy-loading: "valutare lazy loading... se realmente necessario", non lo
// e' oggi per un'app personale — SPEC_FE_REDESIGN §31).
const resources = {
  it: { accounts: accountsIt, categories: categoriesIt, common: commonIt, dashboard: dashboardIt, enums: enumsIt, imports: importsIt, jobs: jobsIt, navigation: navigationIt, portfolio: portfolioIt, rules: rulesIt, settings: settingsIt, transactions: transactionsIt },
  en: { accounts: accountsEn, categories: categoriesEn, common: commonEn, dashboard: dashboardEn, enums: enumsEn, imports: importsEn, jobs: jobsEn, navigation: navigationEn, portfolio: portfolioEn, rules: rulesEn, settings: settingsEn, transactions: transactionsEn },
};

function readStoredLocale(): SupportedLocale | null {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (SUPPORTED_LOCALES.includes(stored as SupportedLocale)) return stored as SupportedLocale;
  } catch {
    /* localStorage non disponibile */
  }
  return null;
}

function detectBrowserLocale(): SupportedLocale {
  const browserLang = navigator.language?.slice(0, 2);
  return SUPPORTED_LOCALES.includes(browserLang as SupportedLocale) ? (browserLang as SupportedLocale) : DEFAULT_LOCALE;
}

void i18n.use(initReactI18next).init({
  resources,
  lng: readStoredLocale() ?? detectBrowserLocale(),
  fallbackLng: DEFAULT_LOCALE,
  supportedLngs: SUPPORTED_LOCALES,
  // "enums": un solo posto per le etichette degli enum del backend
  // (SPEC_FE_REDESIGN §27), condiviso da tutte le feature che mostrano
  // lo stesso enum invece di una mappa hardcoded per feature.
  // "jobs": etichette dei job di sistema (name/description/scheduleDescription/
  // disableWarning/parametri) — il backend (app/services/job_registry.py)
  // restituisce solo chiavi stabili, mai piu' testo italiano hardcoded
  // (DECISION REQUIRED "testo backend", risolta scegliendo questa strada).
  // "categories": CategoryPicker/CreateCategoryDialog sono componenti
  // condivisi usati anche fuori da Impostazioni (correzione transazione,
  // creazione regola), non solo dalla pagina Settings > Categorie.
  ns: ["accounts", "categories", "common", "dashboard", "enums", "imports", "jobs", "navigation", "portfolio", "rules", "settings", "transactions"],
  defaultNS: "common",
  interpolation: { escapeValue: false },
  // In sviluppo una translation key mancante deve essere facilmente
  // individuabile (SPEC_FE_REDESIGN §31/§32), non silenziosamente ignorata.
  saveMissing: import.meta.env.DEV,
  missingKeyHandler: import.meta.env.DEV
    ? (langs, ns, key) => console.warn(`[i18n] chiave mancante: ${ns}:${key} (${langs.join(", ")})`)
    : undefined,
});

/** Persiste la scelta lingua (stesso pattern di `ThemeProvider`) e aggiorna
 * i18next — chi chiama non deve occuparsi separatamente delle due cose. */
export function setLocale(locale: SupportedLocale): void {
  void i18n.changeLanguage(locale);
  try {
    localStorage.setItem(STORAGE_KEY, locale);
  } catch {
    /* localStorage non disponibile: la lingua resta valida solo per la sessione corrente */
  }
}

export default i18n;
