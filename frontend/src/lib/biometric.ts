import { BiometricAuth } from "@aparajita/capacitor-biometric-auth";

import { isNativeApp } from "./platform";

/** Biometria (o PIN/schema del telefono) disponibile sul dispositivo. */
export async function isBiometricAvailable(): Promise<boolean> {
  if (!isNativeApp()) return false;
  try {
    const info = await BiometricAuth.checkBiometry();
    return info.isAvailable || info.deviceIsSecure;
  } catch {
    return false;
  }
}

/** Chiede impronta/volto; con `allowDeviceCredential` ripiega su PIN/schema del
 * telefono (chi non ha biometria registrata non resta chiuso fuori). `false` se
 * annullato o fallito: nessuna eccezione al chiamante. */
export async function authenticateUser(title: string, cancelTitle: string): Promise<boolean> {
  if (!isNativeApp()) return true;
  try {
    await BiometricAuth.authenticate({
      reason: title,
      cancelTitle,
      allowDeviceCredential: true,
      androidTitle: title,
    });
    return true;
  } catch {
    return false;
  }
}
