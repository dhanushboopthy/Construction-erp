import { useState } from "react";

import { ApiError, openFile } from "@/api/client";
import { toFormError, type FormError } from "@/api/errors";
import { useCreateCreditNote, useCreditNotes } from "@/api/returns";
import type { SalesInvoiceFull } from "@/api/sales";
import { ApprovalPrompt } from "@/components/ApprovalPrompt";
import { Button } from "@/components/Button";
import styles from "@/components/Ledger.module.css";
import { ReturnForm, type ReturnPick } from "@/components/ReturnForm";
import { formatMoney, trimDecimal } from "@/lib/format";

/** Credit notes for one bill: the earlier ones, and a form to take goods back (rule B11). */
export function InvoiceReturn({ inv }: { inv: SalesInvoiceFull }) {
  const notes = useCreditNotes(inv.id);
  const create = useCreateCreditNote();
  const [open, setOpen] = useState(false);
  const [error, setError] = useState<FormError | null>(null);
  const [needsOwner, setNeedsOwner] = useState<{ pick: ReturnPick; message: string } | null>(null);
  const [done, setDone] = useState<string | null>(null);

  async function send(pick: ReturnPick, approvalIds: number[]) {
    setError(null);
    try {
      const made = await create.mutateAsync({
        invoice_id: inv.id,
        reason: pick.reason,
        lines: pick.lines,
        approval_ids: approvalIds,
      });
      setNeedsOwner(null);
      setOpen(false);
      setDone(`Credit note ${made.number} for ₹${formatMoney(made.grand_total)} is saved.`);
    } catch (err) {
      if (
        err instanceof ApiError &&
        err.requiresOwnerApproval &&
        err.body.code !== "APPROVAL_INVALID"
      ) {
        setNeedsOwner({ pick, message: err.message });
      } else {
        setNeedsOwner(null);
        setError(toFormError(err));
      }
    }
  }

  const rows = inv.lines.map((l) => ({
    id: l.id,
    label: l.description,
    billed: `${trimDecimal(l.quantity)} ${l.unit}`,
    returned: `${trimDecimal(l.returned_qty)} ${l.base_unit}`,
    unit: l.unit,
  }));
  const list = notes.data?.items ?? [];

  return (
    <div className={styles.stack}>
      <h3 style={{ margin: 0 }}>Returns</h3>
      {done ? (
        <p role="status" className={styles.saved}>
          {done}
        </p>
      ) : null}
      {list.length === 0 ? (
        <p className={styles.sub}>No goods have come back on this bill.</p>
      ) : null}
      {list.map((n) => (
        <span key={n.id} className={styles.kv}>
          <span>
            {n.number} · {n.note_date} · {n.reason}
          </span>
          <span>
            ₹{formatMoney(n.grand_total)}{" "}
            <Button variant="quiet" onClick={() => void openFile(`/credit-notes/${n.id}/pdf`)}>
              Print {n.number}
            </Button>
          </span>
        </span>
      ))}
      {open ? (
        <ReturnForm
          rows={rows}
          submitLabel="Save credit note"
          pending={create.isPending}
          error={error}
          onSubmit={(pick) => void send(pick, [])}
        >
          {needsOwner ? (
            <ApprovalPrompt
              actions={["late_return"]}
              partyId={inv.party_id}
              messages={[needsOwner.message]}
              onApproved={(ids) => void send(needsOwner.pick, ids)}
            />
          ) : null}
        </ReturnForm>
      ) : (
        <Button
          onClick={() => {
            setOpen(true);
            setDone(null);
          }}
        >
          Return goods
        </Button>
      )}
    </div>
  );
}
