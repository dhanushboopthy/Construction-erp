import { useState } from "react";

import { useProfit } from "@/api/reports";
import type { ProfitGroup } from "@/api/types";
import { SelectField, TextField } from "@/components/Field";
import styles from "@/components/Ledger.module.css";
import { formatMoney } from "@/lib/format";

function iso(offsetDays: number): string {
  const d = new Date(Date.now() - offsetDays * 86_400_000);
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
}

const GROUPS: { value: ProfitGroup; label: string }[] = [
  { value: "item", label: "By item" },
  { value: "customer", label: "By customer" },
  { value: "site", label: "By site" },
];

/** Owner only. Sales less returns, less cost, less freight. */
export function ProfitPage() {
  const [group, setGroup] = useState<ProfitGroup>("item");
  const [from, setFrom] = useState(() => iso(30));
  const [to, setTo] = useState(() => iso(0));
  const report = useProfit(group, from, to);
  const r = report.data;
  return (
    <div className={styles.stack}>
      <div className={styles.filters}>
        <SelectField
          label="Group"
          value={group}
          onChange={(e) => setGroup(e.target.value as ProfitGroup)}
        >
          {GROUPS.map((g) => (
            <option key={g.value} value={g.value}>
              {g.label}
            </option>
          ))}
        </SelectField>
        <TextField
          label="From"
          type="date"
          value={from}
          onChange={(e) => setFrom(e.target.value)}
        />
        <TextField label="To" type="date" value={to} onChange={(e) => setTo(e.target.value)} />
      </div>
      {report.isError ? (
        <p role="alert" className={styles.formError}>
          The report could not be made. Check the dates (up to a year).
        </p>
      ) : null}
      {r && r.rows.length === 0 ? <p className={styles.empty}>No sales in these dates.</p> : null}
      {r && r.rows.length > 0 ? (
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th scope="col">
                  {GROUPS.find((g) => g.value === group)?.label.replace("By ", "")}
                </th>
                <th scope="col" className="num">
                  Sales (₹)
                </th>
                <th scope="col" className="num">
                  Cost (₹)
                </th>
                <th scope="col" className="num">
                  Freight (₹)
                </th>
                <th scope="col" className="num">
                  Profit (₹)
                </th>
                <th scope="col" className="num">
                  Margin
                </th>
              </tr>
            </thead>
            <tbody>
              {r.rows.map((x) => (
                <tr key={x.key}>
                  <th scope="row" style={{ fontWeight: 500, color: "inherit" }}>
                    {x.key}
                  </th>
                  <td className="num">{formatMoney(x.taxable)}</td>
                  <td className="num">{formatMoney(x.cost)}</td>
                  <td className="num">{formatMoney(x.freight)}</td>
                  <td className="num">{formatMoney(x.profit)}</td>
                  <td className="num">{x.margin_pct ? `${x.margin_pct}%` : "—"}</td>
                </tr>
              ))}
              <tr>
                <th scope="row">Total</th>
                <td className="num">{formatMoney(r.taxable)}</td>
                <td className="num">{formatMoney(r.cost)}</td>
                <td className="num">{formatMoney(r.freight)}</td>
                <td className="num">
                  <strong>{formatMoney(r.profit)}</strong>
                </td>
                <td />
              </tr>
            </tbody>
          </table>
        </div>
      ) : null}
    </div>
  );
}
