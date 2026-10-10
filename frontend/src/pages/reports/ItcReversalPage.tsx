import { useState } from "react";

import { useItcReversal } from "@/api/adjustments";
import { useToday } from "@/api/reports";
import { TextField } from "@/components/Field";
import styles from "@/components/Ledger.module.css";
import { Metric } from "@/components/Metric";
import { formatMoney, trimDecimal } from "@/lib/format";

/** Input tax to take back in GSTR-3B for goods lost in the month (FM2, owner and accountant). */
export function ItcReversalPage() {
  const asOf = useToday().data?.as_of ?? "";
  const [picked, setPicked] = useState<string | null>(null);
  const period = picked ?? asOf.slice(0, 7);
  const report = useItcReversal(period);
  const r = report.data;

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
          The ITC list could not be loaded.
        </p>
      ) : null}
      {r ? (
        <>
          <dl className={styles.totalBand}>
            <Metric
              code="itc_to_reverse"
              label="ITC to reverse"
              value={`₹${formatMoney(r.total_itc)}`}
              note={`On goods worth ₹${formatMoney(r.total_value)} lost this month.`}
            />
          </dl>
          <p className={styles.note}>{r.note}</p>
          <div className={styles.tableWrap}>
            <table className={styles.table} aria-label="ITC to reverse">
              <thead>
                <tr>
                  <th scope="col">Date</th>
                  <th scope="col">Document</th>
                  <th scope="col">Item</th>
                  <th scope="col">HSN</th>
                  <th scope="col">Reason</th>
                  <th scope="col" className="num">
                    Quantity
                  </th>
                  <th scope="col" className="num">
                    Value
                  </th>
                  <th scope="col" className="num">
                    GST %
                  </th>
                  <th scope="col" className="num">
                    ITC
                  </th>
                </tr>
              </thead>
              <tbody>
                {r.rows.map((row, i) => (
                  <tr key={i}>
                    <td>{row.entry_date}</td>
                    <td className={styles.code}>
                      {row.document} <span className={styles.sub}>{row.location_code}</span>
                    </td>
                    <td>{row.item_name}</td>
                    <td>{row.hsn}</td>
                    <td>{row.reason_label}</td>
                    <td className="num">
                      {trimDecimal(row.quantity)} {row.base_unit}
                    </td>
                    <td className="num">₹{formatMoney(row.value)}</td>
                    <td className="num">{trimDecimal(row.gst_rate)}</td>
                    <td className="num">₹{formatMoney(row.itc)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {r.rows.length === 0 ? (
              <p className={styles.empty}>No goods lost this month: nothing to reverse.</p>
            ) : null}
          </div>
        </>
      ) : null}
    </div>
  );
}
