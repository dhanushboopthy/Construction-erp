import { useState } from "react";

import { usePnl } from "@/api/finance";
import { useToday } from "@/api/reports";
import { SelectField, TextField } from "@/components/Field";
import styles from "@/components/Ledger.module.css";
import { Metric } from "@/components/Metric";
import { useShops } from "@/hooks/useShops";
import { formatMoney } from "@/lib/format";

import pnl from "./PnlPage.module.css";

function rupees(value: string | null | undefined) {
  if (value == null) return "—";
  const n = Number(value);
  return `${n < 0 ? "−" : ""}₹${formatMoney(String(Math.abs(n)))}`;
}

const NATURE = { fixed: "Fixed", variable: "Variable", interest: "Interest" } as const;

/** Profit and loss for a calendar month (FM1, owner only): what trading earned, what running
 * the shop cost, and the sales needed to break even. */
export function PnlPage() {
  const asOf = useToday().data?.as_of ?? "";
  const [picked, setPicked] = useState<string | null>(null);
  const period = picked ?? asOf.slice(0, 7);
  const { shops, single } = useShops();
  const [shopId, setShopId] = useState("");
  const report = usePnl(period, single ? "" : shopId);
  const p = report.data;

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
        {single ? null : (
          <SelectField label="Shop" value={shopId} onChange={(e) => setShopId(e.target.value)}>
            <option value="">Whole business</option>
            {shops.map((s) => (
              <option key={s.id} value={s.id}>
                {s.code} {s.name}
              </option>
            ))}
          </SelectField>
        )}
      </div>

      {report.isError ? (
        <p role="alert" className={styles.formError}>
          The profit and loss could not be loaded.
        </p>
      ) : null}
      {p?.data_note ? <p className={styles.callout}>{p.data_note}</p> : null}

      {p ? (
        <>
          <dl className={pnl.tiles}>
            <Metric code="net_sales" label="Net sales" value={rupees(p.net_sales)} />
            <Metric
              code="gross_profit"
              label="Gross profit"
              value={rupees(p.gross_profit)}
              note={p.gross_margin_pct != null ? `${p.gross_margin_pct}% of net sales.` : undefined}
            />
            <Metric
              code="net_profit"
              label="Net profit"
              value={rupees(p.net_profit)}
              tone={Number(p.net_profit) < 0 ? "critical" : "good"}
            />
            <Metric
              code="break_even_sales"
              label="Break-even sales"
              value={rupees(p.break_even_sales)}
              note={
                p.break_even_sales == null
                  ? "Not enough data yet: needs sales with a positive contribution."
                  : Number(p.net_sales) >= Number(p.break_even_sales)
                    ? "Sales are above break-even this month."
                    : `₹${formatMoney(String(Number(p.break_even_sales) - Number(p.net_sales)))} more sales to break even.`
              }
            />
          </dl>

          <div className={styles.tableWrap}>
            <table className={styles.table} aria-label="Profit and loss">
              <tbody>
                <tr>
                  <th scope="row">Sales (bills, excl. GST)</th>
                  <td className="num">{rupees(p.sales)}</td>
                </tr>
                <tr>
                  <th scope="row">Less returns</th>
                  <td className="num">{rupees(p.returns)}</td>
                </tr>
                <tr className={pnl.subtotal}>
                  <th scope="row">Net sales</th>
                  <td className="num">{rupees(p.net_sales)}</td>
                </tr>
                <tr>
                  <th scope="row">Less cost of goods sold</th>
                  <td className="num">{rupees(p.cogs)}</td>
                </tr>
                <tr>
                  <th scope="row">Less freight on sales</th>
                  <td className="num">{rupees(p.freight)}</td>
                </tr>
                <tr>
                  <th scope="row">
                    {Number(p.stock_loss) < 0 ? "Add stock gained" : "Less stock lost"}{" "}
                    <span className={styles.sub}>breakage, theft, shortages</span>
                  </th>
                  <td className="num">{rupees(String(Math.abs(Number(p.stock_loss))))}</td>
                </tr>
                <tr className={pnl.subtotal}>
                  <th scope="row">Gross profit</th>
                  <td className="num">{rupees(p.gross_profit)}</td>
                </tr>
                {p.expenses
                  .filter((e) => e.nature !== "interest")
                  .map((e) => (
                    <tr key={e.category}>
                      <th scope="row">
                        Less {e.category} <span className={styles.sub}>{NATURE[e.nature]}</span>
                      </th>
                      <td className="num">{rupees(e.amount)}</td>
                    </tr>
                  ))}
                <tr className={pnl.subtotal}>
                  <th scope="row">EBITDA (before interest)</th>
                  <td className="num">{rupees(p.ebitda)}</td>
                </tr>
                <tr>
                  <th scope="row">Less interest and bank charges</th>
                  <td className="num">{rupees(p.interest)}</td>
                </tr>
                {Number(p.write_downs) > 0 ? (
                  <tr>
                    <th scope="row">
                      Less stock written down to market value{" "}
                      <span className={styles.sub}>no GST reversed</span>
                    </th>
                    <td className="num">{rupees(p.write_downs)}</td>
                  </tr>
                ) : null}
                {Number(p.bad_debts) > 0 ? (
                  <tr>
                    <th scope="row">
                      Less bad debts written off <span className={styles.sub}>no GST effect</span>
                    </th>
                    <td className="num">{rupees(p.bad_debts)}</td>
                  </tr>
                ) : null}
                <tr className={pnl.total}>
                  <th scope="row">Net profit</th>
                  <td className="num">{rupees(p.net_profit)}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <p className={styles.note}>
            Fixed costs {rupees(p.fixed_costs)} · variable costs {rupees(p.variable_costs)} ·
            contribution {rupees(p.contribution)}. Expenses come from the cash book; record them
            there to see the true profit.
          </p>
        </>
      ) : null}
    </div>
  );
}
