import { useState } from "react";

import { useChecklist, usePeriodLock, useSetPeriodLock } from "@/api/controls";
import { toFormError } from "@/api/errors";
import { useToday } from "@/api/reports";
import { Button } from "@/components/Button";
import { TextField } from "@/components/Field";
import styles from "@/components/Ledger.module.css";

/** Lock the books after a return is filed, and reopen them with a reason (FM7, owner). */
export function PeriodLockPage() {
  const asOf = useToday().data?.as_of ?? "";
  const lock = usePeriodLock();
  const save = useSetPeriodLock();
  const [through, setThrough] = useState("");
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [month, setMonth] = useState<string | null>(null);
  const checkMonth = month ?? asOf.slice(0, 7);
  const checklist = useChecklist(checkMonth);
  const current = lock.data;

  async function apply(value: string | null) {
    setError(null);
    try {
      await save.mutateAsync({ locked_through: value, reason: reason.trim() });
      setReason("");
      setThrough("");
    } catch (err) {
      setError(toFormError(err).message);
    }
  }

  return (
    <div className={styles.stack}>
      <section className={styles.panel} aria-labelledby="lock-title">
        <div className={styles.panelHead}>
          <h2 id="lock-title">Books lock</h2>
        </div>
        <p role="status">
          {current?.locked_through
            ? `Nothing can be dated on or before ${current.locked_through}.`
            : "The books are not locked. Any open day can take documents."}
        </p>
        {current?.changed_at ? (
          <p className={styles.note}>
            Last changed by {current.changed_by_name ?? "someone"}: {current.reason}
          </p>
        ) : null}
        <p className={styles.note}>
          Lock a month after its return is filed, so a late credit note cannot put the books out of
          step with the return. Ask the accountant whether to lock after GSTR-1 or after GSTR-3B.
        </p>
        <div className={styles.filters}>
          <TextField
            label="Lock through"
            type="date"
            value={through}
            max={asOf || undefined}
            onChange={(e) => setThrough(e.target.value)}
          />
          <TextField
            label="Reason"
            value={reason}
            maxLength={200}
            placeholder="September GSTR-1 filed"
            onChange={(e) => setReason(e.target.value)}
          />
          <Button
            variant="primary"
            disabled={through === "" || reason.trim().length < 5 || save.isPending}
            onClick={() => void apply(through)}
          >
            Lock books
          </Button>
          {current?.locked_through ? (
            <Button
              disabled={reason.trim().length < 5 || save.isPending}
              onClick={() => void apply(null)}
            >
              Reopen all
            </Button>
          ) : null}
        </div>
        <p className={styles.note}>
          Moving the lock earlier, or removing it, is a reopening. It is written to the audit log
          with your reason.
        </p>
        {error ? (
          <p role="alert" className={styles.formError}>
            {error}
          </p>
        ) : null}
      </section>

      <section className={styles.panel} aria-labelledby="check-title">
        <div className={styles.panelHead}>
          <h2 id="check-title">Month-end checklist</h2>
        </div>
        <div className={styles.filters}>
          <TextField
            label="Month"
            type="month"
            value={checkMonth}
            max={asOf.slice(0, 7) || undefined}
            onChange={(e) => setMonth(e.target.value)}
          />
        </div>
        {checklist.data ? (
          <>
            <ul className={styles.stack} aria-label="Checklist">
              {checklist.data.items.map((i) => (
                <li key={i.code}>
                  <strong>
                    {i.state === "ok" ? "✓" : "!"} {i.label}
                  </strong>
                  <span className={styles.sub}> {i.detail}</span>
                </li>
              ))}
            </ul>
            <p className={styles.note}>
              {checklist.data.ready
                ? "Everything looks ready to lock."
                : "Some items need a look. The lock does not wait for them."}
            </p>
          </>
        ) : null}
      </section>
    </div>
  );
}
