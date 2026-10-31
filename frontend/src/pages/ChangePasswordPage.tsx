import { useState, type FormEvent } from "react";
import { Navigate } from "react-router";

import { ApiError } from "@/api/client";
import { useTenant } from "@/api/tenant";
import { useAuth } from "@/auth/AuthContext";
import { BrandMark } from "@/components/BrandMark";
import { ThemeToggle } from "@/components/ThemeToggle";

import styles from "./LoginPage.module.css";

const MIN_PASSWORD = 8; // backend app/core/security.py MIN_PASSWORD_LENGTH

/** Where a user with a temporary password lands (Duolink set it when it onboarded the company).
 * Nothing else opens until they choose their own; the server refuses every other call. */
export function ChangePasswordPage() {
  const { user, ready, changePassword } = useAuth();
  const tenant = useTenant();
  const name = tenant.data?.name;
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [again, setAgain] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);

  // The change signs this browser out; the sign-in page says so.
  if (done) return <Navigate to="/login" replace state={{ changed: true }} />;
  if (!ready) return <p role="status">Loading…</p>;
  if (!user) return <Navigate to="/login" replace />;

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    if (next.length < MIN_PASSWORD) {
      setError(`Use at least ${MIN_PASSWORD} characters.`);
      return;
    }
    if (next !== again) {
      setError("The two new passwords are not the same.");
      return;
    }
    setBusy(true);
    try {
      await changePassword(current, next);
      setDone(true);
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
      <aside className={styles.brand} aria-label="About this shop">
        <BrandMark name={name} logoUrl={tenant.data?.logo_url} className={styles.appIcon} />
        <p className={styles.brandName}>{name ?? "Construction ERP"}</p>
        <p className={styles.product}>Construction ERP</p>
      </aside>
      <div className={styles.formSide}>
        <form
          className={styles.card}
          onSubmit={(e) => void onSubmit(e)}
          aria-describedby="change-password-error"
        >
          <h1 className={styles.title}>Choose a new password</h1>
          <p className={styles.subtitle}>
            {user.must_change_password
              ? "You signed in with a temporary password. Choose your own to continue."
              : "You will be signed out and asked to sign in again."}
          </p>
          <label className={styles.field}>
            Temporary password
            <input
              autoFocus
              type="password"
              autoComplete="current-password"
              value={current}
              onChange={(e) => setCurrent(e.target.value)}
              required
            />
          </label>
          <label className={styles.field}>
            New password
            <input
              type="password"
              autoComplete="new-password"
              value={next}
              onChange={(e) => setNext(e.target.value)}
              required
            />
          </label>
          <label className={styles.field}>
            New password again
            <input
              type="password"
              autoComplete="new-password"
              value={again}
              onChange={(e) => setAgain(e.target.value)}
              required
            />
          </label>
          <p id="change-password-error" role="alert" className={styles.error}>
            {error}
          </p>
          <button type="submit" className={styles.submit} disabled={busy} aria-busy={busy}>
            {busy ? "Saving…" : "Change password"}
          </button>
        </form>
      </div>
    </main>
  );
}
