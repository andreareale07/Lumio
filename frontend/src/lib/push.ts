import { Preferences } from "@capacitor/preferences";
import { PushNotifications } from "@capacitor/push-notifications";

import { api } from "./apiClient";
import { isNativeApp } from "./platform";

// Notifiche push (FCM) nell'app Android. Il token del telefono si registra sul
// server; il server manda un avviso (senza importi) dopo le sync bancarie
// automatiche. Senza `google-services.json` nell'APK `register()` fallisce:
// e' il caso "FCM non configurato", gestito come errore normale.

const TOKEN_KEY = "lumio.push_token";
const CHANNEL_ID = "lumio_default";

export type PushEnableResult = "enabled" | "denied" | "error";

let listenersReady = false;

function registrationToken(): Promise<string> {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error("timeout")), 15000);
    void PushNotifications.addListener("registration", (token) => {
      clearTimeout(timer);
      resolve(token.value);
    });
    void PushNotifications.addListener("registrationError", (error) => {
      clearTimeout(timer);
      reject(new Error(error.error));
    });
    void PushNotifications.register();
  });
}

export async function enablePush(): Promise<PushEnableResult> {
  if (!isNativeApp()) return "error";
  try {
    const permission = await PushNotifications.requestPermissions();
    if (permission.receive !== "granted") return "denied";
    await PushNotifications.createChannel({
      id: CHANNEL_ID,
      name: "Lumio",
      importance: 3,
    }).catch(() => undefined);
    const token = await registrationToken();
    await api.post("/push/devices", { token, platform: "android" });
    await Preferences.set({ key: TOKEN_KEY, value: token });
    return "enabled";
  } catch {
    return "error";
  }
}

export async function disablePush(): Promise<void> {
  if (!isNativeApp()) return;
  const { value } = await Preferences.get({ key: TOKEN_KEY });
  if (value) {
    await api.delete("/push/devices", { token: value }).catch(() => undefined);
    await Preferences.remove({ key: TOKEN_KEY });
  }
}

export async function isPushEnabledOnDevice(): Promise<boolean> {
  if (!isNativeApp()) return false;
  const { value } = await Preferences.get({ key: TOKEN_KEY });
  return !!value;
}

/** Tocco su una notifica: apre i movimenti da verificare. */
export function initPushNavigation(): void {
  if (!isNativeApp() || listenersReady) return;
  listenersReady = true;
  void PushNotifications.addListener("pushNotificationActionPerformed", () => {
    window.location.assign("/transactions?review=1");
  });
}
