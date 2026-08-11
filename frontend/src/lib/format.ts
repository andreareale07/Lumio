// SPEC_FE §61 (Currency Formatting), §62 (Date Formatting), §66 (Financial
// Numbers) — centralizzati qui, mai formattati ad-hoc nei componenti.

export function formatMoney(amount: string | number, currency: string): string {
  const value = typeof amount === "string" ? Number(amount) : amount;
  return new Intl.NumberFormat("it-IT", { style: "currency", currency }).format(value);
}

/** Il segno non si affida solo al colore (SPEC_FE §66): antepone sempre +/-. */
export function formatSignedMoney(amount: string | number, currency: string): string {
  const value = typeof amount === "string" ? Number(amount) : amount;
  const formatted = formatMoney(Math.abs(value), currency);
  return value < 0 ? `-${formatted}` : `+${formatted}`;
}

export function formatDate(isoDate: string): string {
  return new Intl.DateTimeFormat("it-IT", { day: "2-digit", month: "short", year: "numeric" }).format(
    new Date(isoDate),
  );
}

export function formatDateTime(isoDateTime: string): string {
  return new Intl.DateTimeFormat("it-IT", {
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
  const formatted = new Intl.NumberFormat("it-IT", {
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
  return new Intl.NumberFormat("it-IT", {
    style: "currency",
    currency,
    notation: "compact",
    maximumFractionDigits: 1,
  }).format(value);
}
