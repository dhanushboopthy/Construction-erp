import { useState } from "react";

import { Button } from "@/components/Button";
import { CheckField, TextField } from "@/components/Field";
import styles from "@/components/Ledger.module.css";

import {
  useCompanyData,
  useCompanyDataView,
  useDataPreview,
  useDeleteAllCompanyData,
  useDeleteCompanyData,
} from "../../api";
import adminStyles from "../../Admin.module.css";
import type { DataDeleteResult, DataKind, TenantDetail } from "../../types";

const WORD = "DELETE";

function number(n: number): string {
  return n.toLocaleString("en-IN");
}

function Result({ done }: { done: DataDeleteResult }) {
  return (
    <div role="status" className={adminStyles.healthCard}>
      <p>
        <strong>{number(done.total)}</strong> rows removed
        {done.files_removed ? `, ${number(done.files_removed)} stored files too` : ""}. A protected
        safety backup (number {done.backup_id}) was taken first.
      </p>
      {done.series_reset.length > 0 && (
        <p className={styles.note}>
          Number series started again from 1:{" "}
          {done.series_reset.map((s) => `${s.series} (was ${s.from_number})`).join(", ")}.
        </p>
      )}
    </div>
  );
}

/** What a deletion would remove, read when the dialog opens (never carried over from the tab). */
function Preview({ tenantId, keys }: { tenantId: number; keys: string[] | null }) {
  const preview = useDataPreview(tenantId, keys, true);
  if (preview.isPending) return <p role="status">Counting what would go…</p>;
  if (preview.isError) {
    return (
      <p role="alert" className={styles.formError}>
        {preview.error.message}
      </p>
    );
  }
  const p = preview.data;
  return (
    <div aria-label="What will be removed">
      <p>
        <strong>{number(p.total)}</strong> rows
        {p.files ? ` and ${number(p.files)} stored files` : ""} will be removed:
      </p>
      <ul>
        {p.tables
          .filter((t) => t.count > 0)
          .map((t) => (
            <li key={t.table}>
              <code>{t.table}</code>: {number(t.count)}
            </li>
          ))}
      </ul>
      {p.message && (
        <p role="alert" className={styles.formError}>
          {p.message} Choose those kinds too, or delete them first.
        </p>
      )}
    </div>
  );
}

function DeleteDialog({
  tenant,
  keys,
  onClose,
}: {
  tenant: TenantDetail;
  keys: string[];
  onClose: () => void;
}) {
  const del = useDeleteCompanyData(tenant.id);
  const preview = useDataPreview(tenant.id, keys, true);
  const [typed, setTyped] = useState("");
  const blocked = Boolean(preview.data?.message);
  return (
    <div className={adminStyles.confirm} role="alertdialog" aria-label="Delete company data">
      <p>
        Delete the selected data of <strong>{tenant.name}</strong>? This cannot be undone from the
        screen: a protected safety backup is taken first and kept.
      </p>
      <Preview tenantId={tenant.id} keys={keys} />
      <TextField
        label={`Type ${WORD} to continue`}
        value={typed}
        autoFocus
        autoComplete="off"
        onChange={(e) => setTyped(e.target.value)}
      />
      <div className={styles.actions}>
        <Button
          variant="primary"
          className={adminStyles.danger}
          disabled={typed !== WORD || blocked || preview.isPending || del.isPending}
          onClick={() => del.mutate({ keys, confirm: typed })}
        >
          Delete selected data
        </Button>
        <Button variant="ghost" onClick={onClose}>
          {del.isSuccess ? "Close" : "Cancel"}
        </Button>
      </div>
      {del.isError && (
        <p role="alert" className={styles.formError}>
          {del.error.message}
        </p>
      )}
      {del.isSuccess && <Result done={del.data} />}
    </div>
  );
}

function DeleteAllDialog({ tenant, onClose }: { tenant: TenantDetail; onClose: () => void }) {
  const del = useDeleteAllCompanyData(tenant.id);
  const preview = useDataPreview(tenant.id, null, true);
  const [typed, setTyped] = useState("");
  const [name, setName] = useState("");
  const [ticked, setTicked] = useState(false);
  const ready = typed === WORD && name === tenant.name && ticked;
  return (
    <div className={adminStyles.confirm} role="alertdialog" aria-label="Delete all company data">
      <p>
        This removes <strong>every kind of business data</strong> of <strong>{tenant.name}</strong>:
        items, parties, bills, purchases, payments, ledgers, files. Its users, shops, settings,
        subscription, tickets and audit log stay. Number series start again from 1.
      </p>
      <Preview tenantId={tenant.id} keys={null} />
      <TextField
        label={`Type ${WORD} to continue`}
        value={typed}
        autoComplete="off"
        onChange={(e) => setTyped(e.target.value)}
      />
      <TextField
        label="Type the company's exact name"
        hint={tenant.name}
        value={name}
        autoComplete="off"
        onChange={(e) => setName(e.target.value)}
      />
      <CheckField
        label="I understand this deletes the company's books and cannot be undone here"
        checked={ticked}
        onChange={(e) => setTicked(e.target.checked)}
      />
      <div className={styles.actions}>
        <Button
          variant="primary"
          className={adminStyles.danger}
          disabled={!ready || preview.isPending || del.isPending}
          onClick={() => del.mutate({ confirm: typed, company_name: name, acknowledged: ticked })}
        >
          Delete all company data
        </Button>
        <Button variant="ghost" onClick={onClose}>
          {del.isSuccess ? "Close" : "Cancel"}
        </Button>
      </div>
      {del.isError && (
        <p role="alert" className={styles.formError}>
          {del.error.message}
        </p>
      )}
      {del.isSuccess && <Result done={del.data} />}
    </div>
  );
}

