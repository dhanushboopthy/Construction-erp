import { useState, type FormEvent } from "react";

import { toFormError, type FormError } from "@/api/errors";
import { Button } from "@/components/Button";
import { SelectField, TextField } from "@/components/Field";
import styles from "@/components/Ledger.module.css";
import { formatDateTime } from "@/lib/format";

import { useUpdateTenant } from "../../api";
import adminStyles from "../../Admin.module.css";
import { useAdminAuth } from "../../AdminAuthContext";
import { Badge } from "../../Badge";
import { PLAN, STATUS, TRIAL } from "../../labels";
import type { TenantDetail, TenantPlan, TenantUpdate } from "../../types";

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

/** The plan, its limits and the trial. Renewals and payments join this tab in Milestone 21. */
export function SubscriptionTab({ tenant }: { tenant: TenantDetail }) {
  const { isSuperAdmin } = useAdminAuth();
  if (!isSuperAdmin) {
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
          <dd>{PLAN[tenant.plan].label}</dd>
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
  return <PlanForm tenant={tenant} />;
}

function PlanForm({ tenant }: { tenant: TenantDetail }) {
  const update = useUpdateTenant(tenant.id);
  const [plan, setPlan] = useState<TenantPlan>(tenant.plan);
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
        onChange={(e) => setPlan(e.target.value as TenantPlan)}
        hint={PLAN[plan].note}
        error={fieldError("plan")}
      >
        {(Object.keys(PLAN) as TenantPlan[]).map((p) => (
          <option key={p} value={p}>
            {PLAN[p].label}
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
