import { createContext, useContext } from "react";
import { createPortal } from "react-dom";
import type { ReactNode, ReactPortal } from "react";

/** Nodo DOM del contenitore nel Topbar (fra il logo e lingua/tema/utente),
 * fornito da `AppShell` — `null` finche' il Topbar non e' montato o su
 * mobile (il contenitore e' `hidden` sotto `md:`, ma il ref esiste comunque:
 * il portal funziona anche in un contenitore nascosto via CSS, semplicemente
 * non e' visibile finche' non lo diventa). */
export const PageToolbarContext = createContext<HTMLDivElement | null>(null);

/**
 * Sposta le azioni di pagina (navigatore periodo, pulsante "aggiungi X")
 * nel Topbar invece che in cima al contenuto scrollabile (PHASE 5b, rework
 * Dashboard-come-punto-d'ingresso): restano visibili scorrendo perche' il
 * Topbar non scorre mai, e vivono tutte nello stesso posto in ogni pagina.
 *
 * Portal su un nodo DOM stabile (stesso principio di `Dialog.tsx`/
 * `Drawer.tsx` in questo repo), NON stato React condiviso: se il contenuto
 * passasse per lo stato di `AppShell` via un `useEffect` in ogni pagina, un
 * nuovo nodo JSX ad ogni render della pagina rifarebbe scattare l'effect,
 * causando un re-render di `AppShell` che ri-renderizza l'intero
 * sottoalbero incluse le pagine — loop. Un portal invece e' idempotente:
 * "renderizza anche qui" non tocca lo stato di nessun antenato.
 *
 * Il valore ritornato va incluso nel JSX della pagina chiamante (es.
 * `{toolbarPortal}` in un punto qualsiasi dell'albero) perche' il portal
 * venga montato — la posizione nel JSX della pagina non conta, solo il
 * nodo DOM target conta. Uno smontaggio (cambio tab, cambio pagina) rimuove
 * da solo il contenuto dal Topbar, comportamento standard di `createPortal`.
 */
export function usePageToolbar(node: ReactNode): ReactPortal | null {
  const slot = useContext(PageToolbarContext);
  return slot ? createPortal(node, slot) : null;
}
