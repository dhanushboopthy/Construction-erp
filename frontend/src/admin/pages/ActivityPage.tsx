import { Link, useSearchParams } from "react-router";

import { SelectField } from "@/components/Field";
import styles from "@/components/Ledger.module.css";
import { formatDateTime } from "@/lib/format";

import { useAdminActions, useSignIns } from "../api";
import { Badge } from "../Badge";
import { ACTION, SIGN_IN } from "../labels";
import type { AuditFilters } from "../types";

const VIEWS = [
  { value: "sign-ins", label: "Sign-ins at companies" },
  { value: "admin", label: "What Duolink admins did" },
] as const;

export function ActivityPage() {
  const [params, setParams] = useSearchParams();
  const view = params.get("view") === "admin" ? "admin" : "sign-ins";
  const action = params.get("action") ?? "";

  return (
    <section aria-labelledby="activity-title" className={styles.page}>
      <h1 id="activity-title" className={styles.title}>
        Activity
      </h1>
      <nav aria-label="Activity views">
        <ul className={styles.tabs}>
          {VIEWS.map((v) => (
            <li key={v.value}>
              <Link
                to={`/admin/activity?view=${v.value}`}
                className={view === v.value ? styles.tabActive : styles.tab}
                aria-current={view === v.value ? "page" : undefined}
              >
                {v.label}
              </Link>
            </li>
          ))}
        </ul>
      </nav>
      {view === "admin" ? (
        <AdminActions />
      ) : (
        <>
          <div className={styles.filters}>
            <SelectField
              label="Show"
              value={action}
              onChange={(e) => {
                const next = new URLSearchParams(params);
                if (e.target.value) next.set("action", e.target.value);
                else next.delete("action");
                setParams(next, { replace: true });
              }}
            >
              <option value="">Every sign-in</option>
              {Object.entries(SIGN_IN).map(([key, s]) => (
                <option key={key} value={key}>
                  {s.label}
                </option>
              ))}
            </SelectField>
          </div>
          <SignIns action={action} />
        </>
      )}
    </section>
  );
}

/** Sign-ins at every company, or at one when `tenantId` is given (the company page's tab). */
export function SignIns({
  action = "",
  tenantId,
  dateFrom,
  dateTo,
}: {
  action?: string;
  tenantId?: number;
  dateFrom?: string;
  dateTo?: string;
}) {
  const events = useSignIns({
    action: action || undefined,
    tenant_id: tenantId,
    date_from: dateFrom || undefined,
    date_to: dateTo || undefined,
  });
  if (events.isPending) return <p role="status">Loading sign-ins…</p>;
  if (events.isError) return <p className={styles.formError}>Sign-ins could not be loaded.</p>;
  return (
    <div className={styles.tableWrap}>
      <table className={styles.table}>
        <thead>
          <tr>
            <th scope="col">When</th>
            <th scope="col">Company</th>
            <th scope="col">Username</th>
            <th scope="col">What happened</th>
            <th scope="col">From</th>
          </tr>
        </thead>
        <tbody>
          {events.data.items.length ? (
            events.data.items.map((e, i) => {
              const kind = SIGN_IN[e.action] ?? { label: e.action, tone: "neutral" as const };
              return (
                <tr key={`${e.at}-${i}`}>
                  <td>{formatDateTime(e.at)}</td>
                  <td>
                    <Link to={`/admin/companies/${e.tenant_id}`}>{e.tenant_slug}</Link>
                  </td>
                  <td>{e.username ?? "—"}</td>
                  <td>
                    <Badge tone={kind.tone}>{kind.label}</Badge>
                  </td>
                  <td>{e.ip ?? "—"}</td>
                </tr>
              );
            })
          ) : (
            <tr>
              <td colSpan={5} className={styles.empty}>
                Nothing yet. Sign-ins appear here as people use the ERP.
              </td>
            </tr>
          )}
        </tbody>
      </table>
      <p className={styles.results}>Newest first, the last {events.data.items.length} shown</p>
    </div>
  );
}

/** "reason: Unpaid invoice; sessions_ended: 3" from an audit entry's details. */
function describe(details: Record<string, unknown> | null): string {
  const entries = Object.entries(details ?? {});
  if (!entries.length) return "—";
  return entries
    .map(([k, v]) => `${k}: ${typeof v === "object" ? JSON.stringify(v) : String(v)}`)
    .join("; ");
}

/** What admins did, everywhere or at one company. */
export function AdminActions({
  tenantId,
  filters = {},
}: {
  tenantId?: number;
  filters?: AuditFilters;
}) {
  const entries = useAdminActions({ ...filters, tenant_id: tenantId ?? filters.tenant_id });
  if (entries.isPending) return <p role="status">Loading admin actions…</p>;
  if (entries.isError) {
    return <p className={styles.formError}>Admin actions could not be loaded.</p>;
  }
  return (
    <div className={styles.tableWrap}>
      <table className={styles.table}>
        <thead>
          <tr>
            <th scope="col">When</th>
            <th scope="col">Admin</th>
            <th scope="col">Action</th>
            <th scope="col">Company</th>
            <th scope="col">Details</th>
          </tr>
        </thead>
        <tbody>
          {entries.data.items.length ? (
            entries.data.items.map((a) => (
              <tr key={a.id}>
                <td>{formatDateTime(a.at)}</td>
                <td>{a.admin_email ?? "—"}</td>
                <td>{ACTION[a.action]}</td>
                <td>{a.tenant_slug ?? "—"}</td>
                <td className={styles.sub}>{describe(a.details)}</td>
              </tr>
            ))
          ) : (
            <tr>
              <td colSpan={5} className={styles.empty}>
                No admin actions yet.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
