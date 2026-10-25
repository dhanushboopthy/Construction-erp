import styles from "./Admin.module.css";
import type { Tone } from "./labels";

/** A status in colour and in words (DESIGN.md: status is never colour alone). */
export function Badge({ tone, children }: { tone: Tone; children: string }) {
  return (
    <span className={styles.badge} data-tone={tone}>
      {children}
    </span>
  );
}

/** "3 of 5" with a thin bar; turns amber when the limit is reached. */
export function Usage({ used, limit, label }: { used: number; limit: number; label: string }) {
  const share = limit > 0 ? Math.min(100, Math.round((used / limit) * 100)) : 100;
  return (
    <span className={styles.usage} data-full={used >= limit}>
      <span className={styles.usageText}>
        {used} of {limit}
        <span className="visually-hidden"> {label}</span>
      </span>
      <span className={styles.usageTrack} aria-hidden="true">
        <span className={styles.usageFill} style={{ width: `${share}%` }} />
      </span>
    </span>
  );
}
