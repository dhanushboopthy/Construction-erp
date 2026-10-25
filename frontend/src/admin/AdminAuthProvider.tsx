import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";

import { json } from "@/api/client";

import { AdminAuthContext, type AdminAuthState } from "./AdminAuthContext";
import { adminApi, adminClient } from "./client";
import type { Admin, AdminTokenResponse } from "./types";

export function AdminAuthProvider({ children }: { children: ReactNode }) {
  const [admin, setAdmin] = useState<Admin | null>(null);
  const [ready, setReady] = useState(false);

  // On load, try the admin refresh cookie so a page reload keeps the admin signed in.
  useEffect(() => {
    adminClient.setSessionEndedHandler(() => setAdmin(null));
    adminClient
      .refreshSession()
      .then((data) => setAdmin(data?.admin ?? null))
      .finally(() => setReady(true));
    return () => adminClient.setSessionEndedHandler(null);
  }, []);

  const signIn = useCallback(async (email: string, password: string) => {
    const data = await adminApi<AdminTokenResponse>("/auth/login", {
      method: "POST",
      body: json({ email, password }),
    });
    adminClient.setAccessToken(data.access_token);
    setAdmin(data.admin);
  }, []);

  const signOut = useCallback(async () => {
    try {
      await adminApi<undefined>("/auth/logout", { method: "POST" });
    } finally {
      adminClient.setAccessToken(null);
      setAdmin(null);
    }
  }, []);

  const value = useMemo<AdminAuthState>(
    () => ({ admin, ready, signIn, signOut }),
    [admin, ready, signIn, signOut],
  );
  return <AdminAuthContext.Provider value={value}>{children}</AdminAuthContext.Provider>;
}
