import { useState, type FormEvent } from "react";

import { toFormError, type FormError } from "@/api/errors";
import { Button } from "@/components/Button";
import { SelectField, TextField } from "@/components/Field";
import styles from "@/components/Ledger.module.css";
import { formatDateTime, formatDay } from "@/lib/format";

import { usePayments, usePlans, useSubscriptions, useUpdateTenant } from "../../api";
import adminStyles from "../../Admin.module.css";
import { useAdminAuth } from "../../AdminAuthContext";
import { Badge } from "../../Badge";
import {
  STATUS,
  SUBSCRIPTION,
  TRIAL,
  daysLeftLabel,
  durationLabel,
  limitsNote,
  methodLabel,
  rupees,
} from "../../labels";
import { CancelSubscriptionDialog, RenewDialog } from "../../SubscriptionDialogs";
import type { TenantDetail, TenantUpdate } from "../../types";

const IST = "Asia/Kolkata";

/** An instant as the calendar day in shop time, for a date input (YYYY-MM-DD). */
function dayOf(iso: string | null): string {
  if (!iso) return "";
  return new Intl.DateTimeFormat("en-CA", { timeZone: IST }).format(new Date(iso));
}

/** The end of that day in shop time, as the API's instant. */
function endOfDay(day: string): string {
  return `${day}T23:59:59+05:30`;
}

/** The plan and limits, then the current subscription with its payments and, for a Super Admin,
 * renewal (Milestone 21). */
export function SubscriptionTab({ tenant }: { tenant: TenantDetail }) {
  const { isSuperAdmin } = useAdminAuth();
  return (
    <>
      {isSuperAdmin ? <PlanForm tenant={tenant} /> : <PlanFacts tenant={tenant} />}
      <BillingSection tenant={tenant} />
    </>
  );
}

