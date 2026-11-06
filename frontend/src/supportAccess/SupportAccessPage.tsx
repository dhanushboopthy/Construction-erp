import { useEffect, useState, type FormEvent } from "react";

import { toFormError } from "@/api/errors";
import type { AccessGrant, GrantCreate, SupportVisit } from "@/api/types";
import { Button } from "@/components/Button";
import { CheckField, SelectField, TextAreaField } from "@/components/Field";
import styles from "@/components/Ledger.module.css";
import { formatDateTime, formatTimeLeft } from "@/lib/format";
import { useTickets } from "@/support/api";

import { useAccessOverview, useGrantAccess, useRevokeAccess, useVisits } from "./api";

const DURATION_LABEL: Record<number, string> = {
  1: "1 hour",
  4: "4 hours",
  24: "24 hours",
  72: "72 hours (3 days)",
};

const VISIT_STATUS: Record<SupportVisit["status"], string> = {
  open: "Inside now",
  ended: "Ended",
  stale: "Ended (window closed)",
};

const END_REASON: Record<string, string> = {
  exited: "Duolink left",
  revoked: "You turned access off",
  grant_ended: "Time ran out",
  replaced: "Duolink entered again",
  admin_not_allowed: "Duolink staff change",
};

/** Seconds left on a live grant, counted down on this screen between the server's answers. */
function useSecondsLeft(grant: AccessGrant | null | undefined): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!grant) return;
    setNow(Date.now());
    const timer = window.setInterval(() => setNow(Date.now()), 15_000);
    return () => window.clearInterval(timer);
  }, [grant]);
  if (!grant) return 0;
  return Math.max(0, Math.floor((new Date(grant.ends_at).getTime() - now) / 1000));
}

/** Settings, Duolink support access (M23, owner only): let Duolink look, read-only, for a set
 * time; see who came; switch it off at once. */
export function SupportAccessPage() {
  const overview = useAccessOverview();
  const visits = useVisits();
  const tickets = useTickets("");
  const grant = useGrantAccess();
  const revoke = useRevokeAccess();
  const [hours, setHours] = useState<GrantCreate["duration_hours"]>(4);
  const [costs, setCosts] = useState(false);
  const [reason, setReason] = useState("");
  const [ticketId, setTicketId] = useState("");
  const [error, setError] = useState<string | null>(null);
  const live = overview.data?.live ?? null;
  const left = useSecondsLeft(live);

  async function onGrant(event: FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      await grant.mutateAsync({
        duration_hours: hours,
        include_costs: costs,
        reason: reason.trim(),
        ticket_id: ticketId ? Number(ticketId) : null,
      });
      setReason("");
      setTicketId("");
      setCosts(false);
    } catch (err) {
      setError(toFormError(err).message);
    }
  }

  async function onRevoke() {
    setError(null);
    try {
      await revoke.mutateAsync();
    } catch (err) {
      setError(toFormError(err).message);
    }
  }

  if (overview.isPending) return <p role="status">Loading…</p>;
  if (overview.isError) {
    return <p className={styles.formError}>Support access could not be loaded.</p>;
  }

  return (
    <div className={styles.stack}>
      <section className={styles.panel} aria-labelledby="access-title">
        <div className={styles.panelHead}>
          <h2 id="access-title">Duolink support access</h2>
        </div>
        <p className={styles.note}>
          Duolink can only look inside your company when you let it. While access is on, a Duolink
          Super Admin sees the screens you see, read-only: they cannot save, change a user or a
          password, or change this setting. You can switch it off at any moment, and every visit is
          listed below.
        </p>
        {live ? (
          <div role="status" aria-label="Support access is on">
            <p>
              <strong>Access is on</strong> until {formatDateTime(live.ends_at)} (
              {formatTimeLeft(left)} left). {live.include_costs ? "Cost and margin are shown." : ""}
            </p>
            <p className={styles.note}>
              Given by {live.granted_by_name}: {live.reason}
              {live.ticket_number ? ` (ticket ${live.ticket_number})` : ""}
            </p>
            <Button
              type="button"
              variant="secondary"
              onClick={() => void onRevoke()}
              disabled={revoke.isPending}
            >
              Turn off now
            </Button>
          </div>
        ) : (
          <p role="status">Access is off. Duolink cannot enter this company.</p>
        )}
        {error ? (
          <p role="alert" className={styles.formError}>
            {error}
          </p>
        ) : null}
      </section>

      <section className={styles.panel} aria-labelledby="grant-title">
        <div className={styles.panelHead}>
          <h2 id="grant-title">{live ? "Replace the current access" : "Let Duolink in"}</h2>
        </div>
        <form onSubmit={(e) => void onGrant(e)}>
          <SelectField
            label="For how long"
            value={hours}
            onChange={(e) => setHours(Number(e.target.value) as GrantCreate["duration_hours"])}
          >
            {overview.data.durations.map((d) => (
              <option key={d} value={d}>
                {DURATION_LABEL[d] ?? `${d} hours`}
              </option>
            ))}
          </SelectField>
          <TextAreaField
            label="What do you want help with"
            hint="Duolink sees this reason."
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            required
            minLength={3}
            maxLength={300}
          />
          <SelectField
            label="Ticket (optional)"
            value={ticketId}
            onChange={(e) => setTicketId(e.target.value)}
          >
            <option value="">No ticket</option>
            {(tickets.data?.items ?? []).map((t) => (
              <option key={t.id} value={t.id}>
                {t.number} · {t.subject}
              </option>
            ))}
          </SelectField>
          <CheckField
            label="Show cost and margin"
            hint="Off by default. Duolink then sees the screens as a counter user would, without cost, margin or profit."
            checked={costs}
            onChange={(e) => setCosts(e.target.checked)}
          />
          <div>
            <Button type="submit" variant="primary" allowWhenReadOnly disabled={grant.isPending}>
              {live ? "Replace access" : "Give access"}
            </Button>
          </div>
        </form>
      </section>

      <section className={styles.panel} aria-labelledby="visits-title">
        <div className={styles.panelHead}>
          <h2 id="visits-title">Who from Duolink came in</h2>
        </div>
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th scope="col">Who</th>
                <th scope="col">Entered</th>
                <th scope="col">Left</th>
                <th scope="col">Pages opened</th>
                <th scope="col">Status</th>
              </tr>
            </thead>
            <tbody>
              {(visits.data ?? []).length ? (
                (visits.data ?? []).map((v) => (
                  <tr key={v.id}>
                    <td>
                      {v.admin_name}
                      <div className={styles.sub}>{v.reason}</div>
                    </td>
                    <td>{formatDateTime(v.started_at)}</td>
                    <td>{formatDateTime(v.ended_at)}</td>
                    <td>{v.request_count}</td>
                    <td>
                      {VISIT_STATUS[v.status]}
                      {v.end_reason ? (
                        <div className={styles.sub}>{END_REASON[v.end_reason] ?? v.end_reason}</div>
                      ) : null}
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={5} className={styles.empty}>
                    Duolink has not entered this company.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
