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

// --- Granularita' + navigazione (rework UX/design, slice 1) ---------------
//
// Sostituisce concettualmente i preset sopra con un pattern unico:
// granularita' (giorno/settimana/mese/trimestre/semestre/anno) + un'ancora
// che identifica IL bucket corrente, navigabile avanti/indietro di un'unita'
// alla volta (vedi `usePeriodNavigator.ts`). I preset restano per la
// migrazione di eventuali URL/bookmark vecchi (`migrateLegacyPeriodParams`).

export type Granularity = "day" | "week" | "month" | "quarter" | "semester" | "year";

export const GRANULARITY_ORDER: Granularity[] = ["day", "week", "month", "quarter", "semester", "year"];

export const GRANULARITY_LABELS: Record<Granularity, string> = {
  day: "Giorno",
  week: "Settimana",
  month: "Mese",
  quarter: "Trimestre",
  semester: "Semestre",
  year: "Anno",
};

export const DEFAULT_GRANULARITY: Granularity = "month";

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

function addDays(d: Date, days: number): Date {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate() + days);
}

/** Periodo immediatamente precedente, della stessa durata — speculare a
 * `previous_period` in `backend/app/services/analytics_calc.py` (usata li'
 * per "vs periodo precedente" di KPI/Cash Flow). Qui serve per lo stesso
 * confronto ma per UNA categoria (drill-down del cruscotto), dove non c'e'
 * un campo `previous_*` gia' calcolato dal backend come per il summary
 * generale — due chiamate a `by-category` con questo range, non un nuovo
 * endpoint. */
export function previousPeriod(dateFrom: string, dateTo: string): Period {
  const from = new Date(`${dateFrom}T00:00:00`);
  const to = new Date(`${dateTo}T00:00:00`);
  const lengthDays = Math.round((to.getTime() - from.getTime()) / 86_400_000) + 1;
  const prevTo = addDays(from, -1);
  const prevFrom = addDays(prevTo, -(lengthDays - 1));
  return { date_from: toIsoDate(prevFrom), date_to: toIsoDate(prevTo) };
}

const GRANULARITY_MONTHS: Partial<Record<Granularity, number>> = {
  month: 1,
  quarter: 3,
  semester: 6,
  year: 12,
};

/** Inizio del bucket di `granularity` che contiene `d` — sempre
 * "canonicalizzato" (giorno 1 per month/quarter/semester/year), mai un
 * giorno arbitrario: ogni calcolo successivo (next/prev/finestra) parte da
 * qui, evitando i casi limite di fine mese/anno bisestile per costruzione.
 * Mirror esatto di `_bucket_start` in
 * `backend/app/services/analytics_calc.py` (stessa regola settimana
 * Monday-start: `(d.getDay() + 6) % 7`, equivalente a `d.weekday()` Python). */
export function bucketStart(granularity: Granularity, d: Date): Date {
  switch (granularity) {
    case "day":
      return new Date(d.getFullYear(), d.getMonth(), d.getDate());
    case "week": {
      const mondayOffset = (d.getDay() + 6) % 7;
      return addDays(new Date(d.getFullYear(), d.getMonth(), d.getDate()), -mondayOffset);
    }
    case "month":
      return startOfMonth(d);
    case "quarter": {
      const quarterMonth = Math.floor(d.getMonth() / 3) * 3;
      return new Date(d.getFullYear(), quarterMonth, 1);
    }
    case "semester":
      return new Date(d.getFullYear(), d.getMonth() < 6 ? 0 : 6, 1);
    case "year":
      return new Date(d.getFullYear(), 0, 1);
  }
}

/** Inizio del bucket successivo, assumendo che `d` sia gia' l'inizio di un
 * bucket (chiamare sempre su `bucketStart(...)`, mai su una data arbitraria).
 * Mirror esatto di `_next_bucket` in `analytics_calc.py`. */
export function nextBucketStart(granularity: Granularity, d: Date): Date {
  if (granularity === "day") return addDays(d, 1);
  if (granularity === "week") return addDays(d, 7);
  return addMonths(d, GRANULARITY_MONTHS[granularity]!);
}

/** `{date_from, date_to}` del bucket che contiene `anchor` — `date_to` e'
 * sempre "il giorno prima dell'inizio del bucket successivo", mai
 * un'aritmetica su giorni fissi (corretto per febbraio bisestile/mesi da
 * 30-31 giorni senza casi speciali). */
export function periodForAnchor(granularity: Granularity, anchor: Date): Period {
  const start = bucketStart(granularity, anchor);
  const end = addDays(nextBucketStart(granularity, start), -1);
  return { date_from: toIsoDate(start), date_to: toIsoDate(end) };
}

