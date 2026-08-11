// Layer centralizzato di comunicazione col backend (SPEC_FE §6): nessun
// fetch sparso nei componenti, tutto passa da qui. Stesso-origine sempre
// (vedi vite.config.ts/nginx.conf) quindi il path e' sempre relativo.

const API_BASE = "/api/v1";

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

async function refreshAccessToken(): Promise<boolean> {
  const response = await fetch(`${API_BASE}/auth/refresh`, {
    method: "POST",
    credentials: "include",
  });
  if (!response.ok) return false;
  const body = (await parseBody(response)) as { access_token?: string } | null;
  if (!body?.access_token) return false;
  setAccessToken(body.access_token);
  return true;
}

interface RequestOptions {
  method?: string;
  body?: unknown;
  isFormData?: boolean;
  signal?: AbortSignal;
}

async function rawRequest(path: string, options: RequestOptions): Promise<Response> {
  const headers: Record<string, string> = {};
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

  return fetch(`${API_BASE}${path}`, {
    method: options.method ?? "GET",
    headers,
    body,
    credentials: "include",
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
  patch: <T>(path: string, body?: unknown) => apiRequest<T>(path, { method: "PATCH", body }),
  delete: <T>(path: string) => apiRequest<T>(path, { method: "DELETE" }),
  refreshAccessToken,
  base: API_BASE,
};
