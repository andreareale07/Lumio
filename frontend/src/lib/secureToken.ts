import { SecureStorage } from "@aparajita/capacitor-secure-storage";

import { isNativeApp } from "./platform";

// Refresh token dell'app nativa: nel Keystore Android / Keychain iOS (cifrato dal
// sistema), mai in localStorage. Sul web non serve: c'e' il cookie httpOnly.

const REFRESH_TOKEN_KEY = "refresh_token";

export async function getStoredRefreshToken(): Promise<string | null> {
  if (!isNativeApp()) return null;
  try {
    const value = await SecureStorage.getItem(REFRESH_TOKEN_KEY);
    return typeof value === "string" && value ? value : null;
  } catch {
    return null;
  }
}

export async function storeRefreshToken(token: string): Promise<void> {
  if (!isNativeApp()) return;
  await SecureStorage.setItem(REFRESH_TOKEN_KEY, token);
}

export async function clearStoredRefreshToken(): Promise<void> {
  if (!isNativeApp()) return;
  try {
    await SecureStorage.removeItem(REFRESH_TOKEN_KEY);
  } catch {
    /* gia' assente */
  }
}
