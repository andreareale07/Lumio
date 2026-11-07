import { Preferences } from "@capacitor/preferences";

import { isNativeApp } from "./platform";

// Preferenze del blocco app (per dispositivo, nell'app nativa). Lette una volta
// all'avvio in `loadAppLockPrefs` e poi sincrone dalla cache.

const ENABLED_KEY = "lumio.lock_enabled";
const DELAY_KEY = "lumio.lock_delay_s";

/** Tempo in background dopo il quale l'app si blocca (0 = al rientro, sempre). */
export const LOCK_DELAY_OPTIONS_S = [0, 60, 300] as const;
export type LockDelay = (typeof LOCK_DELAY_OPTIONS_S)[number];

let enabled = false;
let delaySeconds: LockDelay = 60;

export async function loadAppLockPrefs(): Promise<void> {
  if (!isNativeApp()) return;
  const [e, d] = await Promise.all([Preferences.get({ key: ENABLED_KEY }), Preferences.get({ key: DELAY_KEY })]);
  enabled = e.value === "1";
  const parsed = Number(d.value);
  delaySeconds = (LOCK_DELAY_OPTIONS_S as readonly number[]).includes(parsed) ? (parsed as LockDelay) : 60;
}

export const isLockEnabled = (): boolean => enabled;
export const getLockDelay = (): LockDelay => delaySeconds;

export async function setLockEnabled(value: boolean): Promise<void> {
  enabled = value;
  await Preferences.set({ key: ENABLED_KEY, value: value ? "1" : "0" });
}

export async function setLockDelay(value: LockDelay): Promise<void> {
  delaySeconds = value;
  await Preferences.set({ key: DELAY_KEY, value: String(value) });
}
