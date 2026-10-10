import { Info } from "lucide-react";
import { useId, type ReactNode } from "react";

import { useKpiDefinitions } from "@/api/finance";

import styles from "./Metric.module.css";

/** One figure from the KPI catalogue (backend domain/kpi_catalogue.py): its name, the value,
 * a one-line "what this means", and the formula with a worked example on hover or focus. */
export function Metric({
  code,
  label,
  value,
  tone,
  note,
}: {
  code: string;
  label: string;
  value: ReactNode;
  tone?: "good" | "critical";
  note?: ReactNode;
}) {
  const tipId = useId();
  const def = useKpiDefinitions().data?.find((d) => d.code === code);
  return (
    <div className={styles.metric} data-tone={tone}>
      <dt className={styles.label}>
        {def?.name ?? label}
        {def ? (
          <span className={styles.tipRoot}>
            <button
              type="button"
              className={styles.tipButton}
              aria-label={`How ${def.name} is worked out`}
              aria-describedby={tipId}
            >
              <Info size={14} strokeWidth={2.2} aria-hidden="true" />
            </button>
            <span role="tooltip" id={tipId} className={styles.tip}>
              <strong>{def.formula}</strong>
              <span>e.g. {def.example}</span>
            </span>
          </span>
        ) : null}
      </dt>
      <dd className={styles.value}>{value}</dd>
      {note || def ? <dd className={styles.meaning}>{note ?? def?.meaning}</dd> : null}
    </div>
  );
}