/** Ancora del bucket `±steps` rispetto a quello di `anchor`, sempre
 * normalizzata a inizio-bucket. I casi limite (fine anno per
 * trimestre/semestre/settimana, cambio anno) si risolvono per costruzione:
 * l'aritmetica opera sempre su un "inizio bucket" (giorno 1, tranne
 * day/week), mai su un giorno che potrebbe non esistere nel mese di
 * destinazione. */
export function shiftAnchor(granularity: Granularity, anchor: Date, steps: number): Date {
  const start = bucketStart(granularity, anchor);
  if (granularity === "day") return addDays(start, steps);
  if (granularity === "week") return addDays(start, steps * 7);
  return addMonths(start, GRANULARITY_MONTHS[granularity]! * steps);
}

/** `{date_from, date_to}` di una finestra scorrevole di `size` bucket che
 * termina nel bucket di `anchor` — usata per i grafici trend (stesso
 * controllo di navigazione del periodo puntuale, vedi decisione presa con
 * l'utente sul modello "finestra scorrevole" in `usePeriodNavigator.ts`). */
export function slidingWindow(granularity: Granularity, anchor: Date, size: number): Period {
  const endBucket = bucketStart(granularity, anchor);
  const startBucket = shiftAnchor(granularity, endBucket, -(size - 1));
  return {
    date_from: toIsoDate(startBucket),
    date_to: periodForAnchor(granularity, endBucket).date_to,
  };
}

const MONTH_YEAR_FORMAT = new Intl.DateTimeFormat("it-IT", { month: "long", year: "numeric" });
const DAY_MONTH_FORMAT = new Intl.DateTimeFormat("it-IT", { day: "2-digit", month: "short" });
const DAY_MONTH_YEAR_FORMAT = new Intl.DateTimeFormat("it-IT", { day: "2-digit", month: "short", year: "numeric" });

/** Etichetta leggibile del bucket corrente, coerente con lo stile gia' in
 * uso per gli assi dei grafici (`chartData.ts::formatBucketLabel`, minuscolo
 * per i nomi di mese come da convenzione italiana). */
export function periodLabel(granularity: Granularity, anchor: Date): string {
  const start = bucketStart(granularity, anchor);
  switch (granularity) {
    case "day":
      return DAY_MONTH_YEAR_FORMAT.format(start);
    case "week":
      return `Settimana dal ${DAY_MONTH_FORMAT.format(start)}`;
    case "month":
      return MONTH_YEAR_FORMAT.format(start);
    case "quarter":
      return `T${Math.floor(start.getMonth() / 3) + 1} ${start.getFullYear()}`;
    case "semester":
      return `S${start.getMonth() < 6 ? 1 : 2} ${start.getFullYear()}`;
    case "year":
      return String(start.getFullYear());
  }
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

export type MigratedPeriodParams =
  | { mode: "granular"; granularity: Granularity; anchor: string }
  | { mode: "custom"; from: string; to: string };

/** Traduce un vecchio `?period=<preset>` (dal filtro a preset fissi,
 * superato da questo slice) nel nuovo modello granularita'+ancora, o in
 * range personalizzato quando il preset non ha un equivalente granulare
 * pulito. Ritorna `null` se non c'e' nulla da migrare (nessun `period`
 * legacy nei search params). Chiamata una sola volta da
 * `usePeriodNavigator` alla prima lettura di una pagina. */
export function migrateLegacyPeriodParams(
  params: URLSearchParams,
  today: Date = new Date(),
): MigratedPeriodParams | null {
  const legacyPreset = params.get("period") as PeriodPresetKey | null;
  if (!legacyPreset) return null;

  switch (legacyPreset) {
    case "this_month":
      return { mode: "granular", granularity: "month", anchor: toIsoDate(bucketStart("month", today)) };
    case "last_month":
      return {
        mode: "granular",
        granularity: "month",
        anchor: toIsoDate(shiftAnchor("month", today, -1)),
      };
    case "this_year":
      return { mode: "granular", granularity: "year", anchor: toIsoDate(bucketStart("year", today)) };
    case "custom": {
      const from = params.get("from") ?? "";
      const to = params.get("to") ?? "";
      if (from && to) return { mode: "custom", from, to };
      const fallback = resolvePeriodPreset(DEFAULT_PERIOD_PRESET, today)!;
      return { mode: "custom", from: fallback.date_from, to: fallback.date_to };
    }
    case "last_3_months":
    case "last_6_months":
    case "last_12_months": {
      // Nessun equivalente granulare pulito (sono finestre rolling-da-oggi,
      // non "il trimestre/anno corrente") — migrati a un range personalizzato
      // congelato al momento della migrazione, non piu' rolling ad ogni
      // apertura (compromesso accettato per bookmark salvati, vedi piano).
      const resolved = resolvePeriodPreset(legacyPreset, today)!;
      return { mode: "custom", from: resolved.date_from, to: resolved.date_to };
    }
  }
}
