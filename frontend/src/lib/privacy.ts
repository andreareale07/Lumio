import { useSyncExternalStore } from "react";

// Modalita' privacy: gli importi in valuta non vengono mostrati (utile in
// pubblico). Preferenza per dispositivo, quindi in localStorage e non sul server.
// `lib/format.ts` la legge fuori da React; i componenti si riallineano grazie al
// remount di `App` quando il valore cambia (stesso meccanismo della lingua).

const STORAGE_KEY = "lumio-hide-amounts";
export const HIDDEN_AMOUNT = "••••";

function readStored(): boolean {
  try {
    return localStorage.getItem(STORAGE_KEY) === "1";
  } catch {
    return false;
  }
}

let hidden = readStored();
const listeners = new Set<() => void>();

export function isAmountsHidden(): boolean {
  return hidden;
}

export function setAmountsHidden(value: boolean): void {
  if (value === hidden) return;
  hidden = value;
  try {
    localStorage.setItem(STORAGE_KEY, value ? "1" : "0");
  } catch {
    /* modalita' privata: la preferenza dura solo per la sessione */
  }
  listeners.forEach((listener) => listener());
}

export function useAmountsHidden(): boolean {
  return useSyncExternalStore(
    (listener) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    isAmountsHidden,
  );
}
