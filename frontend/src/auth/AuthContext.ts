import { createContext, useContext } from "react";

import type { User } from "@/api/types";

export interface AuthState {
  user: User | null;
  ready: boolean;
  signIn: (username: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;
  /** Re-read the signed-in user, e.g. after the owner edits their own name. */
  reloadUser: () => Promise<void>;
}

export const AuthContext = createContext<AuthState | null>(null);

export function useAuth(): AuthState {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside <AuthProvider>");
  return value;
}
