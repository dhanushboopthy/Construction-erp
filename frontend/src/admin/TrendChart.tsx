import { useId, useState } from "react";

import styles from "./Chart.module.css";

export interface TrendBar {
  /** Axis label, e.g. "Nov 2026". */
  label: string;
  /** Used only for the bar's height, never shown. */
  height: number;
  /** What is written for this bar, e.g. "₹1,23,456.00" or "4". */
  text: string;
}

const W = 600;
const H = 150;
const PAD_TOP = 8;
const GAP = 8;

/**
 * Twelve months as bars on one axis. Each bar can be reached by keyboard or pointer and reads
 * out its month and value below the plot; the same figures are in a table for a screen reader
 * and for anyone who prefers numbers. Colour is one series token; nothing relies on it alone.
 */
export function TrendChart({
  title,
  series,
  bars,
  tone,
}: {
  title: string;
  /** The column heading in the table: "Revenue" or "Sign-ups". */
  series: string;
  bars: TrendBar[];
  tone: 1 | 2;
}) {
  const id = useId();
  const [active, setActive] = useState<number | null>(null);
  const peak = Math.max(...bars.map((b) => b.height), 0);
  const slot = bars.length ? (W - GAP * (bars.length - 1)) / bars.length : W;
  const shown = active === null ? null : bars[active];

  return (
    <figure className={styles.figure} aria-labelledby={`${id}-title`}>
      <figcaption id={`${id}-title`} className={styles.caption}>
        {title}
      </figcaption>
      <svg
        className={styles.plot}
        viewBox={`0 0 ${W} ${H + 18}`}
        role="group"
        aria-label={`${title}, ${bars.length} months`}
      >
        <line className={styles.axis} x1={0} y1={H} x2={W} y2={H} />
        {bars.map((b, i) => {
          const h =
            peak > 0 ? Math.max(b.height > 0 ? 3 : 0, (b.height / peak) * (H - PAD_TOP)) : 0;
          const x = i * (slot + GAP);
          return (
            <g
              key={b.label}
              className={styles.bar}
              data-tone={tone}
              data-active={active === i}
              tabIndex={0}
              role="img"
              aria-label={`${b.label}: ${b.text}`}
              onMouseEnter={() => setActive(i)}
              onMouseLeave={() => setActive(null)}
              onFocus={() => setActive(i)}
              onBlur={() => setActive(null)}
            >
              <rect className={styles.hit} x={x - GAP / 2} y={0} width={slot + GAP} height={H} />
              <rect className={styles.mark} x={x} y={H - h} width={slot} height={h} rx={3} />
              {i === 0 || i === bars.length - 1 || i % 3 === 0 ? (
                <text className={styles.tick} x={x + slot / 2} y={H + 14} textAnchor="middle">
                  {b.label.split(" ")[0]}
                </text>
              ) : null}
            </g>
          );
        })}
      </svg>
      <p className={styles.readout} aria-live="polite">
        {shown ? (
          <>
            {shown.label}: <strong>{shown.text}</strong>
          </>
        ) : (
          "Point at or tab to a bar for its figure."
        )}
      </p>
      <details className={styles.details}>
        <summary>Show as a table</summary>
        <table className={styles.table}>
          <caption className="visually-hidden">{title}</caption>
          <thead>
            <tr>
              <th scope="col">Month</th>
              <th scope="col" className="num">
                {series}
              </th>
            </tr>
          </thead>
          <tbody>
            {bars.map((b) => (
              <tr key={b.label}>
                <th scope="row">{b.label}</th>
                <td className="num">{b.text}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </figure>
  );
}
