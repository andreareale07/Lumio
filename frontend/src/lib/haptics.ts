import { Haptics, ImpactStyle, NotificationType } from "@capacitor/haptics";

import { isNativeApp } from "./platform";

// Feedback tattile: plugin nativo nel guscio Capacitor, `navigator.vibrate` nel
// browser Android; ovunque non sia supportato (iOS Safari, desktop) non fa nulla.
// Mai bloccante: un errore del plugin non deve rompere l'azione dell'utente.

function vibrate(pattern: number | number[]) {
  try {
    navigator.vibrate?.(pattern);
  } catch {
    /* non supportato */
  }
}

/** Tocco leggero: soglia raggiunta, selezione. */
export function hapticTap() {
  if (isNativeApp()) void Haptics.impact({ style: ImpactStyle.Light }).catch(() => undefined);
  else vibrate(10);
}

/** Azione completata (es. movimento confermato). */
export function hapticSuccess() {
  if (isNativeApp()) void Haptics.notification({ type: NotificationType.Success }).catch(() => undefined);
  else vibrate([12, 40, 12]);
}
