import type { AnalyticsGranularity } from "../../types/api";
import { type PeriodLabelStrings, quarterOrSemesterLabel } from "../../lib/period";

/** Etichetta leggibile di un bucket temporale per assi/tabelle dei grafici,
 * coerente con la granularita' scelta (SPEC_FE §67 Charts). Resta piu'
 * compatta di `period.ts::periodLabel` (usata dal navigatore periodo) per
 * giorno/settimana/mese — stesso spazio limitato di un'etichetta d'asse —
 * ma condivide con essa il calcolo di trimestre/semestre, identico nelle
 * due formattazioni (SPEC_FE_REDESIGN §21). `strings` opzionale, stesso
 * principio di `period.ts::PeriodLabelStrings` (default italiano, il
 * chiamante React passa `intlLocale()`/abbreviazioni tradotte). */
export function formatBucketLabel(
  period: string,
  granularity: AnalyticsGranularity,
  strings: Pick<PeriodLabelStrings, "locale" | "quarterAbbrev" | "semesterAbbrev"> = {},
): string {
  const locale = strings.locale ?? "it-IT";
  const date = new Date(`${period}T00:00:00`);
  switch (granularity) {
    case "day":
    case "week":
      return new Intl.DateTimeFormat(locale, { day: "2-digit", month: "short" }).format(date);
    case "month":
      return new Intl.DateTimeFormat(locale, { month: "short", year: "numeric" }).format(date);
    case "quarter":
    case "semester":
      return quarterOrSemesterLabel(granularity, date, strings);
    case "year":
      return String(date.getFullYear());
  }
}

export type GreetingBucket = "morning" | "afternoon" | "evening";

/** Solo la fascia oraria: il testo vive in dashboard:greeting.<bucket>
 * (namespace i18next), non qui — questo modulo non e' un componente React
 * e non ha accesso a `t()`. */
export function greetingBucketForHour(hour: number): GreetingBucket {
  if (hour < 12) return "morning";
  if (hour < 18) return "afternoon";
  return "evening";
}
