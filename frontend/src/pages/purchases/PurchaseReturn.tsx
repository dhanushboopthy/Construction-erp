import { useState } from "react";

import { openFile } from "@/api/client";
import { toFormError, type FormError } from "@/api/errors";
import type { PurchaseRow } from "@/api/purchasing";
import { useCreateDebitNote, useDebitNotes } from "@/api/returns";
import { Button } from "@/components/Button";
import styles from "@/components/Ledger.module.css";
import { ReturnForm, type ReturnPick } from "@/components/ReturnForm";
import { formatMoney, trimDecimal } from "@/lib/format";

/** Owner only: send goods back to the supplier with a debit note. Stock leaves at its landed
 * cost and what we owe the supplier falls by the note. */
export function PurchaseReturn({ purchase }: { purchase: PurchaseRow }) {
  const notes = useDebitNotes(purchase.id, true);
  const create = useCreateDebitNote();
  const [open, setOpen] = useState(false);
  const [error, setError] = useState<FormError | null>(null);
  const [done, setDone] = useState<string | null>(null);

  async function send(pick: ReturnPick) {
    setError(null);
    try {
      const made = await create.mutateAsync({
        purchase_id: purchase.id,
        reason: pick.reason,
        lines: pick.lines,
      });
      setOpen(false);
      setDone(`Debit note ${made.number} for ₹${formatMoney(made.grand_total)} is saved.`);
    } catch (err) {
      setError(toFormError(err));
    }
  }

  const list = notes.data?.items ?? [];
  return (
    <div className={styles.stack}>
      <h3 style={{ margin: 0 }}>Returns to the supplier</h3>
      {done ? (
        <p role="status" className={styles.saved}>
          {done}
        </p>
      ) : null}
      {list.length === 0 ? <p className={styles.sub}>Nothing has gone back on this bill.</p> : null}
      {list.map((n) => (
        <span key={n.id} className={styles.kv}>
          <span>
            {n.number} · {n.note_date} · {n.reason}
          </span>
          <span>
            ₹{formatMoney(n.grand_total)}{" "}
            <Button variant="quiet" onClick={() => void openFile(`/debit-notes/${n.id}/pdf`)}>
              Print {n.number}
            </Button>
          </span>
        </span>
      ))}
      {open ? (
        <ReturnForm
          rows={purchase.lines.map((l) => ({
            id: l.id,
            label: l.item_name,
            billed: `${trimDecimal(l.quantity)} ${l.unit}`,
            returned: null,
            unit: l.unit,
          }))}
          submitLabel="Save debit note"
          pending={create.isPending}
          error={error}
          onSubmit={(pick) => void send(pick)}
        />
      ) : (
        <Button
          onClick={() => {
            setOpen(true);
            setDone(null);
          }}
        >
          Return to supplier
        </Button>
      )}
    </div>
  );
}
