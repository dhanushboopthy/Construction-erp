import { createContext, useContext } from "react";

import type { SupportSessionStatus, User } from "@/api/types";

export interface AuthState {
  user: User | null;
  ready: boolean;
  /** Set while a Duolink Super Admin is inside this company under the owner's grant (M23):
   * read-only, with a banner. The token lives in memory only. */
  support: SupportSessionStatus | null;
  signIn: (username: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;
  /** Sets a new password. The server ends every session, this browser's included. */
  changePassword: (current: string, next: string) => Promise<void>;
  /** Re-read the signed-in user, e.g. after the owner edits their own name. */
  reloadUser: () => Promise<void>;
  /** Start a support session with the token from /support-entry. Resolves false when the
   * server refuses it (ended, revoked, wrong company). */
  enterSupport: (token: string) => Promise<boolean>;
  /** Leave the support session: tells the server, then forgets the token. */
  exitSupport: () => Promise<void>;
}

export const AuthContext = createContext<AuthState | null>(null);

export function useAuth(): AuthState {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside <AuthProvider>");
  return value;
}
