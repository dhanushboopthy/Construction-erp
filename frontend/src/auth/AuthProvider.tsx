import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";

import {
  api,
  json,
  refreshSession,
  setAccessToken,
  setRefreshEnabled,
  setSessionEndedHandler,
} from "@/api/client";
import type { SupportSessionStatus, TokenResponse, User } from "@/api/types";

import { AuthContext, type AuthState } from "./AuthContext";

/** The page a Duolink admin lands on. It must not try the refresh cookie first: that could be
 * a company user's session in the same browser, and it would replace the support token. */
export const SUPPORT_ENTRY_PATH = "/support-entry";

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [support, setSupport] = useState<SupportSessionStatus | null>(null);
  const [ready, setReady] = useState(false);

  // On load, try the refresh cookie so a page reload keeps the user signed in.
  useEffect(() => {
    setSessionEndedHandler(() => {
      setUser(null);
      setSupport(null);
    });
    if (window.location.pathname === SUPPORT_ENTRY_PATH) {
      setReady(true);
    } else {
      refreshSession()
        .then((data) => setUser(data?.user ?? null))
        .finally(() => setReady(true));
    }
    return () => setSessionEndedHandler(null);
  }, []);

  const signIn = useCallback(async (username: string, password: string) => {
    const data = await api<TokenResponse>("/auth/login", {
      method: "POST",
      body: json({ username, password }),
    });
    setAccessToken(data.access_token);
    setUser(data.user);
  }, []);

  const signOut = useCallback(async () => {
    try {
      await api<undefined>("/auth/logout", { method: "POST" });
    } finally {
      setAccessToken(null);
      setUser(null);
    }
  }, []);

  const changePassword = useCallback(async (current: string, next: string) => {
    await api<undefined>("/auth/change-password", {
      method: "POST",
      body: json({ current_password: current, new_password: next }),
    });
    setAccessToken(null);
    setUser(null);
  }, []);

  const reloadUser = useCallback(async () => {
    setUser(await api<User>("/auth/me"));
  }, []);

  const enterSupport = useCallback(async (token: string) => {
    setRefreshEnabled(false);
    setAccessToken(token);
    try {
      const [me, session] = await Promise.all([
        api<User>("/auth/me"),
        api<SupportSessionStatus>("/support-session"),
      ]);
      setUser(me);
      setSupport(session);
      return true;
    } catch {
      setAccessToken(null);
      setRefreshEnabled(true);
      return false;
    }
  }, []);

  const exitSupport = useCallback(async () => {
    try {
      await api<undefined>("/support-session/exit", { method: "POST" });
    } finally {
      setAccessToken(null);
      setRefreshEnabled(true);
      setUser(null);
      setSupport(null);
    }
  }, []);

  const value = useMemo<AuthState>(
    () => ({
      user,
      ready,
      support,
      signIn,
      signOut,
      changePassword,
      reloadUser,
      enterSupport,
      exitSupport,
    }),
    [user, ready, support, signIn, signOut, changePassword, reloadUser, enterSupport, exitSupport],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
