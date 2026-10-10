import { useState } from "react";
import { Link } from "react-router";

import { useExceptions } from "@/api/controls";
import { useToday } from "@/api/reports";
import { TextField } from "@/components/Field";
import styles from "@/components/Ledger.module.css";
import { Metric } from "@/components/Metric";
import { addDays } from "@/lib/dates";
import { formatMoney } from "@/lib/format";

import tiles from "./PnlPage.module.css";

/** Entries that look like the usual ways money or stock goes missing (FM7, owner only). A flag
 * is a reason to ask someone, not a finding. */
export function ExceptionsPage() {
  const asOf = useToday().data?.as_of ?? "";
  const [from, setFrom] = useState<string | null>(null);
  const [to, setTo] = useState<string | null>(null);
  const dateTo = to ?? asOf;
  const dateFrom = from ?? (asOf ? addDays(asOf, -29) : "");
  const report = useExceptions(dateFrom, dateTo);
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
      </div>
      {report.isError ? (
        <p role="alert" className={styles.formError}>
          The exception report could not be loaded.
        </p>
      ) : null}
      {r ? (
        <>
          <dl className={tiles.tiles}>
            <Metric
              code="exceptions_flagged"
              label="Entries flagged"
              value={String(r.rows.length)}
              tone={r.rows.length === 0 ? "good" : undefined}
            />
          </dl>
          <ul className={styles.pillRow} aria-label="Flags by kind">
            {r.counts
              .filter((c) => c.count > 0)
              .map((c) => (
                <li key={c.code} className={styles.pill}>
                  {c.title}: {c.count}
                </li>
              ))}
          </ul>
          <div className={styles.tableWrap}>
            <table className={styles.table} aria-label="Flagged entries">
              <thead>
                <tr>
                  <th scope="col">Date</th>
                  <th scope="col">What</th>
                  <th scope="col">Where</th>
                  <th scope="col">By</th>
                  <th scope="col">Document</th>
                  <th scope="col">Detail</th>
                  <th scope="col" className="num">
                    ₹
                  </th>
                </tr>
              </thead>
              <tbody>
                {r.rows.map((row, i) => (
                  <tr key={i}>
                    <td>{row.on}</td>
                    <td>{row.title}</td>
                    <td>{row.location_code ?? ""}</td>
                    <td>{row.user_name ?? ""}</td>
                    <td className={styles.code}>
                      {row.link ? (
                        <Link to={row.link}>{row.document ?? "Open"}</Link>
                      ) : (
                        (row.document ?? "")
                      )}
                    </td>
                    <td>{row.detail}</td>
                    <td className="num">{row.value ? formatMoney(row.value) : ""}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {r.rows.length === 0 ? (
              <p className={styles.empty}>Nothing flagged in these dates.</p>
            ) : null}
          </div>
          <p className={styles.note}>
            The limits behind each flag are under Settings, Bank matching and exception report.
          </p>
        </>
      ) : null}
    </div>
  );
}
