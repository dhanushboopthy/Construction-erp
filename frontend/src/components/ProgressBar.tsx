import type { PillTone } from "./StatusPill";
import styles from "./ProgressBar.module.css";

/**
 * A bar with its percentage written beside it. `role="progressbar"` with `aria-valuenow`,
 * `min` and `max`, and a name saying what it measures. Values are clamped to 0..max.
 */
export function ProgressBar({
  value,
  max = 100,
  label,
  tone = "accent",
}: {
  value: number;
  max?: number;
  /** What the bar measures, e.g. "Share of dues overdue". */
  label: string;
  tone?: PillTone;
}) {
  const now = Math.min(Math.max(value, 0), max);
  const percent = Math.round((now / (max || 1)) * 100);
  return (
    <div className={styles.row}>
      <div
        className={styles.track}
        role="progressbar"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={max}
        aria-valuenow={now}
        aria-valuetext={`${percent}%`}
      >
        <span className={styles.fill} data-tone={tone} style={{ width: `${percent}%` }} />
      </div>
      <span className={`${styles.percent} num`}>{percent}%</span>
    </div>
  );
}
