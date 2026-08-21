import i18n from "i18next";
import { initReactI18next } from "react-i18next";

import commonEn from "../locales/en/common.json";
import enumsEn from "../locales/en/enums.json";
import jobsEn from "../locales/en/jobs.json";
import navigationEn from "../locales/en/navigation.json";
import settingsEn from "../locales/en/settings.json";
import commonIt from "../locales/it/common.json";
import enumsIt from "../locales/it/enums.json";
import jobsIt from "../locales/it/jobs.json";
import navigationIt from "../locales/it/navigation.json";
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
  it: { common: commonIt, enums: enumsIt, jobs: jobsIt, navigation: navigationIt, settings: settingsIt },
  en: { common: commonEn, enums: enumsEn, jobs: jobsEn, navigation: navigationEn, settings: settingsEn },
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
  ns: ["common", "enums", "jobs", "navigation", "settings"],
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
