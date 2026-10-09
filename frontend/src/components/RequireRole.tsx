import type { ReactNode } from "react";

import type { Role } from "@/api/types";
import { useAuth } from "@/auth/AuthContext";

/**
 * Screen-level guard. The API enforces every permission on its own (rule B4); this only stops
 * a typed URL from showing a screen whose requests would all answer 403.
 */
export function RequireRole({ roles, children }: { roles: Role[]; children: ReactNode }) {
  const { user } = useAuth();
  if (!user || !roles.includes(user.role)) {
    return (
      <section aria-labelledby="denied-title">
        <h1 id="denied-title">Not available for your role</h1>
        <p>Ask the owner if you need this screen. Use Alt+1 to go back to Today.</p>
      </section>
    );
  }
  return children;
}
