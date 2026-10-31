import { ShieldCheck } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Navigate, useLocation, useNavigate } from "react-router";

import { ApiError } from "@/api/client";
import { ThemeToggle } from "@/components/ThemeToggle";
import styles from "@/pages/LoginPage.module.css";

import { useAdminAuth } from "../AdminAuthContext";

export function AdminLoginPage() {
  const { admin, signIn } = useAdminAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const state = location.state as { from?: string; changed?: boolean } | null;
  const from = state?.from ?? "/admin";
  if (admin) return <Navigate to={from} replace />;

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await signIn(email, password);
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
        aria-describedby="admin-login-error"
      >
        <span className={styles.appIcon} aria-hidden="true">
          <ShieldCheck size={30} strokeWidth={2} />
        </span>
        <h1 className={styles.title}>Duolink admin</h1>
        <p className={styles.subtitle}>
          For Duolink staff. Shop users sign in at their own address.
        </p>
        {state?.changed ? (
          <p role="status" className={styles.subtitle}>
            Password changed. Sign in with the new one.
          </p>
        ) : null}
        <label className={styles.field}>
          Email
          <input
            autoFocus
            type="email"
            autoComplete="username"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
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
            required
          />
        </label>
        <p id="admin-login-error" role="alert" className={styles.error}>
          {error}
        </p>
        <button type="submit" className={styles.submit} disabled={busy} aria-busy={busy}>
          {busy ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </main>
  );
}
