import { useState } from "react";

import { toFormError } from "@/api/errors";
import { Button } from "@/components/Button";
import { CheckField, TextAreaField, TextField } from "@/components/Field";
import styles from "@/components/Ledger.module.css";

import {
  useArchivePlan,
  useDeletePlan,
  useDuplicatePlan,
  usePlan,
  useUpdatePlan,
  usePlanFeatures,
  usePlans,
} from "../api";
import adminStyles from "../Admin.module.css";
import { useAdminAuth } from "../AdminAuthContext";
import { PlanCard } from "../PlanCard";
import { PlanEditor } from "../PlanEditor";
import planStyles from "../Plans.module.css";
import type { Plan } from "../types";

type Panel = { kind: "edit"; plan: Plan } | { kind: "new" } | null;

/** What Duolink sells (Milestone 20): plans with their limits, prices and listed features.
 * Support may look; a Super Admin edits. Prices are Duolink's own, never a company's money. */
export function PlansPage() {
  const { isSuperAdmin } = useAdminAuth();
  const [showArchived, setShowArchived] = useState(false);
  const plans = usePlans();
  const features = usePlanFeatures();
  const [panel, setPanel] = useState<Panel>(null);
  const names = Object.fromEntries((features.data ?? []).map((f) => [f.code, f.name]));
  const shown = (plans.data ?? []).filter((p) => showArchived || p.is_active);

  if (panel) {
    return (
      <section aria-labelledby="plans-title" className={styles.page}>
        <h1 id="plans-title" className={styles.title}>
          Plans
        </h1>
        <PlanEditor
          key={panel.kind === "edit" ? panel.plan.id : "new"}
          plan={panel.kind === "edit" ? panel.plan : undefined}
          features={features.data ?? []}
          onDone={() => setPanel(null)}
          onCancel={() => setPanel(null)}
        />
      </section>
    );
  }

  return (
    <section aria-labelledby="plans-title" className={styles.page}>
      <div className={styles.toolbar}>
        <h1 id="plans-title" className={styles.title}>
          Plans
        </h1>
        {isSuperAdmin ? (
          <Button variant="primary" onClick={() => setPanel({ kind: "new" })}>
            Add plan
          </Button>
        ) : null}
      </div>
      <p className={styles.note}>
        What Duolink sells. A plan sets how many users and shops a company may have. The features
        listed on a card are shown only; nothing is switched on or off by them yet.
      </p>
      <CheckField
        label="Show archived plans"
        checked={showArchived}
        onChange={(e) => setShowArchived(e.target.checked)}
      />
      {plans.isPending ? <p role="status">Loading…</p> : null}
      {plans.isError ? (
        <p role="alert" className={styles.formError}>
          The plans could not be loaded.
        </p>
      ) : null}
      <div className={planStyles.cards}>
        {shown.map((plan) => (
          <PlanCard
            key={plan.id}
            plan={plan}
            featureNames={names}
            actions={
              isSuperAdmin ? (
                <PlanActions plan={plan} onEdit={() => setPanel({ kind: "edit", plan })} />
              ) : null
            }
          />
        ))}
      </div>
      {plans.data && shown.length === 0 ? <p className={styles.empty}>No plans to show.</p> : null}
    </section>
  );
}

