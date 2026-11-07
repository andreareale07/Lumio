import type { BankConnection } from "../../../types/api";

export type BankStatusKey = "active" | "expiring" | "expired" | "revoked" | "error" | "pending";
export type BankStatusTone = "success" | "warning" | "danger" | "neutral";

/** Lo stato mostrato combina `status` e `expiring_soon`: "in scadenza" non e'
 * uno stato del backend ma un avviso anticipato sul consenso ancora valido. */
export function statusKeyOf(connection: BankConnection): BankStatusKey {
  if (connection.status === "active" && connection.expiring_soon) return "expiring";
  return connection.status;
}

export const STATUS_TONE: Record<BankStatusKey, BankStatusTone> = {
  active: "success",
  expiring: "warning",
  expired: "danger",
  error: "danger",
  revoked: "neutral",
  pending: "neutral",
};

/** Il consenso richiede un intervento dell'utente (rinnovo) oppure presto lo richiedera'. */
export function needsRenewal(connection: BankConnection): boolean {
  const key = statusKeyOf(connection);
  return key === "expiring" || key === "expired";
}

/** Paesi dello Spazio Economico Europeo in cui Enable Banking opera: i nomi si
 * ricavano da `Intl.DisplayNames`, mai tradotti a mano. L'elenco reale delle
 * banche arriva sempre dall'API del provider. */
export const COUNTRY_CODES = [
  "IT", "AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR", "HU", "IS", "IE", "LV",
  "LI", "LT", "LU", "MT", "NL", "NO", "PL", "PT", "RO", "SK", "SI", "ES", "SE",
] as const;
