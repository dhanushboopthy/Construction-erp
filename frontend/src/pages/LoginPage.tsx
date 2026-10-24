import { Factory } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Navigate, useLocation, useNavigate } from "react-router";

import { ApiError } from "@/api/client";
import { useTenant } from "@/api/setup";
import { useAuth } from "@/auth/AuthContext";
import { ThemeToggle } from "@/components/ThemeToggle";

import styles from "./LoginPage.module.css";

/** Answers of GET /tenant that mean nobody can sign in at this address (ADR 0011). */
const CLOSED = new Set(["TENANT_NOT_FOUND", "TENANT_SUSPENDED", "TENANT_CANCELLED"]);

export function LoginPage() {
  const { user, signIn } = useAuth();
  const tenant = useTenant();
  const closed =
    tenant.error instanceof ApiError && CLOSED.has(tenant.error.body.code)
      ? tenant.error.message
      : null;
  const navigate = useNavigate();
  const location = useLocation();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const from = (location.state as { from?: string } | null)?.from ?? "/";
  if (user) return <Navigate to={from} replace />;

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await signIn(username, password);
      void navigate(from, { replace: true });
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Cannot reach the server. Check the network.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className={styles.page}>
      <ThemeToggle className={styles.themeCorner} />
      <form
        className={styles.card}
        onSubmit={(e) => void onSubmit(e)}
        aria-describedby="login-error"
      >
        <span className={styles.appIcon} aria-hidden="true">
          <Factory size={30} strokeWidth={2} />
        </span>
        <h1 className={styles.title}>Sign in to the shop</h1>
        <p className={styles.subtitle}>{tenant.data?.name ?? "Construction ERP"}</p>
        <label className={styles.field}>
          Username
          <input
            autoFocus
            autoComplete="username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            disabled={closed !== null}
            required
          />
        </label>
        <label className={styles.field}>
          Password
          <input
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            disabled={closed !== null}
            required
          />
        </label>
        <p id="login-error" role="alert" className={styles.error}>
          {closed ?? error}
        </p>
        <button
          type="submit"
          className={styles.submit}
          disabled={busy || closed !== null}
          aria-busy={busy}
        >
          {busy ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </main>
  );
}
