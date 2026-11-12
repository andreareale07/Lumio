import type { RulePreview } from "../../types/api";
import type { RulePreviewInput } from "./api";

/** Input dell'anteprima senza paginazione: la scheda e il riepilogo ne
 * derivano le richieste (stessa chiave di cache per i conteggi). */
export type RuleImpactInput = Omit<RulePreviewInput, "group" | "limit" | "offset">;

/** Solo i conteggi: una riga basta, il resto lo chiede la scheda dei movimenti. */
export function summaryInput(input: RuleImpactInput | null): RulePreviewInput | null {
  return input ? { ...input, limit: 1 } : null;
}

/** Movimenti che la regola catturerebbe pur avendo un'altra categoria, anche se
 * protetti da una correzione manuale: la frase e' condivisa con un'altra categoria. */
export function conflictCount(preview: RulePreview): number {
  return preview.other_category ?? 0;
}

/** La regola toglierebbe da altre categorie piu' movimenti di quanti sono gia'
 * giusti: segnale di una regola troppo ampia. Quelli senza categoria non
 * contano, e' l'effetto voluto. */
export function broadWarning(preview: RulePreview): boolean {
  return preview.recategorized > 3 && preview.recategorized > preview.already_correct;
}
