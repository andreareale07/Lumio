// SPEC_FE §61 (Currency Formatting), §62 (Date Formatting), §66 (Financial
// Numbers) — centralizzati qui, mai formattati ad-hoc nei componenti.

import i18n from "../app/i18n";

// Locale Intl completo per la lingua corrente (SPEC_FE_REDESIGN §28-29):
// letto al momento della chiamata, mai fissato a "it-IT" — chi vuole vedere
// il cambio riflesso a schermo deve rimontare (vedi `App.tsx`, key su
// `i18n.language`), stesso principio gia' in uso per il tema.
const INTL_LOCALE_BY_LANGUAGE: Record<string, string> = { it: "it-IT", en: "en-US" };
function intlLocale(): string {
  return INTL_LOCALE_BY_LANGUAGE[i18n.language] ?? "it-IT";
}

export function formatMoney(amount: string | number, currency: string): string {
  const value = typeof amount === "string" ? Number(amount) : amount;
  return new Intl.NumberFormat(intlLocale(), { style: "currency", currency }).format(value);
}

/** Il segno non si affida solo al colore (SPEC_FE §66): antepone sempre +/-. */
export function formatSignedMoney(amount: string | number, currency: string): string {
  const value = typeof amount === "string" ? Number(amount) : amount;
  const formatted = formatMoney(Math.abs(value), currency);
  return value < 0 ? `-${formatted}` : `+${formatted}`;
}

export function formatDate(isoDate: string): string {
  return new Intl.DateTimeFormat(intlLocale(), { day: "2-digit", month: "short", year: "numeric" }).format(
    new Date(isoDate),
  );
}

export function formatDateTime(isoDateTime: string): string {
  return new Intl.DateTimeFormat(intlLocale(), {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(isoDateTime));
}

export function formatPeriodLabel(dateFrom: string, dateTo: string): string {
  return `${formatDate(dateFrom)} – ${formatDate(dateTo)}`;
}

/** Variazione percentuale per i confronti "vs periodo precedente"
 * (SPEC_FE §13). Riceve una frazione (0.084 → "8,4%"), non una percentuale
 * gia' moltiplicata per 100. */
export function formatPercent(fraction: string | number, options: { signed?: boolean } = {}): string {
  const value = typeof fraction === "string" ? Number(fraction) : fraction;
  const formatted = new Intl.NumberFormat(intlLocale(), {
    style: "percent",
    maximumFractionDigits: 1,
  }).format(Math.abs(value));
  if (!options.signed) return formatted;
  if (value > 0) return `+${formatted}`;
  if (value < 0) return `-${formatted}`;
  return formatted;
}

/** Notazione compatta per gli assi dei grafici (es. "1,2 K €") — mai per i
 * KPI principali, dove il valore esatto conta (SPEC_FE §66). */
export function formatCompactMoney(amount: string | number, currency: string): string {
  const value = typeof amount === "string" ? Number(amount) : amount;
  return new Intl.NumberFormat(intlLocale(), {
    style: "currency",
    currency,
    notation: "compact",
    maximumFractionDigits: 1,
  }).format(value);
}

const _LARGE_MONEY_TIERS: [number, string][] = [
  [1e12, "T"],
  [1e9, "B"],
  [1e6, "M"],
];

/** Valori molto grandi (patrimonio di un fondo, capitalizzazione) con
 * unità M/B/T (milione/bilione/trilione) — a differenza di
 * `formatCompactMoney`, non usa l'abbreviazione italiana di Intl
 * ("mln"/"mld"), sempre queste tre lettere per richiesta esplicita. */
export function formatLargeMoney(amount: string | number, currency: string): string {
  const value = typeof amount === "string" ? Number(amount) : amount;
  const tier = _LARGE_MONEY_TIERS.find(([threshold]) => Math.abs(value) >= threshold);
  if (!tier) return formatMoney(value, currency);
  const [divisor, suffix] = tier;
  const scaled = new Intl.NumberFormat(intlLocale(), { maximumFractionDigits: 2, minimumFractionDigits: 2 }).format(
    value / divisor,
  );
  const symbol =
    new Intl.NumberFormat(intlLocale(), { style: "currency", currency, currencyDisplay: "narrowSymbol" })
      .formatToParts(0)
      .find((p) => p.type === "currency")?.value ?? currency;
  return `${scaled} ${suffix} ${symbol}`;
}
