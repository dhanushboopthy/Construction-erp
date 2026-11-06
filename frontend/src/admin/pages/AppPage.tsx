import { useEffect, useState, type FormEvent } from "react";

import { toFormError } from "@/api/errors";
import { Button } from "@/components/Button";
import { TextField } from "@/components/Field";
import styles from "@/components/Ledger.module.css";
import { formatDateTime } from "@/lib/format";
import { checkForUpdate, promptInstall, shellCached, usePwa } from "@/pwa/updates";

import { useAppUpdate, useForceUpdate } from "../api";
import { useAdminAuth } from "../AdminAuthContext";
import { Badge } from "../Badge";

const WORKER_LABEL = {
  unsupported: "Not supported by this browser",
  none: "Not registered",
  installing: "Installing",
  active: "Running",
} as const;

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <tr>
      <th scope="row">{label}</th>
      <td>{children}</td>
    </tr>
  );
}

/**
 * App and updates (Milestone 29): the build of the backend and of the frontend, how this
 * browser stands (can it install the app, is the service worker running, is the app shell ready
 * for no connection, is an update waiting), and Force update for a Super Admin.
 */
export function AppPage() {
  const { isSuperAdmin } = useAdminAuth();
  const pwa = usePwa();
  const info = useAppUpdate();
  const force = useForceUpdate();
  const [shell, setShell] = useState<boolean | null>(null);
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<number | null>(null);

  useEffect(() => {
    let live = true;
    void shellCached().then((ready) => live && setShell(ready));
    return () => {
      live = false;
    };
  }, [pwa.worker, pwa.offlineReady]);

  async function onForce(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setDone(null);
    try {
      const result = await force.mutateAsync(reason.trim() ? { reason: reason.trim() } : {});
      setDone(result.generation);
      setReason("");
    } catch (err) {
      setError(toFormError(err).message);
    }
  }

  const installed = pwa.installed;
  return (
    <section aria-labelledby="app-title" className={styles.page}>
      <h1 id="app-title" className={styles.title}>
        App and updates
      </h1>

      <h2 className={styles.panelHead}>Builds</h2>
      <div className={styles.tableWrap}>
        <table className={styles.table}>
          <tbody>
            <Row label="Frontend">
              {__APP_VERSION__} · build {__APP_BUILD__}
            </Row>
            <Row label="Backend">
              {info.isPending
                ? "Loading…"
                : info.isError
                  ? "Could not be loaded"
                  : `${info.data.backend_version} · build ${info.data.backend_build}`}
            </Row>
          </tbody>
        </table>
      </div>

      <h2 className={styles.panelHead}>This browser</h2>
      <div className={styles.tableWrap}>
        <table className={styles.table}>
          <tbody>
            <Row label="Can be installed">
              {installed ? (
                <Badge tone="good">Installed as an app</Badge>
              ) : pwa.installable ? (
                <>
                  <Badge tone="good">Yes</Badge>{" "}
                  <Button variant="secondary" onClick={() => void promptInstall()}>
                    Install
                  </Button>
                </>
              ) : (
                <Badge tone="neutral">Not offered right now</Badge>
              )}
            </Row>
            <Row label="Service worker">
              <Badge tone={pwa.worker === "active" ? "good" : "neutral"}>
                {WORKER_LABEL[pwa.worker]}
              </Badge>
            </Row>
            <Row label="Offline shell">
              {shell === null ? (
                "Checking…"
              ) : shell ? (
                <Badge tone="good">Ready</Badge>
              ) : (
                <Badge tone="warn">Not ready</Badge>
              )}
            </Row>
            <Row label="Update waiting">
              {pwa.updateWaiting ? (
                <Badge tone="accent">Yes, a new build is waiting</Badge>
              ) : (
                <Badge tone="neutral">No</Badge>
              )}{" "}
              <Button variant="ghost" onClick={() => void checkForUpdate()}>
                Check now
              </Button>
            </Row>
            <Row label="Browser">{navigator.userAgent}</Row>
          </tbody>
        </table>
      </div>

      <h2 className={styles.panelHead}>Force update</h2>
      <p>
        Generation {info.data?.generation ?? "…"}
        {info.data?.forced_at
          ? `, last forced ${formatDateTime(info.data.forced_at)} by ${info.data.forced_by ?? "someone"}`
          : ", never forced"}
        .
      </p>
      <p>
        Every open company window looks for a new build within minutes instead of at its next
        half-hourly check. Nobody is reloaded: a new version shows an &ldquo;Update now&rdquo; toast
        and waits, and never reloads a form with unsaved changes.
      </p>
      {isSuperAdmin ? (
        <form className={styles.stack} onSubmit={(e) => void onForce(e)} noValidate>
          <TextField
            label="Reason (optional)"
            value={reason}
            maxLength={200}
            onChange={(e) => setReason(e.target.value)}
          />
          {error ? (
            <p className={styles.formError} role="alert">
              {error}
            </p>
          ) : null}
          {done !== null ? <p role="status">Done. Generation is now {done}.</p> : null}
          <div className={styles.actions}>
            <Button type="submit" variant="primary" disabled={force.isPending}>
              Force update
            </Button>
          </div>
        </form>
      ) : (
        <p>Only a Super Admin can force an update.</p>
      )}
    </section>
  );
}
