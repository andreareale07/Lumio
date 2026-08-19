import type { AnalyticsGranularity } from "../../types/api";
import { quarterOrSemesterLabel } from "../../lib/period";

/** Etichetta leggibile di un bucket temporale per assi/tabelle dei grafici,
 * coerente con la granularita' scelta (SPEC_FE §67 Charts). Resta piu'
 * compatta di `period.ts::periodLabel` (usata dal navigatore periodo) per
 * giorno/settimana/mese — stesso spazio limitato di un'etichetta d'asse —
 * ma condivide con essa il calcolo di trimestre/semestre, identico nelle
 * due formattazioni (SPEC_FE_REDESIGN §21). */
export function formatBucketLabel(period: string, granularity: AnalyticsGranularity): string {
  const date = new Date(`${period}T00:00:00`);
  switch (granularity) {
    case "day":
    case "week":
      return new Intl.DateTimeFormat("it-IT", { day: "2-digit", month: "short" }).format(date);
    case "month":
      return new Intl.DateTimeFormat("it-IT", { month: "short", year: "numeric" }).format(date);
    case "quarter":
    case "semester":
      return quarterOrSemesterLabel(granularity, date);
    case "year":
      return String(date.getFullYear());
  }
}

export function greetingForHour(hour: number): string {
  if (hour < 12) return "Buongiorno";
  if (hour < 18) return "Buon pomeriggio";
  return "Buonasera";
}
