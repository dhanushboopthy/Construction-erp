import { Fragment, useState } from "react";

import { useAuditLog, type AuditFilter } from "@/api/controls";
import { useUsers } from "@/api/setup";
import { SelectField, TextField } from "@/components/Field";
import styles from "@/components/Ledger.module.css";
import { Button } from "@/components/Button";
import { formatDateTime } from "@/lib/format";

const ACTIONS = [
  "insert",
  "update",
  "delete",
  "login",
  "login_failed",
  "logout",
  "token_reuse",
  "override",
  "export",
] as const;
const PAGE = 50;

/** Who changed what and when (FM7, owner): every insert, update and delete of the books' records,
 * logins, owner overrides and exports. Read only. */
export function AuditLogPage() {
  const [filter, setFilter] = useState<AuditFilter>({
    entity: "",
    action: "",
    userId: "",
    since: "",
    until: "",
    offset: 0,
  });
  const [open, setOpen] = useState<number | null>(null);
  const users = useUsers();
  const log = useAuditLog(filter, PAGE);
  const names = new Map((users.data ?? []).map((u) => [u.id, u.full_name]));
  const set = (patch: Partial<AuditFilter>) => setFilter((f) => ({ ...f, offset: 0, ...patch }));
  const page = log.data;

  return (
    <div className={styles.stack}>
      <div className={styles.filters}>
        <TextField
          label="Record kind"
          value={filter.entity}
          placeholder="sales_invoice"
          onChange={(e) => set({ entity: e.target.value.trim() })}
        />
        <SelectField
          label="What happened"
          value={filter.action}
          onChange={(e) => set({ action: e.target.value as AuditFilter["action"] })}
        >
          <option value="">Anything</option>
          {ACTIONS.map((a) => (
            <option key={a} value={a}>
              {a.replace("_", " ")}
            </option>
          ))}
        </SelectField>
        <SelectField
          label="Who"
          value={filter.userId}
          onChange={(e) => set({ userId: e.target.value })}
        >
          <option value="">Anyone</option>
          {(users.data ?? []).map((u) => (
            <option key={u.id} value={u.id}>
              {u.full_name}
            </option>
          ))}
        </SelectField>
        <TextField
          label="From"
          type="date"
          value={filter.since}
          onChange={(e) => set({ since: e.target.value })}
        />
        <TextField
          label="To"
          type="date"
          value={filter.until}
          onChange={(e) => set({ until: e.target.value })}
        />
      </div>
      {log.isError ? (
        <p role="alert" className={styles.formError}>
          The audit log could not be loaded.
        </p>
      ) : null}
      {page ? (
        <>
          <div className={styles.tableWrap}>
            <table className={styles.table} aria-label="Audit log">
              <thead>
                <tr>
                  <th scope="col">When</th>
                  <th scope="col">Who</th>
                  <th scope="col">What</th>
                  <th scope="col">Record</th>
                  <th scope="col">Changes</th>
                </tr>
              </thead>
              <tbody>
                {page.items.map((row) => (
                  <Fragment key={row.id}>
                    <tr>
                      <td>{formatDateTime(row.at)}</td>
                      <td>
                        {row.user_id == null ? "" : (names.get(row.user_id) ?? `#${row.user_id}`)}
                      </td>
                      <td>{row.action.replace("_", " ")}</td>
                      <td className={styles.code}>
                        {row.entity}
                        {row.entity_id ? ` #${row.entity_id}` : ""}
                      </td>
                      <td>
                        {row.changes && Object.keys(row.changes).length > 0 ? (
                          <Button
                            aria-expanded={open === row.id}
                            onClick={() => setOpen(open === row.id ? null : row.id)}
                          >
                            {open === row.id ? "Hide" : "Show"}
                          </Button>
                        ) : null}
                      </td>
                    </tr>
                    {open === row.id ? (
                      <tr>
                        <td colSpan={5}>
                          <pre className={styles.code}>{JSON.stringify(row.changes, null, 2)}</pre>
                        </td>
                      </tr>
                    ) : null}
                  </Fragment>
                ))}
              </tbody>
            </table>
            {page.items.length === 0 ? (
              <p className={styles.empty}>Nothing matches these filters.</p>
            ) : null}
          </div>
          <div className={styles.actions}>
            <Button
              disabled={filter.offset === 0}
              onClick={() => setFilter((f) => ({ ...f, offset: Math.max(0, f.offset - PAGE) }))}
            >
              Newer
            </Button>
            <span className={styles.sub}>
              {page.total === 0 ? 0 : filter.offset + 1}–
              {Math.min(filter.offset + PAGE, page.total)} of {page.total}
            </span>
            <Button
              disabled={filter.offset + PAGE >= page.total}
              onClick={() => setFilter((f) => ({ ...f, offset: f.offset + PAGE }))}
            >
              Older
            </Button>
          </div>
        </>
      ) : null}
    </div>
  );
}
