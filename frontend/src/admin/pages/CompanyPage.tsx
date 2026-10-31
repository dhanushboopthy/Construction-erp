import { useState, type FormEvent } from "react";
import { Link, useLocation, useParams } from "react-router";

import { toFormError, type FormError } from "@/api/errors";
import { Button } from "@/components/Button";
import { SelectField, TextAreaField, TextField } from "@/components/Field";
import styles from "@/components/Ledger.module.css";
import { formatDateTime } from "@/lib/format";

import { useReactivateTenant, useSuspendTenant, useTenant, useUpdateTenant } from "../api";
import adminStyles from "../Admin.module.css";
import { useAdminAuth } from "../AdminAuthContext";
import { Badge, Usage } from "../Badge";
import { PLAN, STATUS, TRIAL, companyAddress } from "../labels";
import type { TenantDetail, TenantPlan, TenantUpdate } from "../types";
import { UsersView } from "../UsersView";

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

export function CompanyPage() {
  const id = Number(useParams().id);
  const location = useLocation();
  const tenant = useTenant(id);
  const { isSuperAdmin } = useAdminAuth();
  const created = (location.state as { created?: boolean } | null)?.created === true;

  if (tenant.isPending) return <p role="status">Loading the company…</p>;
  if (tenant.isError) {
    return (
      <p className={styles.formError}>
        This company could not be loaded. <Link to="/admin/companies">Back to companies</Link>
      </p>
    );
  }
  const t = tenant.data;
  const trial = TRIAL[t.trial_state];
  const address = companyAddress(t.slug);

  return (
    <section aria-labelledby="company-title" className={styles.page}>
      <p>
        <Link to="/admin/companies">Companies</Link>
      </p>
      <div className={adminStyles.heading}>
        <h1 id="company-title" className={styles.title}>
          {t.name}
        </h1>
        <Badge tone={STATUS[t.status].tone}>{STATUS[t.status].label}</Badge>
        {trial && t.status === "trial" ? <Badge tone={trial.tone}>{trial.label}</Badge> : null}
        <a className={adminStyles.address} href={address} target="_blank" rel="noreferrer">
          {address.replace(/^https?:\/\//, "")}
        </a>
      </div>
      {created ? (
        <p role="status" className={styles.saved}>
          Company created. Its owner can sign in at {address} now.
        </p>
      ) : null}

      <div className={adminStyles.twoColumns}>
        <div className={styles.panel}>
          <h2 className={styles.panelHead}>In use</h2>
          <dl className={adminStyles.facts}>
            <dt>Active users</dt>
            <dd>
              <Usage used={t.users} limit={t.max_users} label="active users" />
            </dd>
            <dt>Shops and godowns</dt>
            <dd>
              <Usage used={t.locations} limit={t.max_locations} label="shops and godowns" />
            </dd>
            <dt>Bills, last 30 days</dt>
            <dd>{t.bills_30d}</dd>
            <dt>Signed in now</dt>
            <dd>{t.open_sessions}</dd>
            <dt>Last sign-in</dt>
            <dd>{formatDateTime(t.last_sign_in_at)}</dd>
            <dt>Joined</dt>
            <dd>{formatDateTime(t.created_at)}</dd>
          </dl>
        </div>
        {isSuperAdmin ? (
          <PlanForm tenant={t} />
        ) : (
          <div className={styles.panel}>
            <h2 className={styles.panelHead}>Plan and limits</h2>
            <dl className={adminStyles.facts}>
              <dt>Plan</dt>
              <dd>{PLAN[t.plan].label}</dd>
              <dt>Own user limit</dt>
              <dd>{t.own_max_users ?? "The plan's limit"}</dd>
              <dt>Own limit for shops and godowns</dt>
              <dd>{t.own_max_locations ?? "The plan's limit"}</dd>
              <dt>Trial ends</dt>
              <dd>{formatDateTime(t.trial_ends_at)}</dd>
            </dl>
            <p className={styles.note}>Only a Super Admin changes a company.</p>
          </div>
        )}
      </div>

      {isSuperAdmin ? <Suspension tenant={t} /> : null}

      <h2 className={styles.title}>Users</h2>
      <UsersView tenantId={t.id} />
    </section>
  );
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

function Suspension({ tenant }: { tenant: TenantDetail }) {
  const suspend = useSuspendTenant(tenant.id);
  const reactivate = useReactivateTenant(tenant.id);
  const [reason, setReason] = useState("");
  const [confirming, setConfirming] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (tenant.status === "suspended") {
    return (
      <div className={styles.panel}>
        <h2 className={styles.panelHead}>Suspended</h2>
        <dl className={adminStyles.facts}>
          <dt>Since</dt>
          <dd>{formatDateTime(tenant.suspended_at)}</dd>
          <dt>Reason</dt>
          <dd>{tenant.suspended_reason}</dd>
        </dl>
        <p className={styles.note}>Nobody at {tenant.name} can sign in. Their books are kept.</p>
        <div className={styles.actions}>
          <Button
            variant="primary"
            disabled={reactivate.isPending}
            onClick={() => {
              setError(null);
              reactivate.mutate(undefined, { onError: (e) => setError(toFormError(e).message) });
            }}
          >
            Reactivate company
          </Button>
        </div>
        {error ? (
          <p role="alert" className={styles.formError}>
            {error}
          </p>
        ) : null}
      </div>
    );
  }

  return (
    <form
      className={styles.panel}
      onSubmit={(e) => {
        e.preventDefault();
        if (reason.trim().length < 3) {
          setError("Write why, in a few words. The company's owner may ask.");
          return;
        }
        setError(null);
        setConfirming(true);
      }}
      noValidate
    >
      <h2 className={styles.panelHead}>Suspend company</h2>
      <TextAreaField
        label="Reason"
        value={reason}
        onChange={(e) => {
          setReason(e.target.value);
          setConfirming(false);
        }}
        hint="For example: Invoice for October unpaid."
        error={error}
      />
      {confirming ? (
        <div className={adminStyles.confirm} role="alertdialog" aria-labelledby="suspend-confirm">
          <p id="suspend-confirm">
            Suspend {tenant.name}? {tenant.open_sessions} signed-in{" "}
            {tenant.open_sessions === 1 ? "person is" : "people are"} signed out now, and nobody can
            sign in until you reactivate it.
          </p>
          <div className={styles.actions}>
            <Button
              variant="primary"
              className={adminStyles.danger}
              disabled={suspend.isPending}
              autoFocus
              onClick={() =>
                suspend.mutate(reason.trim(), {
                  onSuccess: () => {
                    setConfirming(false);
                    setReason("");
                  },
                  onError: (e) => setError(toFormError(e).message),
                })
              }
            >
              Suspend now
            </Button>
            <Button onClick={() => setConfirming(false)}>Keep it running</Button>
          </div>
        </div>
      ) : (
        <div className={styles.actions}>
          <Button type="submit">Suspend company</Button>
        </div>
      )}
    </form>
  );
}
