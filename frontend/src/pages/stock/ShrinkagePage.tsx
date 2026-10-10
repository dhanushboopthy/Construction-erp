import { useState } from "react";

import { useShrinkage } from "@/api/inventory";
import { TextField } from "@/components/Field";
import styles from "@/components/Ledger.module.css";
import { Metric } from "@/components/Metric";
import { formatMoney, trimDecimal } from "@/lib/format";
import tiles from "@/pages/reports/PnlPage.module.css";

const rupees = (value: string) => `₹${formatMoney(value)}`;

/** Weight shortages by supplier (FM6): what the bill said against what the weighbridge showed,
 * with the lines to claim back. The last 90 days unless dates are chosen. */
export function ShrinkagePage() {
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const report = useShrinkage(from, to);
  const s = report.data;

  return (
    <div className={styles.stack}>
      <div className={styles.filters}>
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
          The weight shortages could not be loaded.
        </p>
      ) : null}
      {s ? (
        <>
          <dl className={tiles.tiles}>
            <Metric
              code="shrinkage_value"
              label="Weight shortage value"
              value={rupees(s.shortage_value)}
              note={`From ${s.date_from} to ${s.date_to}.`}
            />
          </dl>
          <div className={styles.tableWrap}>
            <table className={styles.table} aria-label="Shortages by supplier">
              <thead>
                <tr>
                  <th scope="col">Supplier</th>
                  <th scope="col" className="num">
                    Bill lines
                  </th>
                  <th scope="col" className="num">
                    Short lines
                  </th>
                  <th scope="col" className="num">
                    Goods billed
                  </th>
                  <th scope="col" className="num">
                    Short by
                  </th>
                  <th scope="col" className="num">
                    Value
                  </th>
                </tr>
              </thead>
              <tbody>
                {s.suppliers.map((x) => (
                  <tr key={x.party_id}>
                    <th scope="row">{x.party_name}</th>
                    <td className="num">{x.lines}</td>
                    <td className="num">{x.short_lines}</td>
                    <td className="num">{rupees(x.goods_value)}</td>
                    <td className="num">{x.shortage_pct == null ? "—" : `${x.shortage_pct}%`}</td>
                    <td className="num">{rupees(x.shortage_value)}</td>
                  </tr>
                ))}
                {s.suppliers.length === 0 ? (
                  <tr>
                    <td colSpan={6} className={styles.empty}>
                      No supplier bills in these dates.
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
          {s.claims.length > 0 ? (
            <>
              <h2 style={{ margin: 0 }}>Lines to claim</h2>
              <div className={styles.tableWrap}>
                <table className={styles.table} aria-label="Shortage claims">
                  <thead>
                    <tr>
                      <th scope="col">Bill</th>
                      <th scope="col">Date</th>
                      <th scope="col">Supplier</th>
                      <th scope="col">Item</th>
                      <th scope="col" className="num">
                        Billed
                      </th>
                      <th scope="col" className="num">
                        Received
                      </th>
                      <th scope="col" className="num">
                        Short
                      </th>
                      <th scope="col" className="num">
                        Value
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {s.claims.map((c) => (
                      <tr key={`${c.purchase_number}-${c.item_name}`}>
                        <th scope="row">
                          {c.purchase_number} <span className={styles.sub}>{c.bill_no}</span>
                        </th>
                        <td>{c.bill_date}</td>
                        <td>{c.party_name}</td>
                        <td>{c.item_name}</td>
                        <td className="num">
                          {trimDecimal(c.billed_qty)} {c.base_unit}
                        </td>
                        <td className="num">{trimDecimal(c.received_qty)}</td>
                        <td className="num">
                          {trimDecimal(c.shortage_qty)} ({c.loss_pct}%)
                        </td>
                        <td className="num">{rupees(c.value)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          ) : null}
        </>
      ) : null}
    </div>
  );
}
