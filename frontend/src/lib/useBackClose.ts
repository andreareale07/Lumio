import { useEffect, useRef } from "react";

let nextId = 1;

function overlayStack(): number[] {
  const state = window.history.state as { __ov?: number[] } | null;
  return Array.isArray(state?.__ov) ? state.__ov : [];
}

/** Lega un overlay (Drawer, Dialog, BottomSheet) al tasto/gesto "indietro".
 *
 * All'apertura aggiunge UNA voce alla cronologia (stesso URL): "indietro" la
 * toglie e chiude l'overlay invece di uscire dalla pagina, un passo alla volta
 * anche con overlay annidati. Alla chiusura da UI (X, sfondo, Escape, azione) la
 * voce viene tolta con `history.back()`, cosi' la cronologia resta coerente.
 * Non usa hook del router: l'overlay funziona ovunque sia montato. */
export function useBackClose(open: boolean, onClose: () => void) {
  const idRef = useRef(0);
  const pushed = useRef(false);
  const onCloseRef = useRef(onClose);
  useEffect(() => {
    onCloseRef.current = onClose;
  });

  useEffect(() => {
    if (open && !pushed.current) {
      idRef.current = nextId++;
      const state = (window.history.state ?? {}) as Record<string, unknown>;
      window.history.pushState({ ...state, __ov: [...overlayStack(), idRef.current] }, "");
      pushed.current = true;
    } else if (!open && pushed.current) {
      pushed.current = false;
      if (overlayStack().includes(idRef.current)) window.history.back();
    }
  }, [open]);

  useEffect(() => {
    const onPop = () => {
      if (pushed.current && !overlayStack().includes(idRef.current)) {
        pushed.current = false;
        onCloseRef.current();
      }
    };
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);
}
