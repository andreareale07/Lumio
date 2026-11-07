import { registerPlugin } from "@capacitor/core";

import { isNativeApp } from "./platform";

// Plugin locale Android (`PrivacyScreenPlugin.java`): FLAG_SECURE = niente anteprima
// nelle app recenti e niente screenshot. Sul web non esiste: no-op.
const PrivacyScreen = registerPlugin<{ setEnabled(options: { enabled: boolean }): Promise<void> }>("PrivacyScreen");

export async function setPrivacyScreen(enabled: boolean): Promise<void> {
  if (!isNativeApp()) return;
  try {
    await PrivacyScreen.setEnabled({ enabled });
  } catch {
    /* piattaforma senza il plugin (iOS): nessun effetto */
  }
}
