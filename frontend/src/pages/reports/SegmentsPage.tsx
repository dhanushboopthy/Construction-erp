import { useState } from "react";

import { useSegments } from "@/api/reports";
import { Button } from "@/components/Button";
import styles from "@/components/Ledger.module.css";

import chart from "./SegmentsPage.module.css";
import { formatMoney } from "@/lib/format";

/** Each series has its own fill pattern as well as its own colour, so the chart reads in grey. */
const SERIES = [
  { key: "retail", label: "Retail", color: "var(--color-series-1)", pattern: "solid" },
  { key: "contractor", label: "Contractor", color: "var(--color-series-2)", pattern: "solid" },
  { key: "bulk", label: "Bulk", color: "var(--color-series-3)", pattern: "hatch" },
  { key: "unassigned", label: "No segment", color: "var(--color-series-4)", pattern: "dots" },
] as const;

/** The fill of a series: its colour, or a pattern of it on the card colour. */
const fillOf = (pattern: (typeof SERIES)[number]["pattern"], color: string, id: string) =>
  pattern === "solid" ? color : `url(#${id}-${pattern})`;

function Patterns({ id }: { id: string }) {
  const bulk = SERIES[2].color;
  const none = SERIES[3].color;
  return (
    <defs>
      <pattern
        id={`${id}-hatch`}
        width="6"
        height="6"
        patternUnits="userSpaceOnUse"
        patternTransform="rotate(45)"
      >
        <rect width="6" height="6" fill="var(--color-surface)" />
        <line x1="0" y1="0" x2="0" y2="6" stroke={bulk} strokeWidth="3.5" />
      </pattern>
      <pattern id={`${id}-dots`} width="6" height="6" patternUnits="userSpaceOnUse">
        <rect width="6" height="6" fill="var(--color-surface)" />
        <circle cx="3" cy="3" r="1.6" fill={none} />
      </pattern>
    </defs>
  );
}

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
            className={chart.chart}
          >
            <Patterns id="seg" />
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
                        fill={fillOf(s.pattern, s.color, "seg")}
                        stroke="var(--color-surface)"
                        strokeWidth="1"
                      >
                        <title>{`${s.label} ${MONTH[Number(mo) - 1]} ${yr}: ₹${formatMoney(m[s.key])}`}</title>
                      </rect>
                    ) : null;
                  })}
                  <text
                    x={i * slot + slot / 2}
                    y={H + 16}
                    textAnchor="middle"
                    className={chart.month}
                  >
                    {MONTH[Number(mo) - 1]}
                  </text>
                </g>
              );
            })}
          </svg>
          <ul className={chart.legend} aria-label="Legend">
            {SERIES.map((s) => (
              <li key={s.key} data-pattern={s.pattern}>
                <svg width="16" height="16" aria-hidden="true" className={chart.swatch}>
                  <rect
                    width="16"
                    height="16"
                    rx="3"
                    fill={fillOf(s.pattern, s.color, "seg")}
                    stroke={s.color}
                    strokeWidth="1"
                  />
                </svg>
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
                    <th scope="row" className={chart.rowHead}>
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
