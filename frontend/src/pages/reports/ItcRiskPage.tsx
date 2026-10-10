import { useState } from "react";

import { useItcAtRisk, useToday } from "@/api/reports";
import type { ItcRiskRow } from "@/api/types";
import { TextField } from "@/components/Field";
import styles from "@/components/Ledger.module.css";
import { Metric } from "@/components/Metric";
import { formatMoney } from "@/lib/format";

import tiles from "./PnlPage.module.css";

const rupees = (value: string) => `₹${formatMoney(value)}`;

function RiskTable({
  title,
  rows,
  partial,
}: {
  title: string;
  rows: ItcRiskRow[];
  partial: boolean;
}) {
  return (
    <>
      <h2 style={{ margin: 0 }}>{title}</h2>
      <div className={styles.tableWrap}>
        <table className={styles.table} aria-label={title}>
          <thead>
            <tr>
              <th scope="col">Supplier</th>
              <th scope="col">GSTIN</th>
              <th scope="col">Bill</th>
              <th scope="col">Date</th>
              <th scope="col" className="num">
                Taxable
              </th>
              <th scope="col" className="num">
                Input tax in books
              </th>
              {partial ? (
                <th scope="col" className="num">
                  Input tax in 2B
                </th>
              ) : null}
              <th scope="col" className="num">
                At risk
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={`${row.gstin}-${row.number}`}>
                <td>{row.supplier ?? ""}</td>
                <td className={styles.code}>{row.gstin}</td>
                <td className={styles.code}>{row.number}</td>
                <td>{row.bill_date ?? ""}</td>
                <td className="num">{formatMoney(row.taxable)}</td>
                <td className="num">{formatMoney(row.itc)}</td>
                {partial ? (
                  <td className="num">{row.portal_itc ? formatMoney(row.portal_itc) : ""}</td>
                ) : null}
                <td className="num">{formatMoney(row.at_risk)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {rows.length === 0 ? <p className={styles.empty}>None.</p> : null}
      </div>
    </>
  );
}

/** Input tax on supplier bills that GSTR-2B does not show, and the GST payable estimate
 * (FM8, owner and accountant). */
export function ItcRiskPage() {
  const asOf = useToday().data?.as_of ?? "";
  const [picked, setPicked] = useState<string | null>(null);
  const period = picked ?? asOf.slice(0, 7);
  const report = useItcAtRisk(period);
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
          The report could not be loaded.
        </p>
      ) : null}
      {r ? (
        <>
          {r.note ? (
            <p role="status" className={styles.callout}>
              {r.note}. Upload it under GST to see which input tax is at risk.
            </p>
          ) : null}
          <dl className={tiles.tiles}>
            <Metric
              code="itc_at_risk"
              label="ITC at risk"
              value={r.at_risk_total == null ? "—" : rupees(r.at_risk_total)}
              tone={r.at_risk_total != null && Number(r.at_risk_total) === 0 ? "good" : undefined}
              note={
                r.at_risk_total == null
                  ? "Not known until GSTR-2B is imported."
                  : `${rupees(r.missing_itc ?? "0")} not in 2B + ${rupees(r.mismatch_itc ?? "0")} where the supplier reported less.`
              }
            />
            <Metric
              code="gst_payable_estimate"
              label={r.payable_to_date ? "GST payable, so far this month" : "GST payable"}
              value={rupees(r.payable_estimate)}
              note={
                r.payable_if_unclaimed == null
                  ? `Due on ${r.due_date}. A minus figure is credit carried forward.`
                  : `Due on ${r.due_date}. ${rupees(r.payable_if_unclaimed)} if the input tax at risk cannot be claimed.`
              }
            />
          </dl>
          {r.has_2b ? (
            <>
              <RiskTable title="In our books, not in GSTR-2B" rows={r.missing} partial={false} />
              <RiskTable
                title="In both, but the supplier reported less tax"
                rows={r.mismatches}
                partial
              />
            </>
          ) : null}
          {Number(r.no_gstin_itc) > 0 ? (
            <p className={styles.note}>
              {rupees(r.no_gstin_itc)} of input tax this month is on bills from suppliers with no
              GSTIN. Those can never appear in GSTR-2B; ask the accountant whether it can be
              claimed.
            </p>
          ) : null}
        </>
      ) : null}
    </div>
  );
}
