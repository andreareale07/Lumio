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
