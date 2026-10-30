import { useState, type FormEvent } from "react";

import { toFormError } from "@/api/errors";
import { useCancelInvoice } from "@/api/returns";
import { Button } from "@/components/Button";
import { TextField } from "@/components/Field";
import styles from "@/components/Ledger.module.css";

/** Owner only. A bill is never deleted (B16): cancelling issues a credit note for all of it,
 * which puts the stock back and takes the amount off the customer's account. */
export function CancelBill({
  invoiceId,
  paidAtBilling,
}: {
  invoiceId: number;
  paidAtBilling: string;
}) {
  const cancel = useCancelInvoice();
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (reason.trim().length < 3) {
      setError("Say why the bill is cancelled.");
      return;
    }
    setError(null);
    try {
      await cancel.mutateAsync({ id: invoiceId, reason: reason.trim() });
      setOpen(false);
    } catch (err) {
      setError(toFormError(err).message);
    }
  }

  if (!open) {
    return (
      <div className={styles.actions}>
        <Button variant="ghost" onClick={() => setOpen(true)}>
          Cancel bill
        </Button>
      </div>
    );
  }
  return (
    <form className={styles.subsection} onSubmit={(e) => void onSubmit(e)} noValidate>
      <h3>Cancel this bill</h3>
      <p className={styles.sub}>
        The bill keeps its number and stays on record. A credit note reverses all of it: the stock
        goes back and the customer no longer owes it.
        {Number(paidAtBilling) > 0
          ? " Money taken with the bill stays on the customer's account as credit."
          : ""}
      </p>
      <TextField
        label="Why is it cancelled?"
        value={reason}
        maxLength={250}
        autoFocus
        error={error}
        onChange={(e) => setReason(e.target.value)}
      />
      <div className={styles.actions}>
        <Button type="submit" variant="primary" disabled={cancel.isPending}>
          {cancel.isPending ? "Cancelling…" : "Cancel the bill"}
        </Button>
        <Button onClick={() => setOpen(false)}>Keep it</Button>
      </div>
    </form>
  );
}
