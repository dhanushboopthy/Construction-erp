import { useState } from "react";
import { Link, useSearchParams } from "react-router";

import { Button } from "@/components/Button";
import { SelectField } from "@/components/Field";
import styles from "@/components/Ledger.module.css";
import { moveRowFocus } from "@/hooks/useKeys";
import { formatDay } from "@/lib/format";

import { SUBSCRIPTION_PAGE_SIZE, usePlans, useSubscriptions } from "../api";
import adminStyles from "../Admin.module.css";
import { useAdminAuth } from "../AdminAuthContext";
import { Badge } from "../Badge";
import { SUBSCRIPTION, SUBSCRIPTION_ORDER, daysLeftLabel, durationLabel, rupees } from "../labels";
import { CancelSubscriptionDialog, RenewDialog, type RenewTarget } from "../SubscriptionDialogs";
import type { SubscriptionRow } from "../types";

const WINDOWS = [7, 15, 30, 60];

type Asking = { kind: "renew" | "cancel"; row: SubscriptionRow } | null;

/** Who is paid up, who is about to lapse and who has lapsed. Support reads; a Super Admin renews
 * and cancels. */
export function SubscriptionsPage() {
  const { isSuperAdmin } = useAdminAuth();
  const [params, setParams] = useSearchParams();
  const status = params.get("status") ?? "";
  const plan = params.get("plan") ?? "";
  const expiring = params.get("expiring_within") ?? "";
  const page = Math.max(0, Number(params.get("page") ?? 0) || 0);
  const plans = usePlans();
  const subs = useSubscriptions({
    status,
    plan,
    expiring_within: expiring,
    offset: page * SUBSCRIPTION_PAGE_SIZE,
  });
  const [asking, setAsking] = useState<Asking>(null);

  const setFilter = (key: string, value: string) =>
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        if (value) next.set(key, value);
        else next.delete(key);
        if (key !== "page") next.delete("page");
        return next;
      },
      { replace: true },
    );

  const target = (row: SubscriptionRow): RenewTarget => ({
    id: row.id,
    tenant_name: row.tenant_name,
    plan_id: row.plan_id,
  });
  const columns = isSuperAdmin ? 7 : 6;

  return (
    <section aria-labelledby="subscriptions-title" className={styles.page}>
      <div className={styles.toolbar}>
        <h1 id="subscriptions-title" className={styles.title}>
          Subscriptions
        </h1>
        <p className={styles.keys}>↑↓ move · Enter open</p>
      </div>

      <form className={styles.filters} role="search" onSubmit={(e) => e.preventDefault()}>
        <SelectField
          label="Status"
          value={status}
          onChange={(e) => setFilter("status", e.target.value)}
        >
          <option value="">Any status</option>
          {SUBSCRIPTION_ORDER.map((s) => (
            <option key={s} value={s}>
              {SUBSCRIPTION[s].label}
            </option>
          ))}
        </SelectField>
        <SelectField label="Plan" value={plan} onChange={(e) => setFilter("plan", e.target.value)}>
          <option value="">Any plan</option>
          {(plans.data ?? []).map((p) => (
            <option key={p.code} value={p.code}>
              {p.name}
              {p.is_active ? "" : " (archived)"}
            </option>
          ))}
        </SelectField>
        <SelectField
          label="Ending within"
          value={expiring}
          onChange={(e) => setFilter("expiring_within", e.target.value)}
        >
          <option value="">Any time</option>
          {WINDOWS.map((d) => (
            <option key={d} value={d}>
              {d} days
            </option>
          ))}
        </SelectField>
      </form>

      {asking?.kind === "renew" ? (
        <RenewDialog target={target(asking.row)} onClose={() => setAsking(null)} />
      ) : null}
      {asking?.kind === "cancel" ? (
        <CancelSubscriptionDialog target={asking.row} onClose={() => setAsking(null)} />
      ) : null}

      {subs.isPending ? (
        <p role="status">Loading subscriptions…</p>
      ) : subs.isError ? (
        <p role="alert" className={styles.formError}>
          Subscriptions could not be loaded. Reload the page.
        </p>
      ) : (
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <caption className="visually-hidden">Subscriptions</caption>
            <thead>
              <tr>
                <th scope="col">Company</th>
                <th scope="col">Plan</th>
                <th scope="col">Status</th>
                <th scope="col">Started</th>
                <th scope="col">Ends</th>
                <th scope="col" className="num">
                  Last price
                </th>
                {isSuperAdmin ? <th scope="col">Actions</th> : null}
              </tr>
            </thead>
            <tbody onKeyDown={moveRowFocus}>
              {subs.data.items.length ? (
                subs.data.items.map((s) => (
                  <tr key={s.id}>
                    <td>
                      <Link to={`/admin/companies/${s.tenant_id}?tab=subscription`} data-row={s.id}>
                        {s.tenant_name}
                      </Link>
                      <div className={styles.sub}>{s.tenant_slug}</div>
                    </td>
                    <td>
                      {s.plan_name}
                      {s.duration_value && s.duration_unit ? (
                        <div className={styles.sub}>
                          {durationLabel(s.duration_value, s.duration_unit)}
                        </div>
                      ) : null}
                    </td>
                    <td>
                      <Badge tone={SUBSCRIPTION[s.status].tone}>
                        {SUBSCRIPTION[s.status].label}
                      </Badge>
                      {s.needs_review ? (
                        <div>
                          <Badge tone="warn">Needs review</Badge>
                        </div>
                      ) : null}
                    </td>
                    <td>{formatDay(s.starts_at)}</td>
                    <td>
                      {s.expires_at ? formatDay(s.expires_at) : "—"}
                      <div className={styles.sub}>{daysLeftLabel(s.days_left)}</div>
                    </td>
                    <td className="num">{s.price ? rupees(s.price) : "—"}</td>
                    {isSuperAdmin ? (
                      <td>
                        <div className={adminStyles.rowActions}>
                          <Button
                            aria-label={`Renew ${s.tenant_name}`}
                            onClick={() => setAsking({ kind: "renew", row: s })}
                          >
                            Renew
                          </Button>
                          {s.status !== "cancelled" ? (
                            <Button
                              aria-label={`Cancel ${s.tenant_name}`}
                              onClick={() => setAsking({ kind: "cancel", row: s })}
                            >
                              Cancel…
                            </Button>
                          ) : null}
                        </div>
                      </td>
                    ) : null}
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={columns} className={styles.empty}>
                    {params.toString()
                      ? "No subscription matches. Clear the filters."
                      : "No subscriptions yet."}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
          <p className={styles.results}>
            {subs.data.total} {subs.data.total === 1 ? "subscription" : "subscriptions"}
          </p>
          {subs.data.total > SUBSCRIPTION_PAGE_SIZE ? (
            <nav aria-label="Pages" className={styles.actions}>
              <Button disabled={page === 0} onClick={() => setFilter("page", String(page - 1))}>
                Previous
              </Button>
              <Button
                disabled={(page + 1) * SUBSCRIPTION_PAGE_SIZE >= subs.data.total}
                onClick={() => setFilter("page", String(page + 1))}
              >
                Next
              </Button>
            </nav>
          ) : null}
        </div>
      )}
    </section>
  );
}
