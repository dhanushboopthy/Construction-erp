import { createContext, useContext } from "react";

import type { Admin } from "./types";

export interface AdminAuthState {
  admin: Admin | null;
  ready: boolean;
  signIn: (email: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;
  /** Only a Super Admin changes things; Support reads. A courtesy: the server enforces it. */
  isSuperAdmin: boolean;
  /** Sets a new password. The server signs the admin out everywhere, this browser included. */
  changePassword: (current: string, next: string) => Promise<void>;
}

export const AdminAuthContext = createContext<AdminAuthState | null>(null);

export function useAdminAuth(): AdminAuthState {
  const value = useContext(AdminAuthContext);
  if (!value) throw new Error("useAdminAuth must be used inside <AdminAuthProvider>");
  return value;
}
