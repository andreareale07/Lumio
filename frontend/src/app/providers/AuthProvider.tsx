import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

import { api } from "../../lib/apiClient";
import { setAccessToken, setUnauthorizedHandler } from "../../lib/apiClient";
import type { Me, TokenResponse } from "../../types/api";

type AuthStatus = "loading" | "authenticated" | "unauthenticated";

interface AuthContextValue {
  status: AuthStatus;
  user: Me | null;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, displayName: string) => Promise<void>;
  logout: () => Promise<void>;
  /** Ri-scarica /auth/me (es. dopo aver cambiato base_currency in
   * Impostazioni > Valuta) — evita che `user` resti con un valore stantio
   * fino al prossimo refresh del token. */
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>("loading");
  const [user, setUser] = useState<Me | null>(null);

  const handleTokenResponse = useCallback((response: TokenResponse) => {
    setAccessToken(response.access_token);
    setUser(response.user);
    setStatus("authenticated");
  }, []);

  const clearSession = useCallback(() => {
    setAccessToken(null);
    setUser(null);
    setStatus("unauthenticated");
  }, []);

  useEffect(() => {
    setUnauthorizedHandler(clearSession);
    return () => setUnauthorizedHandler(null);
  }, [clearSession]);

  // Sessione ripristinata al reload tramite il cookie httpOnly di refresh
  // (l'access token vive solo in memoria, quindi non sopravvive a un
  // ricaricamento della pagina — SPEC_FE §74).
  useEffect(() => {
    let cancelled = false;
    (async () => {
      const refreshed = await api.refreshAccessToken();
      if (cancelled) return;
      if (!refreshed) {
        setStatus("unauthenticated");
        return;
      }
      try {
        const me = await api.get<Me>("/auth/me");
        if (!cancelled) {
          setUser(me);
          setStatus("authenticated");
        }
      } catch {
        if (!cancelled) clearSession();
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [clearSession]);

  const login = useCallback(
    async (email: string, password: string) => {
      const response = await api.post<TokenResponse>("/auth/login", { email, password });
      handleTokenResponse(response);
    },
    [handleTokenResponse],
  );

  const register = useCallback(
    async (email: string, password: string, displayName: string) => {
      const response = await api.post<TokenResponse>("/auth/register", {
        email,
        password,
        display_name: displayName,
      });
      handleTokenResponse(response);
    },
    [handleTokenResponse],
  );

  const logout = useCallback(async () => {
    try {
      await api.post("/auth/logout");
    } finally {
      clearSession();
    }
  }, [clearSession]);

  const refreshUser = useCallback(async () => {
    const me = await api.get<Me>("/auth/me");
    setUser(me);
  }, []);

  const value = useMemo(
    () => ({ status, user, login, register, logout, refreshUser }),
    [status, user, login, register, logout, refreshUser],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
