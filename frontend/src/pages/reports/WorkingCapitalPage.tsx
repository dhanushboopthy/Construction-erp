import { useState } from "react";

import { useWorkingCapital } from "@/api/receivables";
import { useToday } from "@/api/reports";
import { TextField } from "@/components/Field";
import styles from "@/components/Ledger.module.css";
import { Metric } from "@/components/Metric";
import { formatMoney } from "@/lib/format";

import tiles from "./PnlPage.module.css";

const rupees = (value: string) => `₹${formatMoney(value)}`;
const days = (value: string | null | undefined) => (value == null ? "—" : value);

/** Working capital for a month (FM5, owner only): how many days money is out of your hands, and
 * how much is tied up in stock, customers' dues and supplier advances. */
export function WorkingCapitalPage() {
  const asOf = useToday().data?.as_of ?? "";
  const [picked, setPicked] = useState<string | null>(null);
  const period = picked ?? asOf.slice(0, 7);
  const report = useWorkingCapital(period);
  const w = report.data;
  const missing = "Not enough data yet";

  return (
    <div className={styles.stack}>
      <div className={styles.filters}>
        <TextField
          label="Month"
          type="month"
          value={period}
          max={asOf.slice(0, 7) || undefined}
          onChange={(e) => setPicked(e.target.value)}
        />
      </div>
      {report.isError ? (
        <p role="alert" className={styles.formError}>
          The working capital could not be loaded.
        </p>
      ) : null}
      {w?.data_note ? <p className={styles.callout}>{w.data_note}</p> : null}

      {w ? (
        <>
          <dl className={tiles.tiles}>
            <Metric
              code="ccc_days"
              label="Cash conversion cycle"
              value={w.ccc_days == null ? "—" : `${w.ccc_days} days`}
              note={w.ccc_days == null ? `${missing}.` : undefined}
            />
            <Metric
              code="dio_days"
              label="Days inventory outstanding"
              value={w.dio_days == null ? "—" : `${w.dio_days} days`}
            />
            <Metric
              code="dso_days"
              label="Days sales outstanding"
              value={w.dso_days == null ? "—" : `${w.dso_days} days`}
              note={
                w.enough_data && w.dso_days == null
                  ? "No credit sales this month, so there is nothing to measure."
                  : undefined
              }
            />
            <Metric
              code="dpo_days"
              label="Days payables outstanding"
              value={w.dpo_days == null ? "—" : `${w.dpo_days} days`}
            />
            <Metric
              code="advance_days"
              label="Supplier advance days"
              value={w.advance_days == null ? "—" : `${w.advance_days} days`}
            />
            <Metric code="cash_tied_up" label="Cash tied up" value={rupees(w.cash_tied_up)} />
            <Metric
              code="working_capital"
              label="Working capital"
              value={rupees(w.working_capital)}
            />
            <Metric
              code="inventory_turnover"
              label="Inventory turnover"
              value={w.inventory_turnover == null ? "—" : `${w.inventory_turnover} times`}
            />
            <Metric
              code="collection_efficiency_pct"
              label="Collection efficiency"
              value={w.collection_efficiency_pct == null ? "—" : `${w.collection_efficiency_pct}%`}
            />
          </dl>

          <div className={styles.tableWrap}>
            <table className={styles.table} aria-label="Balances and flows">
              <thead>
                <tr>
                  <th scope="col">Balance</th>
                  <th scope="col" className="num">
                    Start of month
                  </th>
                  <th scope="col" className="num">
                    End of month
                  </th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <th scope="row">Stock at cost</th>
                  <td className="num">{rupees(w.stock_start)}</td>
                  <td className="num">{rupees(w.stock_end)}</td>
                </tr>
                <tr>
                  <th scope="row">Customers owe</th>
                  <td className="num">{rupees(w.receivables_start)}</td>
                  <td className="num">{rupees(w.receivables_end)}</td>
                </tr>
                <tr>
                  <th scope="row">Advances paid to suppliers</th>
                  <td className="num">{rupees(w.advances_start)}</td>
                  <td className="num">{rupees(w.advances_end)}</td>
                </tr>
                <tr>
                  <th scope="row">We owe suppliers</th>
                  <td className="num">{rupees(w.payables_start)}</td>
                  <td className="num">{rupees(w.payables_end)}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <p className={styles.note}>
            Over {w.days} days: cost of goods sold {rupees(w.cogs)} · credit sales{" "}
            {rupees(w.credit_sales)} · purchases {rupees(w.purchases)} · collected{" "}
            {rupees(w.collections)}. Days are worked out on the average of the start and end
            balances. Working capital leaves out cash and bank balances.
          </p>

          <h2 style={{ margin: 0 }}>Last six months</h2>
          <div className={styles.tableWrap}>
            <table className={styles.table} aria-label="Trend by month">
              <thead>
                <tr>
                  <th scope="col">Month</th>
                  <th scope="col" className="num">
                    Stock days
                  </th>
                  <th scope="col" className="num">
                    Customer days
                  </th>
                  <th scope="col" className="num">
                    Advance days
                  </th>
                  <th scope="col" className="num">
                    Supplier days
                  </th>
                  <th scope="col" className="num">
                    Cycle
                  </th>
                  <th scope="col" className="num">
                    Cash tied up
                  </th>
                </tr>
              </thead>
              <tbody>
                {w.trend.map((p) => (
                  <tr key={p.period}>
                    <th scope="row">{p.period}</th>
                    <td className="num">{days(p.dio_days)}</td>
                    <td className="num">{days(p.dso_days)}</td>
                    <td className="num">{days(p.advance_days)}</td>
                    <td className="num">{days(p.dpo_days)}</td>
                    <td className="num">{days(p.ccc_days)}</td>
                    <td className="num">{rupees(p.cash_tied_up)}</td>
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
