import { useState } from "react";

import { Button } from "@/components/Button";
import { TextField } from "@/components/Field";
import styles from "@/components/Ledger.module.css";

import { useNumbering, useSetNumbering } from "../../api";
import adminStyles from "../../Admin.module.css";
import type { NumberingRow, TenantDetail } from "../../types";

const rowKey = (r: NumberingRow) => `${r.location_id}/${r.doc_type}/${r.financial_year}`;

function Editor({
  tenantId,
  row,
  onDone,
}: {
  tenantId: number;
  row: NumberingRow;
  onDone: () => void;
}) {
  const save = useSetNumbering(tenantId);
  const [value, setValue] = useState(String(row.configured_next));
  const [reason, setReason] = useState("");
  const wanted = Number(value);
  const low = !Number.isInteger(wanted) || wanted < row.minimum_next;
  const error = low ? `The next number must be ${row.minimum_next} or higher.` : undefined;
  return (
    <form
      className={adminStyles.confirm}
      aria-label={`Set ${row.doc_label} number for ${row.location_code} ${row.financial_year}`}
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate(
          {
            location_id: row.location_id,
            doc_type: row.doc_type,
            financial_year: row.financial_year,
            next_number: wanted,
            reason,
          },
          { onSuccess: onDone },
        );
      }}
    >
      <TextField
        label="Next number"
        inputMode="numeric"
        value={value}
        autoFocus
        error={error}
        hint={
          row.highest_number
            ? `${row.highest_number} is the highest that exists.`
            : "No document exists in this series, so 1 is allowed."
        }
        onChange={(e) => setValue(e.target.value)}
      />
      <TextField
        label="Reason"
        value={reason}
        maxLength={300}
        onChange={(e) => setReason(e.target.value)}
      />
      <div className={styles.actions}>
        <Button variant="primary" type="submit" disabled={low || !reason.trim() || save.isPending}>
          Save
        </Button>
        <Button variant="ghost" onClick={onDone}>
          Cancel
        </Button>
      </div>
      {save.isError && (
        <p role="alert" className={styles.formError}>
          {save.error.message}
        </p>
      )}
    </form>
  );
}

/** One row per shop, document type and financial year. Two numbers are shown because only one
 * may refuse a value: the highest that exists (read from the documents) and the counter. */
export function NumberingTab({ tenant }: { tenant: TenantDetail }) {
  const numbering = useNumbering(tenant.id);
  const [editing, setEditing] = useState<string | null>(null);
  if (numbering.isPending) return <p role="status">Loading the number series…</p>;
  if (numbering.isError) {
    return (
      <p role="alert" className={styles.formError}>
        {numbering.error.message}
      </p>
    );
  }
  const rows = numbering.data.items;
  return (
    <div className={styles.stack}>
      <p className={styles.note}>
        The next number can only go up from the highest document that exists. A series whose
        documents were all deleted can start again at 1. Each change needs a reason and is kept in
        the audit log.
      </p>
      <div className={styles.tableWrap}>
        <table className={styles.table} aria-label="Number series">
          <thead>
            <tr>
              <th scope="col">Shop</th>
              <th scope="col">Document</th>
              <th scope="col">Year</th>
              <th scope="col" className={styles.amount}>
                Highest existing
              </th>
              <th scope="col" className={styles.amount}>
                Next number
              </th>
              <th scope="col">Next document</th>
              <th scope="col">
                <span className="visually-hidden">Actions</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={rowKey(r)}>
                <th scope="row">{r.location_code}</th>
                <td>{r.doc_label}</td>
                <td>{r.financial_year}</td>
                <td className={styles.amount}>{r.highest_existing ?? "None"}</td>
                <td className={styles.amount}>{r.configured_next}</td>
                <td>
                  <code>{r.next_document}</code>
                  {r.ahead_of_documents && r.suggested_next !== null && (
                    <span className={styles.note}>
                      {" "}
                      Ahead of its documents: {r.suggested_next} closes the gap.
                    </span>
                  )}
                </td>
                <td>
                  <Button variant="ghost" onClick={() => setEditing(rowKey(r))}>
                    Set
                  </Button>
                </td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr>
                <td colSpan={7} className={styles.empty}>
                  No number series yet: this company has not saved a document.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      {rows
        .filter((r) => rowKey(r) === editing)
        .map((r) => (
          <Editor key={rowKey(r)} tenantId={tenant.id} row={r} onDone={() => setEditing(null)} />
        ))}
    </div>
  );
}
