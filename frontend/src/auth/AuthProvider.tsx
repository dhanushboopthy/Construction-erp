import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";

import { api, json, refreshSession, setAccessToken, setSessionEndedHandler } from "@/api/client";
import type { TokenResponse, User } from "@/api/types";

import { AuthContext, type AuthState } from "./AuthContext";

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [ready, setReady] = useState(false);

  // On load, try the refresh cookie so a page reload keeps the user signed in.
  useEffect(() => {
    setSessionEndedHandler(() => setUser(null));
    refreshSession()
      .then((data) => setUser(data?.user ?? null))
      .finally(() => setReady(true));
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

  const reloadUser = useCallback(async () => {
    setUser(await api<User>("/auth/me"));
  }, []);

  const value = useMemo<AuthState>(
    () => ({ user, ready, signIn, signOut, reloadUser }),
    [user, ready, signIn, signOut, reloadUser],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
