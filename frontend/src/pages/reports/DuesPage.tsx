import { useState } from "react";

import { useDues } from "@/api/ledger";
import type { LedgerAccount } from "@/api/types";
import { SelectField } from "@/components/Field";
import styles from "@/components/Ledger.module.css";
import { formatMoney, plural } from "@/lib/format";

/** Who owes us, or whom we owe, with how old the money is (the weekly dues list). */
export function DuesPage() {
  const [account, setAccount] = useState<LedgerAccount>("receivable");
  const dues = useDues(account);
  const d = dues.data;
  return (
    <div className={styles.stack}>
      <div className={styles.filters}>
        <SelectField
          label="List"
          value={account}
          onChange={(e) => setAccount(e.target.value as LedgerAccount)}
        >
          <option value="receivable">Customers owe us</option>
          <option value="payable">We owe suppliers</option>
        </SelectField>
      </div>
      {d && d.rows.length === 0 ? <p className={styles.empty}>Nothing is outstanding.</p> : null}
      {d && d.rows.length > 0 ? (
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th scope="col">Name</th>
                <th scope="col" className="num">
                  Owed (₹)
                </th>
                <th scope="col" className="num">
                  Up to 30 days
                </th>
                <th scope="col" className="num">
                  31 to 60
                </th>
                <th scope="col" className="num">
                  Over 60
                </th>
                <th scope="col">Oldest bill</th>
              </tr>
            </thead>
            <tbody>
              {d.rows.map((r) => (
                <tr key={r.party_id}>
                  <th scope="row" style={{ fontWeight: 500, color: "inherit" }}>
                    {r.party_name}
                  </th>
                  <td className="num">{formatMoney(r.balance)}</td>
                  <td className="num">{formatMoney(r.aging.up_to_30)}</td>
                  <td className="num">{formatMoney(r.aging.days_31_60)}</td>
                  <td className="num">{formatMoney(r.aging.over_60)}</td>
                  <td>{r.oldest_date ?? "—"}</td>
                </tr>
              ))}
              <tr>
                <th scope="row">Total</th>
                <td className="num">
                  <strong>{formatMoney(d.total)}</strong>
                </td>
                <td colSpan={4} />
              </tr>
            </tbody>
          </table>
          <p className={styles.results}>{plural(d.rows.length, "party", "parties")}</p>
        </div>
      ) : null}
    </div>
  );
}
