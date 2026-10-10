import { useState } from "react";

import { useMatchReport } from "@/api/orders";
import { useToday } from "@/api/reports";
import { CheckField, TextField } from "@/components/Field";
import styles from "@/components/Ledger.module.css";
import { Metric } from "@/components/Metric";
import { addDays } from "@/lib/dates";
import { formatMoney, trimDecimal } from "@/lib/format";

import tiles from "./PnlPage.module.css";

/** Supplier bills that differ from their purchase order beyond the tolerances, and the purchase
 * price variance on every bill that has an order (FM10, owner only). */
export function OrderMatchPage() {
  const asOf = useToday().data?.as_of ?? "";
  const [from, setFrom] = useState<string | null>(null);
  const [to, setTo] = useState<string | null>(null);
  const [all, setAll] = useState(false);
  const dateTo = to ?? asOf;
  const dateFrom = from ?? (asOf ? addDays(asOf, -30) : "");
  const report = useMatchReport(dateFrom, dateTo, all);
  const r = report.data;

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
        <CheckField
          label="Show every line, not only the exceptions"
          checked={all}
          onChange={(e) => setAll(e.target.checked)}
        />
      </div>
      {report.isError ? (
        <p role="alert" className={styles.formError}>
          The report could not be loaded.
        </p>
      ) : null}
      {r ? (
        <>
          <dl className={tiles.tiles}>
            <Metric
              code="ppv"
              label="Purchase price variance"
              value={`${Number(r.ppv_total) < 0 ? "−" : ""}₹${formatMoney(String(Math.abs(Number(r.ppv_total))))}`}
              tone={Number(r.ppv_total) > 0 ? "critical" : undefined}
              note={`${r.bills_checked} bills against an order, ${r.exceptions} out of tolerance. A plus figure is money paid above the order rate.`}
            />
          </dl>
          <div className={styles.tableWrap}>
            <table className={styles.table} aria-label="Order match exceptions">
              <thead>
                <tr>
                  <th scope="col">Bill</th>
                  <th scope="col">Order</th>
                  <th scope="col">Supplier</th>
                  <th scope="col">Item</th>
                  <th scope="col" className="num">
                    Ordered
                  </th>
                  <th scope="col" className="num">
                    Received
                  </th>
                  <th scope="col" className="num">
                    Billed
                  </th>
                  <th scope="col" className="num">
                    Order rate
                  </th>
                  <th scope="col" className="num">
                    Bill rate
                  </th>
                  <th scope="col" className="num">
                    PPV (₹)
                  </th>
                  <th scope="col">What differs</th>
                </tr>
              </thead>
              <tbody>
                {r.rows.map((row, i) => (
                  <tr key={`${row.purchase_id}-${i}`}>
                    <td>
                      {row.bill_no} <span className={styles.sub}>{row.bill_date}</span>
                    </td>
                    <td className={styles.code}>{row.order_number}</td>
                    <td>{row.supplier_name}</td>
                    <td>{row.item_name}</td>
                    <td className="num">
                      {trimDecimal(row.ordered_qty)} {row.base_unit}
                    </td>
                    <td className="num">{trimDecimal(row.received_qty)}</td>
                    <td className="num">{trimDecimal(row.billed_qty)}</td>
                    <td className="num">{row.order_rate ? formatMoney(row.order_rate) : "—"}</td>
                    <td className="num">{formatMoney(row.bill_rate)}</td>
                    <td className="num">{formatMoney(row.ppv)}</td>
                    <td>
                      {row.ok ? "Within tolerance" : row.reasons.join(" ")}{" "}
                      {!row.ok ? (
                        <strong>
                          {row.approved
                            ? "(approved with the owner's PIN)"
                            : row.entered_by_owner
                              ? "(entered by the owner)"
                              : ""}
                        </strong>
                      ) : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {r.rows.length === 0 ? (
              <p className={styles.empty}>
                No bills against orders differ from them in these dates.
              </p>
            ) : null}
          </div>
          <p className={styles.note}>
            Tolerances (Settings): bill quantity up to {r.qty_tolerance_pct}% over what was received
            or ordered, rate up to {r.rate_tolerance_pct}% over the order rate.
          </p>
        </>
      ) : null}
    </div>
  );
}
