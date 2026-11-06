import { useEffect, useRef, useState } from "react";
import { Navigate } from "react-router";

import { useAuth } from "@/auth/AuthContext";

/**
 * Where a Duolink Super Admin lands: /support-entry#token=... The token is in the fragment, so
 * it never reaches a server log. It is read once, taken out of the address bar and the history
 * at once, and kept in memory only: a reload ends the visit, and the admin enters again.
 */
export function SupportEntryPage() {
  const { enterSupport, support } = useAuth();
  const [failed, setFailed] = useState(false);
  const started = useRef(false);

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    const token = new URLSearchParams(window.location.hash.slice(1)).get("token");
    window.history.replaceState(null, "", window.location.pathname);
    if (!token) {
      setFailed(true);
      return;
    }
    void enterSupport(token).then((ok) => setFailed(!ok));
  }, [enterSupport]);

  if (support) return <Navigate to="/" replace />;
  if (failed) {
    return (
      <main style={{ padding: "var(--space-7)" }}>
        <h1>This support link has ended</h1>
        <p role="alert">
          It is not valid any more: the owner may have turned support access off, or the time ran
          out. Enter the company again from the Duolink admin.
        </p>
      </main>
    );
  }
  return <p role="status">Opening the company…</p>;
}
