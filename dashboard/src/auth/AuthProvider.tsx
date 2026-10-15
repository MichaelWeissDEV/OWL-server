import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api, API, ApiError, onUnauthorized, tokenStore } from "../api/client";
import type { AuthConfig, Me } from "../api/types";

interface AuthState {
  config: AuthConfig | null;
  me: Me | null;
  loading: boolean;
  error: string | null;
  isAdmin: boolean;
  signedIn: boolean;
  login: (username: string, password: string) => Promise<void>;
  acceptToken: (token: string) => Promise<void>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [config, setConfig] = useState<AuthConfig | null>(null);
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [cfg, who] = await Promise.all([
        api<AuthConfig>(`${API}/auth/config`, { quiet401: true }),
        api<Me>(`${API}/auth/me`, { quiet401: true }),
      ]);
      setConfig(cfg);
      setMe(who);
      setError(null);
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) {
        tokenStore.set(null);
        setMe({ authenticated: false, kind: "anonymous", username: "anonymous", is_admin: false, memberships: [], token_role: null });
        try {
          setConfig(await api<AuthConfig>(`${API}/auth/config`, { quiet401: true }));
        } catch {
          /* handled below */
        }
      } else {
        setError((e as Error).message);
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(
    () =>
      onUnauthorized(() => {
        void queryClient.clear();
        void refresh();
      }),
    [queryClient, refresh],
  );

  const acceptToken = useCallback(
    async (token: string) => {
      tokenStore.set(token);
      await queryClient.invalidateQueries();
      await refresh();
    },
    [queryClient, refresh],
  );

  const login = useCallback(
    async (username: string, password: string) => {
      const result = await api<{ token: string }>(`${API}/auth/login`, {
        method: "POST",
        json: { username, password },
        quiet401: true,
      });
      await acceptToken(result.token);
    },
    [acceptToken],
  );

  const logout = useCallback(async () => {
    try {
      await api(`${API}/auth/logout`, { method: "POST", quiet401: true });
    } catch {
      /* the token may already be invalid: logging out must still work */
    }
    tokenStore.set(null);
    queryClient.clear();
    await refresh();
  }, [queryClient, refresh]);

  const value = useMemo<AuthState>(
    () => ({
      config,
      me,
      loading,
      error,
      isAdmin: !!me?.is_admin,
      signedIn: !!me?.authenticated && me.kind !== "open",
      login,
      acceptToken,
      logout,
      refresh,
    }),
    [config, me, loading, error, login, acceptToken, logout, refresh],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}
