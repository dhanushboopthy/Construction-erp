import { useState, type FormEvent } from "react";

import { toFormError } from "@/api/errors";
import { Button } from "@/components/Button";
import { SelectField, TextAreaField, TextField } from "@/components/Field";
import styles from "@/components/Ledger.module.css";
import { isAmount } from "@/lib/format";

import { useCancelSubscription, usePlans, useRenewSubscription, useReversePayment } from "./api";
import adminStyles from "./Admin.module.css";
import { METHODS, durationLabel, rupees } from "./labels";
import type { PaymentMethod, RenewBody } from "./types";

/** The few things a renewal needs to know about the subscription it extends. */
export interface RenewTarget {
  id: number;
  tenant_name: string;
  plan_id: number;
}

const CUSTOM = "custom";

/** Renew by hand: the plan, how long (a listed price or a number of days), what was received and
 * how. The company's access is extended from the later of today and its current end. */
export function RenewDialog({
  target,
  onClose,
}: {
  target: RenewTarget;
  onClose: (renewed: boolean) => void;
}) {
  const renew = useRenewSubscription(target.id);
  const plans = usePlans().data ?? [];
  const [planId, setPlanId] = useState(target.plan_id);
  const offered = plans.filter((p) => p.is_active || p.id === target.plan_id);
  const plan = plans.find((p) => p.id === planId);
  const prices = (plan?.prices ?? []).filter((p) => p.is_active);
  const [choice, setChoice] = useState<string>("");
  const [days, setDays] = useState("");
  // Until the amount is typed in, it follows the chosen price.
  const [amount, setAmount] = useState<string | null>(null);
  const [method, setMethod] = useState<PaymentMethod>("bank");
  const [reference, setReference] = useState("");
  const [notes, setNotes] = useState("");
  const [error, setError] = useState<{ field: string | null; message: string } | null>(null);
  const fieldError = (key: string) => (error?.field === key ? error.message : null);

  // The first listed price is chosen as soon as the plan's prices are known.
  const picked = choice || (prices[0] ? `price:${prices[0].id}` : CUSTOM);
  const pickedPrice = prices.find((p) => `price:${p.id}` === picked);

  const shownAmount = amount ?? pickedPrice?.price ?? "";

  function onPlan(id: number) {
    setPlanId(id);
    setChoice("");
    setAmount(null);
  }

  function onChoice(value: string) {
    setChoice(value);
    setAmount(null);
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    const received = shownAmount.trim();
    if (!isAmount(received)) {
      setError({ field: "amount", message: "Enter the amount received, such as 999.00." });
      return;
    }
    if (picked === CUSTOM && !/^[1-9]\d*$/.test(days.trim())) {
      setError({ field: "custom_days", message: "Enter the number of days, such as 30." });
      return;
    }
    const body: RenewBody = {
      plan_id: planId,
      price_id: pickedPrice ? pickedPrice.id : null,
      custom_days: pickedPrice ? null : Number(days),
      amount: received,
      method,
    };
    if (reference.trim()) body.reference = reference.trim();
    if (notes.trim()) body.notes = notes.trim();
    try {
      await renew.mutateAsync(body);
      onClose(true);
    } catch (err) {
      setError(toFormError(err));
    }
  }

  return (
    <form
      className={styles.panel}
      role="dialog"
      aria-label={`Renew ${target.tenant_name}`}
      onSubmit={(e) => void onSubmit(e)}
      onKeyDown={(e) => {
        if (e.key === "Escape") onClose(false);
      }}
      noValidate
    >
      <h2 className={styles.panelHead}>Renew {target.tenant_name}</h2>
      <SelectField
        label="Plan"
        value={planId}
        onChange={(e) => onPlan(Number(e.target.value))}
        autoFocus
      >
        {offered.map((p) => (
          <option key={p.id} value={p.id}>
            {p.name}
            {p.is_active ? "" : " (archived)"}
          </option>
        ))}
      </SelectField>
      <SelectField
        label="Renew for"
        value={picked}
        onChange={(e) => onChoice(e.target.value)}
        error={fieldError("price_id") ?? fieldError("custom_days")}
      >
        {prices.map((p) => (
          <option key={p.id} value={`price:${p.id}`}>
            {durationLabel(p.duration_value, p.duration_unit)} at {rupees(p.price)}
          </option>
        ))}
        <option value={CUSTOM}>A number of days I choose</option>
      </SelectField>
      {picked === CUSTOM ? (
        <TextField
          label="Number of days"
          inputMode="numeric"
          value={days}
          onChange={(e) => setDays(e.target.value.replace(/\D/g, ""))}
          error={fieldError("custom_days")}
        />
      ) : null}
      <TextField
        label="Amount received"
        inputMode="decimal"
        value={shownAmount}
        onChange={(e) => setAmount(e.target.value)}
        hint="In rupees, as received. Can differ from the list price."
        error={fieldError("amount")}
      />
      <SelectField
        label="Paid by"
        value={method}
        onChange={(e) => setMethod(e.target.value as PaymentMethod)}
        error={fieldError("method")}
      >
        {METHODS.map((m) => (
          <option key={m.value} value={m.value}>
            {m.label}
          </option>
        ))}
      </SelectField>
      <TextField
        label="Reference"
        value={reference}
        onChange={(e) => setReference(e.target.value)}
        hint="Transaction, UTR or cheque number."
      />
      <TextAreaField label="Notes" value={notes} onChange={(e) => setNotes(e.target.value)} />
      {error && !error.field ? (
        <p role="alert" className={styles.formError}>
          {error.message}
        </p>
      ) : null}
      {error?.field && !["amount", "custom_days", "price_id", "method"].includes(error.field) ? (
        <p role="alert" className={styles.formError}>
          {error.message}
        </p>
      ) : null}
      <div className={styles.actions}>
        <Button type="submit" variant="primary" disabled={renew.isPending}>
          {renew.isPending ? "Renewing…" : "Record payment and renew"}
        </Button>
        <Button onClick={() => onClose(false)}>Cancel</Button>
      </div>
    </form>
  );
}

