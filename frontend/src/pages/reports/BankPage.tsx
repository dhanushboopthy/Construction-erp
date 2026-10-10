import { useState } from "react";

import {
  useBankAccounts,
  useCreateBankAccount,
  useReconciliation,
  useStatements,
  useUploadStatement,
} from "@/api/controls";
import { toFormError } from "@/api/errors";
import { useToday } from "@/api/reports";
import { useAuth } from "@/auth/AuthContext";
import { Button } from "@/components/Button";
import { SelectField, TextField } from "@/components/Field";
import styles from "@/components/Ledger.module.css";
import { Metric } from "@/components/Metric";
import { addDays } from "@/lib/dates";
import { formatMoney } from "@/lib/format";

import tiles from "./PnlPage.module.css";

const rupees = (value: string) => `₹${formatMoney(value)}`;

/** Bank statements and what they match (FM7, owner and accountant): upload the bank's CSV and
 * see which lines are receipts and payments we recorded, and which are not. */
export function BankPage() {
  const { user } = useAuth();
  const asOf = useToday().data?.as_of ?? "";
  const [from, setFrom] = useState<string | null>(null);
  const [to, setTo] = useState<string | null>(null);
  const dateTo = to ?? asOf;
  const dateFrom = from ?? (asOf ? addDays(asOf, -30) : "");
  const accounts = useBankAccounts();
  const statements = useStatements();
  const rec = useReconciliation(dateFrom, dateTo);
  const upload = useUploadStatement();
  const create = useCreateBankAccount();
  const [accountId, setAccountId] = useState("");
  const [newName, setNewName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const list = (accounts.data ?? []).filter((a) => a.is_active);
  const only = list.length === 1 ? list[0] : undefined;
  const chosen = accountId || (only ? String(only.id) : "");
  const r = rec.data;

  async function onFile(file: File | undefined) {
    if (!file) return;
    setError(null);
    setNote(null);
    try {
      const done = await upload.mutateAsync({ accountId: Number(chosen), file });
      setNote(
        `${file.name}: ${done.row_count - done.skipped_count} lines added` +
          (done.skipped_count ? `, ${done.skipped_count} already held.` : "."),
      );
    } catch (err) {
      setError(toFormError(err).message);
    }
  }

  async function addAccount(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      const made = await create.mutateAsync({ name: newName.trim() });
      setAccountId(String(made.id));
      setNewName("");
    } catch (err) {
      setError(toFormError(err).message);
    }
  }

  return (
    <div className={styles.stack}>
      <div className={styles.filters}>
        <TextField
          label="From"
          type="date"
          value={dateFrom}
          onChange={(e) => setFrom(e.target.value)}
        />
        <TextField label="To" type="date" value={dateTo} onChange={(e) => setTo(e.target.value)} />
        {list.length > 0 ? (
          <SelectField
            label="Bank account"
            value={chosen}
            onChange={(e) => setAccountId(e.target.value)}
          >
            <option value="">Choose…</option>
            {list.map((a) => (
              <option key={a.id} value={a.id}>
                {a.name}
              </option>
            ))}
          </SelectField>
        ) : null}
        <TextField
          label="Bank statement (CSV)"
          type="file"
          accept=".csv,text/csv"
          disabled={chosen === ""}
          hint={chosen === "" ? "Add or choose a bank account first." : undefined}
          onChange={(e) => {
            void onFile(e.target.files?.[0]);
            e.target.value = "";
          }}
        />
      </div>
      {user?.role === "owner" ? (
        <form onSubmit={(e) => void addAccount(e)} className={styles.filters}>
          <TextField
            label="New bank account"
            value={newName}
            maxLength={60}
            placeholder="SBI current"
            onChange={(e) => setNewName(e.target.value)}
          />
          <Button type="submit" disabled={newName.trim() === "" || create.isPending}>
            Add account
          </Button>
        </form>
      ) : null}
      {error ? (
        <p role="alert" className={styles.formError}>
          {error}
        </p>
      ) : null}
      {note ? <p role="status">{note}</p> : null}

      {r ? (
        <>
          <dl className={tiles.tiles}>
            <Metric
              code="bank_unmatched_lines"
              label="Bank lines with no entry"
              value={String(r.unmatched_count)}
              note={`of ${r.line_count} lines · money in ${rupees(r.unmatched_in)}, out ${rupees(r.unmatched_out)}`}
            />
            <Metric
              code="bank_not_received"
              label="Recorded, not in the bank"
              value={rupees(r.not_in_bank_total)}
              note={`${r.not_in_bank.length} entries, such as a UPI payment that never arrived`}
            />
            <Metric
              code="bank_statement_balance"
              label="Balance on the statement"
              value={r.last_balance == null ? "—" : rupees(r.last_balance)}
              note={r.last_balance_date ? `As at ${r.last_balance_date}` : "No statement yet."}
            />
          </dl>
          <p className={styles.note}>
            A line matches an entry of the same amount and direction dated within {r.window_days}{" "}
            days; a matching UPI or bank reference wins. Matching is worked out each time you open
            this page.
          </p>
          <div className={styles.tableWrap}>
            <table className={styles.table} aria-label="Bank lines">
              <thead>
                <tr>
                  <th scope="col">Date</th>
                  <th scope="col">Narration</th>
                  <th scope="col" className="num">
                    Out
                  </th>
                  <th scope="col" className="num">
                    In
                  </th>
                  <th scope="col">Matches</th>
                </tr>
              </thead>
              <tbody>
                {r.lines.map((l) => (
                  <tr key={l.id}>
                    <td>{l.line_date}</td>
                    <td>{l.narration}</td>
                    <td className="num">{Number(l.debit) ? formatMoney(l.debit) : ""}</td>
                    <td className="num">{Number(l.credit) ? formatMoney(l.credit) : ""}</td>
                    <td>
                      {l.matched ? (
                        <>
                          {l.matched_label}{" "}
                          <span className={styles.sub}>
                            {l.matched_how === "reference" ? "by reference" : "by amount and date"}
                          </span>
                        </>
                      ) : (
                        <strong>No entry in our books</strong>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {r.lines.length === 0 ? (
              <p className={styles.empty}>No bank lines in these dates. Upload a statement.</p>
            ) : null}
          </div>

          <h2 style={{ margin: 0 }}>In our books, not on the statement</h2>
          <div className={styles.tableWrap}>
            <table className={styles.table} aria-label="Recorded but not in the bank">
              <thead>
                <tr>
                  <th scope="col">Date</th>
                  <th scope="col">Entry</th>
                  <th scope="col">How</th>
                  <th scope="col">Reference</th>
                  <th scope="col" className="num">
                    Amount
                  </th>
                </tr>
              </thead>
              <tbody>
                {r.not_in_bank.map((b) => (
                  <tr key={b.key}>
                    <td>{b.entry_date}</td>
                    <td>
                      {b.label}{" "}
                      <span className={styles.sub}>{b.money_in ? "money in" : "money out"}</span>
                    </td>
                    <td>{b.mode}</td>
                    <td className={styles.code}>{b.reference ?? ""}</td>
                    <td className="num">₹{formatMoney(b.amount)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {r.not_in_bank.length === 0 ? (
              <p className={styles.empty}>Everything recorded is on the statement.</p>
            ) : null}
          </div>
        </>
      ) : null}

      {statements.data && statements.data.length > 0 ? (
        <>
          <h2 style={{ margin: 0 }}>Statements uploaded</h2>
          <div className={styles.tableWrap}>
            <table className={styles.table} aria-label="Statements uploaded">
              <thead>
                <tr>
                  <th scope="col">File</th>
                  <th scope="col">Account</th>
                  <th scope="col">Dates</th>
                  <th scope="col" className="num">
                    Lines
                  </th>
                  <th scope="col">By</th>
                </tr>
              </thead>
              <tbody>
                {statements.data.map((s) => (
                  <tr key={s.id}>
                    <td>{s.filename}</td>
                    <td>{s.bank_account_name}</td>
                    <td>
                      {s.from_date} to {s.to_date}
                    </td>
                    <td className="num">
                      {s.row_count - s.skipped_count}
                      {s.skipped_count ? ` (+${s.skipped_count} held)` : ""}
                    </td>
                    <td>{s.imported_by_name}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      ) : null}
    </div>
  );
}
