import type { ReactNode } from "react";

import { Badge } from "./Badge";
import { durationLabel, limitsNote, rupees } from "./labels";
import styles from "./Plans.module.css";
import type { DurationUnit } from "./types";

/** What a card shows. The editor feeds it the form as typed, so the preview is live. */
export interface PlanCardData {
  code: string;
  name: string;
  short_description: string;
  max_users: number;
  max_locations: number;
  features: string[];
  is_popular: boolean;
  is_active: boolean;
  prices: { duration_value: number; duration_unit: DurationUnit; price: string }[];
  companies?: number;
}

/** A plan as Duolink sells it: price rows, limits and the features it lists. */
export function PlanCard({
  plan,
  featureNames,
  actions,
}: {
  plan: PlanCardData;
  featureNames: Record<string, string>;
  actions?: ReactNode;
}) {
  return (
    <article
      className={styles.card}
      data-popular={plan.is_popular}
      data-archived={!plan.is_active}
      aria-label={`${plan.name || "New plan"} plan`}
    >
      <div className={styles.cardHead}>
        <h2 className={styles.cardName}>{plan.name || "New plan"}</h2>
        <span>
          {plan.is_popular ? <Badge tone="accent">Popular</Badge> : null}
          {plan.is_active ? null : <Badge tone="neutral">Archived</Badge>}
        </span>
      </div>
      <span className={styles.code}>{plan.code || "CODE"}</span>
      {plan.short_description ? <p className={styles.tagline}>{plan.short_description}</p> : null}
      <ul className={styles.prices} aria-label="Prices">
        {plan.prices.map((p, i) => (
          <li key={`${p.duration_value}-${p.duration_unit}-${i}`}>
            <span>{durationLabel(p.duration_value, p.duration_unit)}</span>
            <span className={styles.amount}>{rupees(p.price)}</span>
          </li>
        ))}
      </ul>
      <p className={styles.limits}>{limitsNote(plan)}</p>
      {plan.features.length ? (
        <ul className={styles.features} aria-label="Features">
          {plan.features.map((code) => (
            <li key={code}>{featureNames[code] ?? code}</li>
          ))}
        </ul>
      ) : null}
      {plan.companies === undefined ? null : (
        <p className={styles.inUse}>
          {plan.companies === 0
            ? "No company is on this plan"
            : `${plan.companies} ${plan.companies === 1 ? "company is" : "companies are"} on this plan`}
        </p>
      )}
      {actions ? <div className={styles.cardActions}>{actions}</div> : null}
    </article>
  );
}
