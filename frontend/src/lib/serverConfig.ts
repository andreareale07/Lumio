import { Preferences } from "@capacitor/preferences";

import { isNativeApp } from "./platform";

// Nel guscio nativo l'app (asset locali) deve sapere a quale server Lumio
// collegarsi: l'URL sceglie l'utente alla prima apertura. Sul web (stesso
// origin del server) non serve e il base path resta relativo.

const SERVER_URL_KEY = "lumio.server_url";

let serverUrl: string | null = null;

/** Da chiamare una volta all'avvio, prima di montare React. */
export async function loadServerConfig(): Promise<void> {
  if (!isNativeApp()) return;
  const { value } = await Preferences.get({ key: SERVER_URL_KEY });
  serverUrl = value;
}

export function getServerUrl(): string | null {
  return serverUrl;
}

/** `true` se serve ancora scegliere il server (solo nell'app nativa). */
export function needsServerSetup(): boolean {
  return isNativeApp() && !serverUrl;
}

/** Base delle API: relativa sul web, assoluta (server scelto) nell'app nativa. */
export function getApiBase(): string {
  return `${serverUrl ?? ""}/api/v1`;
}

export type ServerUrlCheck = { ok: true; url: string } | { ok: false; reason: "empty" | "invalid" };

/** Normalizza quanto digitato: senza schema si assume https, niente slash finale
 * ne' percorso/query (l'app aggiunge `/api/v1`). */
export function normalizeServerUrl(input: string): ServerUrlCheck {
  const trimmed = input.trim();
  if (!trimmed) return { ok: false, reason: "empty" };
  const withScheme = /^[a-z][a-z0-9+.-]*:\/\//i.test(trimmed) ? trimmed : `https://${trimmed}`;
  try {
    const url = new URL(withScheme);
    if (url.protocol !== "https:" && url.protocol !== "http:") return { ok: false, reason: "invalid" };
    return { ok: true, url: url.origin };
  } catch {
    return { ok: false, reason: "invalid" };
  }
}

/** `http://` verso un host non locale = traffico in chiaro su Internet. */
export function isInsecureRemote(url: string): boolean {
  try {
    const { protocol, hostname } = new URL(url);
    if (protocol !== "http:") return false;
    return !(
      hostname === "localhost" ||
      hostname.endsWith(".local") ||
      /^(10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.|127\.)/.test(hostname)
    );
  } catch {
    return false;
  }
}

/** Verifica che all'indirizzo risponda davvero un server Lumio. */
export async function testServer(url: string): Promise<boolean> {
  try {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 8000);
    const response = await fetch(`${url}/api/v1/auth/refresh`, {
      method: "POST",
      headers: { "X-Lumio-Client": "native" },
      signal: controller.signal,
    });
    clearTimeout(timer);
    // Senza token il backend risponde 401 con un JSON FastAPI ({"detail": ...}):
    // e' la firma di un server Lumio raggiungibile e con CORS corretto.
    if (response.status !== 401) return false;
    const body = (await response.json().catch(() => null)) as { detail?: unknown } | null;
    return typeof body?.detail === "string";
  } catch {
    return false;
  }
}

export async function saveServerUrl(url: string): Promise<void> {
  await Preferences.set({ key: SERVER_URL_KEY, value: url });
  serverUrl = url;
}

export async function clearServerUrl(): Promise<void> {
  await Preferences.remove({ key: SERVER_URL_KEY });
  serverUrl = null;
}
