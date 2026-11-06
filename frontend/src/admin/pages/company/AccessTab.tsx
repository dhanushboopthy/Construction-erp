import { useEffect, useState, type FormEvent } from "react";

import { toFormError } from "@/api/errors";
import { Button } from "@/components/Button";
import { TextField } from "@/components/Field";
import styles from "@/components/Ledger.module.css";
import { formatDateTime, formatTimeLeft } from "@/lib/format";

import { useAccessStatus, useEnterCompany } from "../../api";
import { useAdminAuth } from "../../AdminAuthContext";
import { Badge } from "../../Badge";
import { SupportSessions } from "../../SupportSessions";
import type { TenantDetail } from "../../types";

/** The company's owner decides whether Duolink may look inside; a Super Admin then enters
 * read-only (M23). Nobody here can turn the grant on or off. */
export function AccessTab({ tenant }: { tenant: TenantDetail }) {
  const { isSuperAdmin } = useAdminAuth();
  const status = useAccessStatus(tenant.id);
  const enter = useEnterCompany(tenant.id);
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [now, setNow] = useState(() => Date.now());
  const ends = status.data?.ends_at ?? null;

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 15_000);
    return () => window.clearInterval(timer);
  }, []);

  if (status.isPending) return <p role="status">Loading company access…</p>;
  if (status.isError)
    return <p className={styles.formError}>Company access could not be loaded.</p>;

  const a = status.data;
  const left = ends ? Math.max(0, Math.floor((new Date(ends).getTime() - now) / 1000)) : 0;
  const live = a.live && left > 0;

  async function onEnter(event: FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      const started = await enter.mutateAsync(reason.trim());
      setReason("");
      window.open(started.entry_url, "_blank", "noopener");
    } catch (err) {
      setError(toFormError(err).message);
    }
  }

  return (
    <div className={styles.stack}>
      <section className={styles.panel} aria-labelledby="access-title">
        <div className={styles.panelHead}>
          <h2 id="access-title">Owner-granted access</h2>
          <Badge tone={live ? "good" : "neutral"}>{live ? "Access granted" : "No access"}</Badge>
        </div>
        {live ? (
          <p>
            The owner ({a.granted_by_name}) allowed Duolink in until {formatDateTime(a.ends_at)},{" "}
            {formatTimeLeft(left)} left. {a.owner_only_figures ? "Cost and margin are shown. " : ""}
            Reason given: {a.reason}
            {a.ticket_number ? ` (ticket ${a.ticket_number})` : ""}.
          </p>
        ) : (
          <p>
            The owner has not allowed Duolink in, or the time has ended. Ask the owner to turn on
            Settings, Duolink support access.
          </p>
        )}
        <p className={styles.note}>
          Entering is read-only: nothing can be saved, and every request is logged.{" "}
          {a.open_sessions} {a.open_sessions === 1 ? "session is" : "sessions are"} open now.
        </p>
        {isSuperAdmin ? (
          <form onSubmit={(e) => void onEnter(e)}>
            <TextField
              label="Why are you entering"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              required
              minLength={3}
              maxLength={300}
            />
            <div>
              <Button type="submit" variant="primary" disabled={!live || enter.isPending}>
                Enter company (read-only)
              </Button>
            </div>
          </form>
        ) : (
          <p className={styles.note}>Only a Super Admin can enter a company.</p>
        )}
        {error ? (
          <p role="alert" className={styles.formError}>
            {error}
          </p>
        ) : null}
      </section>
      <section className={styles.panel} aria-labelledby="visits-title">
        <div className={styles.panelHead}>
          <h2 id="visits-title">Visits to this company</h2>
        </div>
        <SupportSessions tenantId={tenant.id} />
      </section>
    </div>
  );
}
