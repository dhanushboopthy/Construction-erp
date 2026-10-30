import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import { Link } from "react-router";

import { ProgressBar } from "./ProgressBar";
import type { PillTone } from "./StatusPill";
import styles from "./KpiCard.module.css";

export interface KpiProgress {
  /** How far along, in the same unit as `max`. */
  value: number;
  max?: number;
  /** Accessible name of the bar, e.g. "Share of dues overdue". */
  label: string;
}

/**
 * One headline figure: label, big tabular value, an icon whose colour carries the tone, an
 * optional progress bar with its percentage written out, and an optional link. With `href` the
 * whole card is one link, so it is one tab stop and one click target.
 */
export function KpiCard({
  label,
  value,
  icon: Icon,
  tone = "neutral",
  note,
  progress,
  href,
}: {
  label: string;
  value: ReactNode;
  icon?: LucideIcon;
  tone?: PillTone;
  note?: ReactNode;
  progress?: KpiProgress;
  href?: string;
}) {
  const body = (
    <>
      <div className={styles.top}>
        <span className={styles.label}>{label}</span>
        {Icon ? (
          <span className={styles.icon} data-tone={tone}>
            <Icon size={20} strokeWidth={2} aria-hidden="true" />
          </span>
        ) : null}
      </div>
      <strong className={styles.value}>{value}</strong>
      {note ? <span className={styles.note}>{note}</span> : null}
      {progress ? (
        <div className={styles.progress}>
          <ProgressBar
            value={progress.value}
            max={progress.max}
            label={progress.label}
            tone={tone}
          />
        </div>
      ) : null}
    </>
  );
  return href ? (
    <Link to={href} className={`${styles.card} ${styles.link}`}>
      {body}
    </Link>
  ) : (
    <article className={styles.card}>{body}</article>
  );
}
