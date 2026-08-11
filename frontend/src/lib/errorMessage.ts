import { ApiError } from "./apiClient";

/** Non mostrare mai l'errore tecnico grezzo (SPEC_FE §56) — solo per gli
 * errori di validazione (422) il dettaglio del backend e' già pensato per
 * l'utente (es. "specificare esattamente uno tra..."). Un 401 NON ha un
 * significato universale: su login/register e' "credenziali sbagliate", su
 * qualunque altra chiamata (dopo che apiClient ha gia' tentato un refresh)
 * e' "sessione scaduta" — significati opposti, quindi qui non si sceglie
 * per conto del chiamante: si usa sempre il `fallback` che il chiamante ha
 * gia' scritto per il proprio contesto specifico.
 */
export function friendlyErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof ApiError) {
    if (error.status === 422 || error.status === 400 || error.status === 409) {
      return error.message;
    }
    if (error.status === 404) return "Elemento non trovato.";
  }
  return fallback;
}
