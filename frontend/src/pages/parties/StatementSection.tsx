import { useState } from "react";

import { useStatement } from "@/api/ledger";
import type { AccountView, Party } from "@/api/types";
import styles from "@/components/Ledger.module.css";
import { SelectField } from "@/components/Field";
import { formatMoney } from "@/lib/format";

function AccountBlock({ view, title }: { view: AccountView; title: string }) {
  const owed = Number(view.balance);
  return (
    <div className={styles.stack}>
      <h4 style={{ margin: 0 }}>{title}</h4>
      <p className={styles.resultBox}>
        <strong className={owed < 0 ? styles.negative : undefined}>
          {owed < 0
            ? `Advance held ₹${formatMoney(String(-owed))}`
            : `₹${formatMoney(view.balance)}`}
        </strong>
        {Number(view.balance) > 0 ? (
          <span className={styles.sub}>
            {" "}
            · 0–30 days ₹{formatMoney(view.aging.up_to_30)} · 31–60 ₹
            {formatMoney(view.aging.days_31_60)} · over 60 ₹{formatMoney(view.aging.over_60)}
          </span>
        ) : null}
      </p>
      {view.entries.length > 0 ? (
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th scope="col">Date</th>
                <th scope="col">For</th>
                <th scope="col" className="num">
                  Debit
                </th>
                <th scope="col" className="num">
                  Credit
                </th>
                <th scope="col" className="num">
                  Balance
                </th>
              </tr>
            </thead>
            <tbody>
              {view.entries.map((e) => (
                <tr key={e.id}>
                  <td>{e.entry_date}</td>
                  <td>{e.doc_no ?? e.ref_type}</td>
                  <td className="num">{Number(e.debit) ? formatMoney(e.debit) : ""}</td>
                  <td className="num">{Number(e.credit) ? formatMoney(e.credit) : ""}</td>
                  <td className="num">{formatMoney(e.running_balance)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className={styles.sub}>No entries yet.</p>
      )}
    </div>
  );
}

/** Balance, aging and entries of a party, per site when one is picked (B9). */
export function StatementSection({ party }: { party: Party }) {
  const [siteId, setSiteId] = useState("");
  const statement = useStatement(party.id, siteId ? Number(siteId) : undefined);
  return (
    <section className={styles.subsection} aria-labelledby={`stmt-${party.id}`}>
      <h3 id={`stmt-${party.id}`}>Statement</h3>
      {party.sites.length > 0 ? (
        <SelectField label="Show" value={siteId} onChange={(e) => setSiteId(e.target.value)}>
          <option value="">All sites together</option>
          {party.sites.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name}
            </option>
          ))}
        </SelectField>
      ) : null}
      {statement.isPending ? <p role="status">Loading statement…</p> : null}
      {statement.data?.receivable ? (
        <AccountBlock view={statement.data.receivable} title="Customer owes us" />
      ) : null}
      {statement.data?.payable ? (
        <AccountBlock view={statement.data.payable} title="We owe the supplier" />
      ) : null}
    </section>
  );
}
