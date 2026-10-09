import { useState, type ReactNode } from "react";

import { Button } from "./Button";
import { TextField } from "./Field";
import styles from "./Ledger.module.css";

export interface ReturnRow {
  id: number;
  label: string;
  /** What was billed, with its unit, e.g. "2.5 ton". */
  billed: string;
  /** What has already been taken back, in the base unit, or null when not known. */
  returned: string | null;
  unit: string;
}

export interface ReturnPick {
  lines: { line_id: number; quantity: string }[];
  reason: string;
}

/** Choose how much of each bill line comes back, and why. Quantities are in the line's own unit;
 * the server works out the value, GST and stock (rule B11). */
export function ReturnForm({
  rows,
  submitLabel,
  pending,
  error,
  children,
  onSubmit,
}: {
  rows: ReturnRow[];
  submitLabel: string;
  pending: boolean;
  error: { field: string | null; message: string } | null;
  children?: ReactNode;
  onSubmit: (pick: ReturnPick) => void;
}) {
  const [qty, setQty] = useState<Record<number, string>>({});
  const [reason, setReason] = useState("");
  const [local, setLocal] = useState<string | null>(null);

  function submit() {
    const lines = rows
      .filter((r) => Number(qty[r.id] ?? 0) > 0)
      .map((r) => ({ line_id: r.id, quantity: (qty[r.id] ?? "").trim() }));
    if (lines.length === 0) return setLocal("Enter how much comes back on at least one line.");
    if (reason.trim().length < 3) return setLocal("Write the reason for the return.");
    setLocal(null);
    onSubmit({ lines, reason: reason.trim() });
  }

  const shown = local ?? error?.message ?? null;
  return (
    <div
      className={styles.stack}
      role="group"
      aria-label="Return"
      onKeyDown={(e) => {
        if (e.key === "Enter" && (e.target as HTMLElement).tagName === "INPUT") {
          e.preventDefault();
          submit();
        }
      }}
    >
      {rows.map((r) => (
        <div key={r.id} className={styles.stack}>
          <strong>{r.label}</strong>
          <span className={styles.kv}>
            <span>Billed {r.billed}</span>
            {r.returned && Number(r.returned) > 0 ? <span>Back already {r.returned}</span> : null}
          </span>
          <TextField
            label={`${r.label}: quantity back (${r.unit})`}
            inputMode="decimal"
            value={qty[r.id] ?? ""}
            onChange={(e) => setQty({ ...qty, [r.id]: e.target.value })}
            error={error?.field === `lines[${rows.indexOf(r)}].quantity` ? error.message : null}
          />
        </div>
      ))}
      <TextField label="Reason" value={reason} onChange={(e) => setReason(e.target.value)} />
      {shown ? (
        <p role="alert" className={styles.formError}>
          {shown}
        </p>
      ) : null}
      {children}
      <Button variant="primary" onClick={submit} disabled={pending}>
        {submitLabel}
      </Button>
    </div>
  );
}
