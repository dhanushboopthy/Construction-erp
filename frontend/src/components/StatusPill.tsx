import { CheckCircle2, CircleAlert, CircleSlash, Info, Minus, type LucideIcon } from "lucide-react";

import styles from "./StatusPill.module.css";

export type PillTone = "good" | "warn" | "critical" | "neutral" | "accent";

const ICONS: Record<PillTone, LucideIcon> = {
  good: CheckCircle2,
  warn: CircleAlert,
  critical: CircleSlash,
  neutral: Minus,
  accent: Info,
};

/**
 * A status as a word with an icon, never colour alone. `label` is required, so a pill without
 * text does not type-check. Solid in light mode, tinted in dark (the `--pill-*` tokens).
 */
export function StatusPill({
  tone,
  label,
  icon,
}: {
  tone: PillTone;
  label: string;
  /** Replaces the tone's default icon. */
  icon?: LucideIcon;
}) {
  const Icon = icon ?? ICONS[tone];
  return (
    <span className={styles.pill} data-tone={tone}>
      <Icon size={14} strokeWidth={2.4} aria-hidden="true" />
      {label}
    </span>
  );
}
