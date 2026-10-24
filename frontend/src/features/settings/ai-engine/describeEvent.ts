import type { TFunction } from "i18next";

import type { AIRunEvent } from "../../../types/api";

/** Il backend restituisce un `code` stabile e un dettaglio tecnico neutro
 * rispetto alla lingua (mai testo per l'utente): qui si compone la frase
 * tradotta. Un dettaglio di tipo "classified=12 no_match=3" viene letto come
 * coppie chiave=valore. */
export function parseDetail(message: string): Record<string, string> {
  const pairs: Record<string, string> = {};
  for (const token of message.split(/\s+/)) {
    const separator = token.indexOf("=");
    if (separator > 0) pairs[token.slice(0, separator)] = token.slice(separator + 1);
  }
  return pairs;
}

export function describeEvent(t: TFunction, event: Pick<AIRunEvent, "code" | "message">): string {
  const prefix = "items.aiEngine.events";
  switch (event.code) {
    case "provider_error":
      return t(`${prefix}.provider_error`, { detail: event.message });
    case "job_interrupted":
      return t(`${prefix}.job_interrupted.${event.message}`, {
        defaultValue: t(`${prefix}.job_interrupted.unexpected`),
      });
    case "skipped_no_profile":
      return t(`${prefix}.skipped_no_profile.${event.message}`, {
        defaultValue: t(`${prefix}.skipped_no_profile.no_active_profile`),
      });
    case "skipped_nothing_eligible":
      return t(`${prefix}.skipped_nothing_eligible`);
    case "run_completed": {
      const counts = parseDetail(event.message);
      // La riclassificazione non conta le righe "senza categoria pertinente":
      // senza quel dato si usa la frase breve, non un "—" nel mezzo di una frase.
      return t(`${prefix}.${counts.no_match === undefined ? "run_completed_short" : "run_completed"}`, {
        classified: counts.classified ?? "0",
        providerErrors: counts.provider_errors ?? "0",
        total: counts.total ?? "0",
        noMatch: counts.no_match,
      });
    }
    default:
      return event.message ? `${event.code}: ${event.message}` : event.code;
  }
}
