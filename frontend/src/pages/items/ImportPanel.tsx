import { useRef, useState } from "react";

import { toFormError } from "@/api/errors";
import { downloadFile } from "@/api/client";
import { useImportItems } from "@/api/masters";
import type { ImportResult } from "@/api/types";
import { Button } from "@/components/Button";
import styles from "@/components/Ledger.module.css";

/** Two steps: check the sheet (nothing saved), then save it. */
export function ImportPanel({ onClose }: { onClose: () => void }) {
  const run = useImportItems();
  const fileInput = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  async function send(dryRun: boolean) {
    if (!file) return;
    setMessage(null);
    try {
      setResult(await run.mutateAsync({ file, dryRun }));
    } catch (err) {
      setResult(null);
      setMessage(toFormError(err).message);
    }
  }

  const clean = result !== null && result.errors.length === 0;

  return (
    <aside
      className={styles.panel}
      aria-labelledby="import-title"
      onKeyDown={(e) => e.key === "Escape" && onClose()}
    >
      <div className={styles.panelHead}>
        <h2 id="import-title">Import items from Excel</h2>
        <Button variant="quiet" onClick={onClose}>
          Close
        </Button>
      </div>
      <p className={styles.sub}>
        One row per item. Importing the same name again updates that item. The whole file is refused
        if any row has a problem.
      </p>
      <div className={styles.actions}>
        <Button onClick={() => void downloadFile("/items/import/template", "items-template.xlsx")}>
          Download template
        </Button>
      </div>
      <label className={styles.stack}>
        <span>Excel file (.xlsx)</span>
        <input
          ref={fileInput}
          type="file"
          accept=".xlsx"
          onChange={(e) => {
            setFile(e.target.files?.[0] ?? null);
            setResult(null);
          }}
        />
      </label>
      <div className={styles.actions}>
        <Button variant="primary" disabled={!file || run.isPending} onClick={() => void send(true)}>
          Check file
        </Button>
        {clean && result.dry_run ? (
          <Button disabled={run.isPending} onClick={() => void send(false)}>
            {`Save ${result.created + result.updated} items`}
          </Button>
        ) : null}
      </div>
      {message ? (
        <p role="alert" className={styles.formError}>
          {message}
        </p>
      ) : null}
      {result && clean ? (
        <p role="status" className={styles.resultBox}>
          {result.dry_run
            ? `File is fine: ${result.created} new, ${result.updated} to update. Nothing is saved yet.`
            : `Saved: ${result.created} new, ${result.updated} updated.`}
        </p>
      ) : null}
      {result && !clean ? (
        <div role="alert">
          <p className={styles.formError}>
            {result.errors.length} problem{result.errors.length === 1 ? "" : "s"} found. Nothing was
            saved. Fix the sheet and check again.
          </p>
          <ul className={styles.errorList}>
            {result.errors.slice(0, 50).map((e, i) => (
              <li key={i}>
                Row {e.row}
                {e.field ? `, ${e.field}` : ""}: {e.message}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </aside>
  );
}
