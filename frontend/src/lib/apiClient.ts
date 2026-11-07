// Layer centralizzato di comunicazione col backend (SPEC_FE §6): nessun
// fetch sparso nei componenti, tutto passa da qui. Sul web e' stesso-origine
// (vedi vite.config.ts/nginx.conf) quindi il path e' relativo; nell'app nativa
// la base e' il server scelto dall'utente (`serverConfig.ts`) e l'autenticazione
// usa solo Bearer + refresh token nel Keystore (nessun cookie nel WebView).

import { isNativeApp } from "./platform";
import { clearStoredRefreshToken, getStoredRefreshToken, storeRefreshToken } from "./secureToken";
import { getApiBase } from "./serverConfig";

/** Identifica il guscio nativo: il backend risponde col refresh token nel body. */
const NATIVE_HEADERS: Record<string, string> = isNativeApp() ? { "X-Lumio-Client": "native" } : {};
const credentialsMode = (): RequestCredentials => (isNativeApp() ? "omit" : "include");

export class ApiError extends Error {
  status: number;
  body: unknown;

  constructor(status: number, message: string, body: unknown) {
    super(message);
    this.status = status;
    this.body = body;
  }
}

let accessToken: string | null = null;
let onUnauthorized: (() => void) | null = null;

/** L'access token vive SOLO in memoria (SPEC_FE §74: mai in localStorage). */
export function setAccessToken(token: string | null): void {
  accessToken = token;
}

export function getAccessToken(): string | null {
  return accessToken;
}

/** Registrato da AuthProvider: invocato quando anche il refresh fallisce. */
export function setUnauthorizedHandler(handler: (() => void) | null): void {
  onUnauthorized = handler;
}

function extractErrorMessage(body: unknown, fallback: string): string {
  if (body && typeof body === "object" && "detail" in body) {
    const detail = (body as { detail: unknown }).detail;
    if (typeof detail === "string") return detail;
    if (detail && typeof detail === "object" && "detail" in detail) {
      const nested = (detail as { detail: unknown }).detail;
      if (typeof nested === "string") return nested;
    }
  }
  return fallback;
}

async function parseBody(response: Response): Promise<unknown> {
  const text = await response.text();
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

/** Nell'app nativa conserva il nuovo refresh token (il backend lo ruota ad ogni uso). */
export async function persistRefreshToken(token: string | null | undefined): Promise<void> {
  if (token) await storeRefreshToken(token);
}

// Single-flight: piu' richieste che prendono 401 insieme devono condividere UN
// solo refresh. Il token ruota ad ogni uso, un secondo tentativo in parallelo
// col vecchio token fallirebbe e farebbe uscire l'utente.
let refreshInFlight: Promise<boolean> | null = null;

async function doRefresh(): Promise<boolean> {
  const native = isNativeApp();
  let body: BodyInit | undefined;
  const headers: Record<string, string> = { ...NATIVE_HEADERS };
  if (native) {
    const stored = await getStoredRefreshToken();
    if (!stored) return false;
    headers["Content-Type"] = "application/json";
    body = JSON.stringify({ refresh_token: stored });
  }
  let response: Response;
  try {
    response = await fetch(`${getApiBase()}/auth/refresh`, {
      method: "POST",
      headers,
      body,
      credentials: credentialsMode(),
    });
  } catch {
    // Server non raggiungibile: non e' una sessione scaduta, il token resta.
    return false;
  }
  if (!response.ok) {
    if (native && response.status === 401) await clearStoredRefreshToken();
    return false;
  }
  const parsed = (await parseBody(response)) as { access_token?: string; refresh_token?: string | null } | null;
  if (!parsed?.access_token) return false;
  setAccessToken(parsed.access_token);
  await persistRefreshToken(parsed.refresh_token);
  return true;
}

function refreshAccessToken(): Promise<boolean> {
  refreshInFlight ??= doRefresh().finally(() => {
    refreshInFlight = null;
  });
  return refreshInFlight;
}

/** Chiusura sessione: revoca il token sul server e svuota il Keystore. */
export async function logoutRequest(): Promise<void> {
  const native = isNativeApp();
  const headers: Record<string, string> = { ...NATIVE_HEADERS };
  let body: BodyInit | undefined;
  if (native) {
    const stored = await getStoredRefreshToken();
    if (stored) {
      headers["Content-Type"] = "application/json";
      body = JSON.stringify({ refresh_token: stored });
    }
  }
  try {
    await fetch(`${getApiBase()}/auth/logout`, { method: "POST", headers, body, credentials: credentialsMode() });
  } finally {
    await clearStoredRefreshToken();
  }
}

interface RequestOptions {
  method?: string;
  body?: unknown;
  isFormData?: boolean;
  signal?: AbortSignal;
}

async function rawRequest(path: string, options: RequestOptions): Promise<Response> {
  const headers: Record<string, string> = { ...NATIVE_HEADERS };
  if (accessToken) headers["Authorization"] = `Bearer ${accessToken}`;

  let body: BodyInit | undefined;
  if (options.body !== undefined) {
    if (options.isFormData) {
      body = options.body as FormData;
    } else {
      headers["Content-Type"] = "application/json";
      body = JSON.stringify(options.body);
    }
  }

  return fetch(`${getApiBase()}${path}`, {
    method: options.method ?? "GET",
    headers,
    body,
    credentials: credentialsMode(),
    signal: options.signal,
  });
}

/**
 * Esegue una richiesta autenticata; su 401 tenta UN refresh e ritenta una
 * sola volta (evita loop infiniti se il refresh stesso e' scaduto/invalido).
 */
export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  let response = await rawRequest(path, options);

  if (response.status === 401 && path !== "/auth/refresh" && path !== "/auth/login") {
    const refreshed = await refreshAccessToken();
    if (refreshed) {
      response = await rawRequest(path, options);
    } else {
      setAccessToken(null);
      onUnauthorized?.();
    }
  }

  if (!response.ok) {
    const body = await parseBody(response);
    throw new ApiError(response.status, extractErrorMessage(body, response.statusText), body);
  }

  if (response.status === 204) return undefined as T;
  return (await parseBody(response)) as T;
}

export const api = {
  get: <T>(path: string, signal?: AbortSignal) => apiRequest<T>(path, { method: "GET", signal }),
  post: <T>(path: string, body?: unknown) => apiRequest<T>(path, { method: "POST", body }),
  postForm: <T>(path: string, body: FormData) =>
    apiRequest<T>(path, { method: "POST", body, isFormData: true }),
  put: <T>(path: string, body?: unknown) => apiRequest<T>(path, { method: "PUT", body }),
  patch: <T>(path: string, body?: unknown) => apiRequest<T>(path, { method: "PATCH", body }),
  delete: <T>(path: string, body?: unknown) => apiRequest<T>(path, { method: "DELETE", body }),
  refreshAccessToken,
  /** Letto a ogni chiamata (nell'app nativa cambia se l'utente cambia server). */
  get base() {
    return getApiBase();
  },
};