/** One reason, asked in place, before something that cannot be quietly undone. */
function ReasonDialog({
  id,
  question,
  reasonLabel,
  confirmLabel,
  keepLabel,
  pending,
  run,
  onClose,
}: {
  id: string;
  question: string;
  reasonLabel: string;
  confirmLabel: string;
  keepLabel: string;
  pending: boolean;
  run: (reason: string) => Promise<unknown>;
  onClose: () => void;
}) {
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      await run(reason.trim());
      onClose();
    } catch (err) {
      setError(toFormError(err).message);
    }
  }

  return (
    <form
      className={adminStyles.confirm}
      role="alertdialog"
      aria-labelledby={id}
      onSubmit={(e) => void onSubmit(e)}
      onKeyDown={(e) => {
        if (e.key === "Escape") onClose();
      }}
    >
      <p id={id}>{question}</p>
      <TextAreaField
        label={reasonLabel}
        value={reason}
        onChange={(e) => setReason(e.target.value)}
        autoFocus
      />
      {error ? (
        <p role="alert" className={styles.formError}>
          {error}
        </p>
      ) : null}
      <div className={styles.actions}>
        <Button
          type="submit"
          variant="primary"
          className={adminStyles.danger}
          disabled={pending || reason.trim().length < 3}
        >
          {confirmLabel}
        </Button>
        <Button onClick={onClose}>{keepLabel}</Button>
      </div>
    </form>
  );
}

export function CancelSubscriptionDialog({
  target,
  onClose,
}: {
  target: { id: number; tenant_name: string };
  onClose: () => void;
}) {
  const cancel = useCancelSubscription(target.id);
  return (
    <ReasonDialog
      id={`cancel-${target.id}`}
      question={`Cancel the subscription of ${target.tenant_name}? The company becomes read-only at once. Its data is kept, and a later renewal opens it again.`}
      reasonLabel="Reason for cancelling"
      confirmLabel="Cancel subscription"
      keepLabel="Keep it"
      pending={cancel.isPending}
      run={(reason) => cancel.mutateAsync(reason)}
      onClose={onClose}
    />
  );
}

export function ReversePaymentDialog({
  target,
  onClose,
}: {
  target: { id: number; tenant_name: string; amount: string };
  onClose: () => void;
}) {
  const reverse = useReversePayment(target.id);
  return (
    <ReasonDialog
      id={`reverse-${target.id}`}
      question={`Reverse the payment of ${rupees(target.amount)} from ${target.tenant_name}? A reversing entry is added, the original stays, and the period it paid for is taken back.`}
      reasonLabel="Reason for reversing"
      confirmLabel="Reverse payment"
      keepLabel="Keep it"
      pending={reverse.isPending}
      run={(reason) => reverse.mutateAsync(reason)}
      onClose={onClose}
    />
  );
}
