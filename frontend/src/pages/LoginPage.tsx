import { useState, type FormEvent } from "react";
import { Navigate, useLocation, useNavigate } from "react-router";

import { ApiError } from "@/api/client";
import { useTenant } from "@/api/tenant";
import { useAuth } from "@/auth/AuthContext";
import { BrandMark } from "@/components/BrandMark";
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

  const state = location.state as { from?: string; changed?: boolean } | null;
  const from = state?.from ?? "/";
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

  // Whose shop this is comes from the API, before anyone has signed in. If it cannot be read the
  // page still works and says only the product name.
  const name = tenant.data?.name;

  return (
    <main className={styles.page}>
      <ThemeToggle className={styles.themeCorner} />
      <aside className={styles.brand} aria-label="About this shop">
        <BrandMark name={name} logoUrl={tenant.data?.logo_url} className={styles.appIcon} />
        <p className={styles.brandName}>{name ?? "Construction ERP"}</p>
        {tenant.data ? <p className={styles.tagline}>{tenant.data.tagline}</p> : null}
        <p className={styles.product}>Construction ERP</p>
      </aside>
      <div className={styles.formSide}>
        <form
          className={styles.card}
          onSubmit={(e) => void onSubmit(e)}
          aria-describedby="login-error"
        >
          <h1 className={styles.title}>Sign in to the shop</h1>
          <p className={styles.subtitle}>{name ?? "Construction ERP"}</p>
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
          {state?.changed ? (
            <p role="status" className={styles.subtitle}>
              Password changed. Sign in with the new one.
            </p>
          ) : null}
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
      </div>
    </main>
  );
}