function ViewPanel({
  tenantId,
  kind,
  onClose,
}: {
  tenantId: number;
  kind: DataKind;
  onClose: () => void;
}) {
  const view = useCompanyDataView(tenantId, kind.key);
  return (
    <section aria-label={`Latest rows of ${kind.label}`} className={adminStyles.healthCard}>
      <h3>{kind.label}: latest 25</h3>
      {view.isPending && <p role="status">Loading…</p>}
      {view.isError && (
        <p role="alert" className={styles.formError}>
          {view.error.message}
        </p>
      )}
      {view.data && (
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                {view.data.columns.map((c) => (
                  <th key={c} scope="col">
                    {c}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {view.data.rows.map((row, i) => (
                <tr key={i}>
                  {row.map((cell, j) => (
                    <td key={j}>{cell}</td>
                  ))}
                </tr>
              ))}
              {view.data.rows.length === 0 && (
                <tr>
                  <td colSpan={4} className={styles.empty}>
                    Nothing here.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
      <div className={styles.actions}>
        <Button variant="ghost" onClick={onClose}>
          Close
        </Button>
      </div>
    </section>
  );
}

/** A company's business data, kind by kind, with the real foreign-key blockers; Super Admin only
 * (the server refuses Support on every route here, reads included). */
export function DataTab({ tenant }: { tenant: TenantDetail }) {
  const inventory = useCompanyData(tenant.id);
  const [picked, setPicked] = useState<string[]>([]);
  const [viewing, setViewing] = useState<DataKind | null>(null);
  const [deleting, setDeleting] = useState<string[] | null>(null);
  const [all, setAll] = useState(false);

  if (inventory.isPending) return <p role="status">Counting the company&apos;s data…</p>;
  if (inventory.isError) {
    return (
      <p role="alert" className={styles.formError}>
        {inventory.error.message}
      </p>
    );
  }
  const toggle = (key: string) =>
    setPicked((now) => (now.includes(key) ? now.filter((k) => k !== key) : [...now, key]));

  return (
    <div className={styles.stack}>
      <div className={styles.tableWrap}>
        <table className={styles.table} aria-label="Company data">
          <thead>
            <tr>
              <th scope="col">Pick</th>
              <th scope="col">Kind of data</th>
              <th scope="col" className={styles.amount}>
                Rows
              </th>
              <th scope="col">Blocked by</th>
              <th scope="col">
                <span className="visually-hidden">Actions</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {inventory.data.items.map((kind) => (
              <tr key={kind.key}>
                <td>
                  <input
                    type="checkbox"
                    aria-label={`Pick ${kind.label}`}
                    checked={picked.includes(kind.key)}
                    onChange={() => toggle(kind.key)}
                  />
                </td>
                <th scope="row">{kind.label}</th>
                <td className={styles.amount}>{number(kind.count)}</td>
                <td>
                  {kind.blocked_by.length === 0
                    ? "Nothing"
                    : kind.blocked_by.map((b) => `${number(b.count)} ${b.label}`).join(", ")}
                </td>
                <td>
                  <div className={styles.actions}>
                    <Button variant="ghost" onClick={() => setViewing(kind)}>
                      View
                    </Button>
                    <Button
                      variant="ghost"
                      disabled={kind.count === 0}
                      onClick={() => setDeleting([kind.key])}
                    >
                      Delete
                    </Button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className={styles.results}>{number(inventory.data.total)} rows in all</p>
      </div>

      <div className={styles.actions}>
        <Button
          variant="secondary"
          disabled={picked.length === 0}
          onClick={() => setDeleting(picked)}
        >
          Delete {picked.length || ""} picked
        </Button>
      </div>

      {viewing && (
        <ViewPanel tenantId={tenant.id} kind={viewing} onClose={() => setViewing(null)} />
      )}
      {deleting && (
        <DeleteDialog
          tenant={tenant}
          keys={deleting}
          onClose={() => {
            setDeleting(null);
            setPicked([]);
          }}
        />
      )}

      <section aria-labelledby="danger-title" className={adminStyles.dangerZone}>
        <h2 id="danger-title">Danger zone</h2>
        <p className={styles.note}>
          Delete everything the company has entered. The company itself, its users, shops, settings,
          subscription, tickets and audit log are kept.
        </p>
        {all ? (
          <DeleteAllDialog tenant={tenant} onClose={() => setAll(false)} />
        ) : (
          <div className={styles.actions}>
            <Button variant="primary" className={adminStyles.danger} onClick={() => setAll(true)}>
              Delete all company data…
            </Button>
          </div>
        )}
      </section>
    </div>
  );
}
