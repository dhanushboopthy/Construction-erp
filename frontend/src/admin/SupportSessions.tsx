import { Link } from "react-router";

import styles from "@/components/Ledger.module.css";
import { formatDateTime } from "@/lib/format";

import { useSupportSessions } from "./api";
import { Badge } from "./Badge";
import type { Tone } from "./labels";
import type { SupportSessionRow } from "./types";

const STATUS: Record<SupportSessionRow["status"], { label: string; tone: Tone }> = {
  open: { label: "Inside now", tone: "good" },
  ended: { label: "Ended", tone: "neutral" },
  stale: { label: "Never left: window closed", tone: "warn" },
};

const END_REASON: Record<string, string> = {
  exited: "Admin left",
  revoked: "Owner turned access off",
  grant_ended: "Grant ran out",
  replaced: "Entered again",
  admin_not_allowed: "Admin no longer allowed",
};

/** Every visit by a Duolink admin to a company, or to one company: who, when, how many requests.
 * No page content or amount is shown, ever (ADR 0013). */
export function SupportSessions({ tenantId }: { tenantId?: number }) {
  const sessions = useSupportSessions({ tenant_id: tenantId });
  if (sessions.isPending) return <p role="status">Loading company access…</p>;
  if (sessions.isError) {
    return <p className={styles.formError}>Company access could not be loaded.</p>;
  }
  const page = sessions.data;
  return (
    <div className={styles.tableWrap}>
      <table className={styles.table}>
        <thead>
          <tr>
            <th scope="col">Entered</th>
            <th scope="col">Admin</th>
            <th scope="col">Company</th>
            <th scope="col">Reason</th>
            <th scope="col">Requests</th>
            <th scope="col">Status</th>
          </tr>
        </thead>
        <tbody>
          {page.items.length ? (
            page.items.map((s) => (
              <tr key={s.id}>
                <td>{formatDateTime(s.started_at)}</td>
                <td>{s.admin_name}</td>
                <td>
                  <Link to={`/admin/companies/${s.tenant_id}`}>{s.tenant_slug}</Link>
                </td>
                <td className={styles.sub}>{s.reason}</td>
                <td>{s.request_count}</td>
                <td>
                  <Badge tone={STATUS[s.status].tone}>{STATUS[s.status].label}</Badge>
                  <div className={styles.sub}>
                    {s.ended_at ? `Until ${formatDateTime(s.ended_at)}` : "Open"}
                    {s.end_reason ? `, ${END_REASON[s.end_reason] ?? s.end_reason}` : ""}
                    {s.owner_only_figures ? ", with cost and margin" : ""}
                  </div>
                </td>
              </tr>
            ))
          ) : (
            <tr>
              <td colSpan={6} className={styles.empty}>
                No admin has entered a company yet.
              </td>
            </tr>
          )}
        </tbody>
      </table>
      <p className={styles.results}>
        {page.total} {page.total === 1 ? "visit" : "visits"}, {page.open} open
        {page.stale ? `, ${page.stale} never ended` : ""}
      </p>
    </div>
  );
}