/** Edit, copy, archive or restore, and delete a plan nobody is on. */
function PlanActions({ plan, onEdit }: { plan: Plan; onEdit: () => void }) {
  const duplicate = useDuplicatePlan();
  const update = useUpdatePlan(plan.id);
  const [asking, setAsking] = useState<"archive" | "delete" | null>(null);
  const [error, setError] = useState<string | null>(null);

  return (
    <>
      <Button onClick={onEdit}>Edit</Button>
      <Button
        disabled={duplicate.isPending}
        onClick={() =>
          duplicate.mutate(plan.id, { onError: (err) => setError(toFormError(err).message) })
        }
      >
        Copy
      </Button>
      {plan.is_active ? (
        <Button onClick={() => setAsking("archive")}>Archive…</Button>
      ) : (
        <Button
          disabled={update.isPending}
          onClick={() =>
            update.mutate(
              { is_active: true },
              { onError: (err) => setError(toFormError(err).message) },
            )
          }
        >
          Restore
        </Button>
      )}
      {plan.companies === 0 ? (
        <Button className={adminStyles.danger} onClick={() => setAsking("delete")}>
          Delete…
        </Button>
      ) : null}
      {error ? (
        <p role="alert" className={styles.formError}>
          {error}
        </p>
      ) : null}
      {asking === "archive" ? <ArchiveDialog plan={plan} onClose={() => setAsking(null)} /> : null}
      {asking === "delete" ? <DeleteDialog plan={plan} onClose={() => setAsking(null)} /> : null}
    </>
  );
}

/** Mounted only while open, so the company count it shows is fetched when it opens. */
function ArchiveDialog({ plan, onClose }: { plan: Plan; onClose: () => void }) {
  const live = usePlan(plan.id);
  const archive = useArchivePlan(plan.id);
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const companies = live.data?.companies;

  return (
    <div className={adminStyles.confirm} role="alertdialog" aria-labelledby={`archive-${plan.id}`}>
      <p id={`archive-${plan.id}`}>
        Archive {plan.name}?{" "}
        {companies === undefined
          ? "Checking which companies are on it…"
          : companies === 0
            ? "No company is on it."
            : `${companies} ${companies === 1 ? "company keeps" : "companies keep"} it and its limits.`}{" "}
        It is hidden when adding a company or changing a plan, and it stops being the popular one.
      </p>
      <TextAreaField
        label="Reason for archiving"
        value={reason}
        onChange={(e) => setReason(e.target.value)}
      />
      {error ? (
        <p role="alert" className={styles.formError}>
          {error}
        </p>
      ) : null}
      <div className={styles.actions}>
        <Button
          variant="primary"
          disabled={archive.isPending || reason.trim().length < 3}
          onClick={() =>
            archive.mutate(reason.trim(), {
              onSuccess: onClose,
              onError: (err) => setError(toFormError(err).message),
            })
          }
        >
          Archive plan
        </Button>
        <Button onClick={onClose}>Keep it</Button>
      </div>
    </div>
  );
}

function DeleteDialog({ plan, onClose }: { plan: Plan; onClose: () => void }) {
  const live = usePlan(plan.id);
  const remove = useDeletePlan(plan.id);
  const [typed, setTyped] = useState("");
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const companies = live.data?.companies ?? 0;

  return (
    <div className={adminStyles.confirm} role="alertdialog" aria-labelledby={`delete-${plan.id}`}>
      <p id={`delete-${plan.id}`}>
        Delete {plan.name} for good?{" "}
        {companies > 0
          ? `${companies} ${companies === 1 ? "company is" : "companies are"} on it, so it cannot be deleted. Archive it instead.`
          : "No company is on it. This cannot be undone."}
      </p>
      <TextField
        label="Type DELETE to confirm"
        value={typed}
        onChange={(e) => setTyped(e.target.value)}
        autoComplete="off"
        autoFocus
      />
      <TextAreaField
        label="Reason for deleting"
        value={reason}
        onChange={(e) => setReason(e.target.value)}
      />
      {error ? (
        <p role="alert" className={styles.formError}>
          {error}
        </p>
      ) : null}
      <div className={styles.actions}>
        <Button
          variant="primary"
          className={adminStyles.danger}
          disabled={remove.isPending || typed !== "DELETE" || reason.trim().length < 3}
          onClick={() =>
            remove.mutate(
              { confirmation: typed, reason: reason.trim() },
              { onSuccess: onClose, onError: (err) => setError(toFormError(err).message) },
            )
          }
        >
          Delete plan
        </Button>
        <Button onClick={onClose}>Keep it</Button>
      </div>
    </div>
  );
}
