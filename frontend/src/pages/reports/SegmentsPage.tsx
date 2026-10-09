import { useState } from "react";

import { useSegments } from "@/api/reports";
import { Button } from "@/components/Button";
import styles from "@/components/Ledger.module.css";
import { formatMoney } from "@/lib/format";

const SERIES = [
  { key: "retail", label: "Retail", color: "var(--color-oxide)" },
  { key: "contractor", label: "Contractor", color: "var(--color-tag)" },
  { key: "bulk", label: "Bulk", color: "var(--color-steel)" },
  { key: "unassigned", label: "No segment", color: "var(--color-rule-strong)" },
] as const;

const MONTH = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** Monthly sales by customer segment. Empty until bills carry customers with a segment. */
export function SegmentsPage() {
  const [year, setYear] = useState<number | null>(null);
  const report = useSegments(year);
  const r = report.data;
  const peak = Math.max(1, ...(r?.months.map((m) => Number(m.total)) ?? [0]));
  const W = 720;
  const H = 220;
  const slot = W / 12;
  return (
    <div className={styles.stack}>
      {r ? (
        <div className={styles.filters}>
          <Button onClick={() => setYear(r.start_year - 1)}>Earlier year</Button>
          <strong>Financial year {r.financial_year}</strong>
          <Button onClick={() => setYear(r.start_year + 1)}>Later year</Button>
        </div>
      ) : null}
      {r && Number(r.total) === 0 ? (
        <p className={styles.empty}>No sales in this year yet. Bars appear as bills are made.</p>
      ) : null}
      {r ? (
        <>
          <svg
            viewBox={`0 0 ${W} ${H + 24}`}
            role="img"
            aria-label={`Sales by customer segment, financial year ${r.financial_year}`}
            style={{
              width: "100%",
              maxWidth: 760,
              background: "var(--color-surface)",
              border: "1px solid var(--color-rule)",
            }}
          >
            {r.months.map((m, i) => {
              let y = H;
              const [yr, mo] = m.month.split("-");
              return (
                <g key={m.month}>
                  {SERIES.map((s) => {
                    const value = Math.max(0, Number(m[s.key]));
                    const h = (value / peak) * (H - 10);
                    y -= h;
                    return h > 0 ? (
                      <rect
                        key={s.key}
                        x={i * slot + 8}
                        y={y}
                        width={slot - 16}
                        height={h}
                        fill={s.color}
                      >
                        <title>{`${s.label} ${MONTH[Number(mo) - 1]} ${yr}: ₹${formatMoney(m[s.key])}`}</title>
                      </rect>
                    ) : null;
                  })}
                  <text
                    x={i * slot + slot / 2}
                    y={H + 16}
                    textAnchor="middle"
                    fontSize="11"
                    fill="var(--color-steel)"
                  >
                    {MONTH[Number(mo) - 1]}
                  </text>
                </g>
              );
            })}
          </svg>
          <ul style={{ display: "flex", gap: 16, listStyle: "none", padding: 0, margin: 0 }}>
            {SERIES.map((s) => (
              <li key={s.key} style={{ display: "flex", gap: 6, alignItems: "center" }}>
                <span
                  aria-hidden
                  style={{ width: 12, height: 12, background: s.color, display: "inline-block" }}
                />
                {s.label}
              </li>
            ))}
          </ul>
          <div className={styles.tableWrap}>
            <table className={styles.table} aria-label="Sales by segment, month by month">
              <thead>
                <tr>
                  <th scope="col">Month</th>
                  {SERIES.map((s) => (
                    <th key={s.key} scope="col" className="num">
                      {s.label} (₹)
                    </th>
                  ))}
                  <th scope="col" className="num">
                    Total (₹)
                  </th>
                </tr>
              </thead>
              <tbody>
                {r.months.map((m) => (
                  <tr key={m.month}>
                    <th scope="row" style={{ fontWeight: 500, color: "inherit" }}>
                      {m.month}
                    </th>
                    {SERIES.map((s) => (
                      <td key={s.key} className="num">
                        {formatMoney(m[s.key])}
                      </td>
                    ))}
                    <td className="num">{formatMoney(m.total)}</td>
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
