import { Capacitor } from "@capacitor/core";

/** `true` quando l'app gira nel guscio nativo (Capacitor), `false` nel browser/PWA. */
export const isNativeApp = (): boolean => Capacitor.isNativePlatform();
