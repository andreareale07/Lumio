/** Preset del filtro periodo globale (SPEC_FE §12.2), puro e
 * unit-testabile: nessuna dipendenza da React/router. `today` e'
 * parametrizzato per i test — di default e' "adesso". */

export interface Period {
  date_from: string;
  date_to: string;
}

export type PeriodPresetKey =
  | "this_month"
  | "last_month"
  | "last_3_months"
  | "last_6_months"
  | "this_year"
  | "last_12_months"
  | "custom";

export const PERIOD_PRESET_ORDER: PeriodPresetKey[] = [
  "this_month",
  "last_month",
  "last_3_months",
  "last_6_months",
  "this_year",
  "last_12_months",
  "custom",
];

export const PERIOD_PRESET_LABELS: Record<PeriodPresetKey, string> = {
  this_month: "Questo mese",
  last_month: "Mese scorso",
  last_3_months: "Ultimi 3 mesi",
  last_6_months: "Ultimi 6 mesi",
  this_year: "Quest'anno",
  last_12_months: "Ultimi 12 mesi",
  custom: "Personalizzato",
};

export const DEFAULT_PERIOD_PRESET: PeriodPresetKey = "this_month";

function toIsoDate(d: Date): string {
  const year = d.getFullYear();
  const month = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function startOfMonth(d: Date): Date {
  return new Date(d.getFullYear(), d.getMonth(), 1);
}

function endOfMonth(d: Date): Date {
  return new Date(d.getFullYear(), d.getMonth() + 1, 0);
}

function addMonths(d: Date, months: number): Date {
  return new Date(d.getFullYear(), d.getMonth() + months, d.getDate());
}

/** Range risolto per un preset, o `null` per "Personalizzato" — in quel
 * caso il chiamante usa il range scelto dall'utente, non uno calcolato. */
export function resolvePeriodPreset(key: PeriodPresetKey, today: Date = new Date()): Period | null {
  switch (key) {
    case "this_month":
      return { date_from: toIsoDate(startOfMonth(today)), date_to: toIsoDate(today) };
    case "last_month": {
      const anchor = addMonths(today, -1);
      return { date_from: toIsoDate(startOfMonth(anchor)), date_to: toIsoDate(endOfMonth(anchor)) };
    }
    case "last_3_months":
      return { date_from: toIsoDate(addMonths(today, -3)), date_to: toIsoDate(today) };
    case "last_6_months":
      return { date_from: toIsoDate(addMonths(today, -6)), date_to: toIsoDate(today) };
    case "this_year":
      return { date_from: toIsoDate(new Date(today.getFullYear(), 0, 1)), date_to: toIsoDate(today) };
    case "last_12_months":
      return { date_from: toIsoDate(addMonths(today, -12)), date_to: toIsoDate(today) };
    case "custom":
      return null;
  }
}
