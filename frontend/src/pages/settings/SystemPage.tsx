import { toFormError } from "@/api/errors";
import { useSystemStatus, useVerify } from "@/api/system";
import type { SystemCheck } from "@/api/types";
import { Button } from "@/components/Button";
import styles from "@/components/Ledger.module.css";

const WORD = { ok: "Good", warn: "Look at this", fail: "Needs action" } as const;
const COLOUR = {
  ok: "var(--color-good)",
  warn: "var(--color-warn)",
  fail: "var(--color-critical)",
} as const;

function Row({ check }: { check: SystemCheck }) {
  return (
    <tr>
      <th scope="row" style={{ fontWeight: 500, color: "inherit" }}>
        {check.name}
      </th>
      <td style={{ color: COLOUR[check.state], fontWeight: 600 }}>{WORD[check.state]}</td>
      <td>{check.detail}</td>
    </tr>
  );
}

/** Owner: is the system healthy (backup, files, versions), and do the books still add up. */
export function SystemPage() {
  const status = useSystemStatus();
  const verify = useVerify();
  const s = status.data;
  const v = verify.data;

  return (
    <div className={styles.stack}>
      {status.isError ? (
        <p role="alert" className={styles.formError}>
          {toFormError(status.error).message}
        </p>
      ) : null}
      {s ? (
        <>
          <p className={styles.sub}>
            Version {s.version} · {s.environment}
            {s.test_watermark ? " · every PDF is stamped TEST (not production)" : ""}
          </p>
          {s.unclosed.length > 0 ? (
            <p role="status" className={styles.callout}>
              Yesterday&apos;s day is not closed at {s.unclosed.join(", ")}. Close it under Reports.
            </p>
          ) : null}
          <div className={styles.tableWrap}>
            <table className={styles.table} aria-label="System status">
              <tbody>
                <Row check={s.migrations} />
                <Row check={s.backup} />
                <Row check={s.storage} />
                <Row check={s.gsp} />
              </tbody>
            </table>
          </div>
        </>
      ) : null}
      <div className={styles.inline}>
        <Button variant="primary" onClick={() => verify.mutate(false)} disabled={verify.isPending}>
          Check the books
        </Button>
        <Button onClick={() => verify.mutate(true)} disabled={verify.isPending}>
          Check the books and every stored file
        </Button>
      </div>
      {verify.isError ? (
        <p role="alert" className={styles.formError}>
          {toFormError(verify.error).message}
        </p>
      ) : null}
      {v ? (
        <>
          <p role="status" className={v.ok ? styles.saved : styles.formError}>
            {v.ok
              ? "Everything adds up."
              : "Something does not add up. Do not close the month; call support with this list."}
          </p>
          <div className={styles.tableWrap}>
            <table className={styles.table} aria-label="Book checks">
              <tbody>
                {v.checks.map((c) => (
                  <Row key={c.name} check={c} />
                ))}
              </tbody>
            </table>
          </div>
        </>
      ) : null}
    </div>
  );
}