/** What the company is on now, what it has paid and a way to renew. */
function BillingSection({ tenant }: { tenant: TenantDetail }) {
  const { isSuperAdmin } = useAdminAuth();
  const subs = useSubscriptions({ tenant_id: tenant.id, limit: 1 });
  const payments = usePayments({ tenant_id: tenant.id, limit: 50 });
  const [renewing, setRenewing] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [renewed, setRenewed] = useState(false);
  const sub = subs.data?.items[0];

  return (
    <div className={styles.panel}>
      <h2 className={styles.panelHead}>Current subscription</h2>
      {subs.isPending ? <p role="status">Loading the subscription…</p> : null}
      {subs.isError ? (
        <p role="alert" className={styles.formError}>
          The subscription could not be loaded.
        </p>
      ) : null}
      {subs.data && !sub ? (
        <p className={styles.note}>This company has no subscription yet.</p>
      ) : null}
      {sub ? (
        <dl className={adminStyles.facts}>
          <dt>Status</dt>
          <dd>
            <Badge tone={SUBSCRIPTION[sub.status].tone}>{SUBSCRIPTION[sub.status].label}</Badge>
            {sub.needs_review ? <Badge tone="warn">Needs review</Badge> : null}
          </dd>
          <dt>Plan</dt>
          <dd>{sub.plan_name}</dd>
          <dt>Started</dt>
          <dd>{formatDay(sub.starts_at)}</dd>
          <dt>Ends</dt>
          <dd>
            {sub.expires_at ? formatDay(sub.expires_at) : "—"} · {daysLeftLabel(sub.days_left)}
          </dd>
          {sub.price ? (
            <>
              <dt>Last price</dt>
              <dd>
                {rupees(sub.price)}
                {sub.duration_value && sub.duration_unit
                  ? ` for ${durationLabel(sub.duration_value, sub.duration_unit)}`
                  : ""}
              </dd>
            </>
          ) : null}
          {sub.cancelled_at ? (
            <>
              <dt>Cancelled</dt>
              <dd>
                {formatDay(sub.cancelled_at)}
                {sub.cancel_reason ? `: ${sub.cancel_reason}` : ""}
              </dd>
            </>
          ) : null}
        </dl>
      ) : null}
      {renewed ? (
        <p role="status" className={styles.saved}>
          Renewed. The payment is recorded below.
        </p>
      ) : null}
      {sub && isSuperAdmin && !renewing && !cancelling ? (
        <div className={styles.actions}>
          <Button variant="primary" onClick={() => setRenewing(true)}>
            Renew…
          </Button>
          {sub.status !== "cancelled" ? (
            <Button onClick={() => setCancelling(true)}>Cancel subscription…</Button>
          ) : null}
        </div>
      ) : null}
      {sub && renewing ? (
        <RenewDialog
          target={{ id: sub.id, tenant_name: tenant.name, plan_id: sub.plan_id }}
          onClose={(done) => {
            setRenewing(false);
            setRenewed(done);
          }}
        />
      ) : null}
      {sub && cancelling ? (
        <CancelSubscriptionDialog
          target={{ id: sub.id, tenant_name: tenant.name }}
          onClose={() => setCancelling(false)}
        />
      ) : null}

      <h2 className={styles.panelHead}>Payments</h2>
      {payments.isPending ? <p role="status">Loading payments…</p> : null}
      {payments.data && payments.data.items.length === 0 ? (
        <p className={styles.note}>No payment recorded for this company.</p>
      ) : null}
      {payments.data?.items.length ? (
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <caption className="visually-hidden">Payment history</caption>
            <thead>
              <tr>
                <th scope="col">Paid on</th>
                <th scope="col">Plan</th>
                <th scope="col" className="num">
                  Amount
                </th>
                <th scope="col">Method</th>
                <th scope="col">Paid for</th>
              </tr>
            </thead>
            <tbody>
              {payments.data.items.map((p) => (
                <tr key={p.id} className={p.reversed ? styles.inactive : ""}>
                  <td>{formatDateTime(p.paid_at)}</td>
                  <td>{p.plan_name}</td>
                  <td className="num">
                    {rupees(p.amount)}
                    {p.reverses_id !== null ? (
                      <div>
                        <Badge tone="warn">Reversal</Badge>
                      </div>
                    ) : p.reversed ? (
                      <div>
                        <Badge tone="neutral">Reversed</Badge>
                      </div>
                    ) : null}
                  </td>
                  <td>
                    {methodLabel(p.method)}
                    {p.reference ? <div className={styles.sub}>{p.reference}</div> : null}
                  </td>
                  <td>
                    {p.period_starts_at && p.period_ends_at
                      ? `${formatDay(p.period_starts_at)} to ${formatDay(p.period_ends_at)}`
                      : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </div>
  );
}

function PlanFacts({ tenant }: { tenant: TenantDetail }) {
  const trial = TRIAL[tenant.trial_state];
  return (
    <div className={styles.panel}>
      <h2 className={styles.panelHead}>Plan and limits</h2>
      <dl className={adminStyles.facts}>
        <dt>Status</dt>
        <dd>
          <Badge tone={STATUS[tenant.status].tone}>{STATUS[tenant.status].label}</Badge>
          {trial && tenant.status === "trial" ? (
            <Badge tone={trial.tone}>{trial.label}</Badge>
          ) : null}
        </dd>
        <dt>Plan</dt>
        <dd>{tenant.plan_name}</dd>
        <dt>Own user limit</dt>
        <dd>{tenant.own_max_users ?? "The plan's limit"}</dd>
        <dt>Own limit for shops and godowns</dt>
        <dd>{tenant.own_max_locations ?? "The plan's limit"}</dd>
        <dt>Trial ends</dt>
        <dd>{formatDateTime(tenant.trial_ends_at)}</dd>
      </dl>
      <p className={styles.note}>Only a Super Admin changes a company.</p>
    </div>
  );
}

function PlanForm({ tenant }: { tenant: TenantDetail }) {
  const update = useUpdateTenant(tenant.id);
  const plans = usePlans().data ?? [];
  const [plan, setPlan] = useState(tenant.plan);
  // Archived plans are not offered, except the one the company is on already.
  const offered = plans.filter((p) => p.is_active || p.code === tenant.plan);
  const picked = plans.find((p) => p.code === plan);
  const [maxUsers, setMaxUsers] = useState(tenant.own_max_users?.toString() ?? "");
  const [maxLocations, setMaxLocations] = useState(tenant.own_max_locations?.toString() ?? "");
  const [trialEnds, setTrialEnds] = useState(dayOf(tenant.trial_ends_at));
  const [error, setError] = useState<FormError | null>(null);
  const [saved, setSaved] = useState(false);
  const fieldError = (key: string) => (error?.field === key ? error.message : null);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setSaved(false);
    const body: TenantUpdate = {};
    if (plan !== tenant.plan) body.plan = plan;
    const users = maxUsers.trim() ? Number(maxUsers) : null;
    if (users !== tenant.own_max_users) body.max_users = users;
    const locations = maxLocations.trim() ? Number(maxLocations) : null;
    if (locations !== tenant.own_max_locations) body.max_locations = locations;
    if (trialEnds !== dayOf(tenant.trial_ends_at)) {
      body.trial_ends_at = trialEnds ? endOfDay(trialEnds) : null;
    }
    try {
      await update.mutateAsync(body);
      setSaved(true);
    } catch (err) {
      setError(toFormError(err));
    }
  }

  return (
    <form className={styles.panel} onSubmit={(e) => void onSubmit(e)} noValidate>
      <h2 className={styles.panelHead}>Plan and limits</h2>
      <SelectField
        label="Plan"
        value={plan}
        onChange={(e) => setPlan(e.target.value)}
        hint={picked ? limitsNote(picked) : undefined}
        error={fieldError("plan")}
      >
        {offered.map((p) => (
          <option key={p.code} value={p.code}>
            {p.name}
            {p.is_active ? "" : " (archived)"}
          </option>
        ))}
      </SelectField>
      <TextField
        label="Own user limit"
        inputMode="numeric"
        value={maxUsers}
        onChange={(e) => setMaxUsers(e.target.value.replace(/\D/g, ""))}
        hint="Blank: the plan's limit."
        error={fieldError("max_users")}
      />
      <TextField
        label="Own limit for shops and godowns"
        inputMode="numeric"
        value={maxLocations}
        onChange={(e) => setMaxLocations(e.target.value.replace(/\D/g, ""))}
        hint="Blank: the plan's limit."
        error={fieldError("max_locations")}
      />
      <TextField
        label="Trial ends"
        type="date"
        value={trialEnds}
        onChange={(e) => setTrialEnds(e.target.value)}
        hint="An ended trial only shows here; the company keeps working until you suspend it."
        error={fieldError("trial_ends_at")}
      />
      {error && !error.field ? (
        <p role="alert" className={styles.formError}>
          {error.message}
        </p>
      ) : null}
      <div className={styles.actions}>
        <Button type="submit" variant="primary" disabled={update.isPending}>
          {update.isPending ? "Saving…" : "Save plan"}
        </Button>
        {saved ? (
          <p role="status" className={styles.saved}>
            Plan saved.
          </p>
        ) : null}
      </div>
    </form>
  );
}
