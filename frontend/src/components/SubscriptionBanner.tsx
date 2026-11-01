import type { Tenant } from "@/api/types";
import { formatDay } from "@/lib/format";

import styles from "./SubscriptionBanner.module.css";

/** Days before the end when the company is first told. */
export const WARN_DAYS = 7;

/**
 * A line above the screens: the plan is about to end, or it has and the company is read-only.
 * Shows nothing for a company with plenty of time left.
 */
export function SubscriptionBanner({ tenant }: { tenant: Tenant | undefined }) {
  if (!tenant) return null;
  if (tenant.access_state === "read_only") {
    return (
      <p className={styles.banner} data-tone="critical" role="status">
        Your Duolink plan ended
        {tenant.expires_at ? ` on ${formatDay(tenant.expires_at)}` : ""}. You can look at everything
        but cannot save changes. Contact Duolink to renew.
      </p>
    );
  }
  const left = tenant.days_left;
  if (tenant.expires_at && left !== null && left !== undefined && left >= 0 && left <= WARN_DAYS) {
    return (
      <p className={styles.banner} data-tone="warn" role="status">
        Your Duolink plan ends on {formatDay(tenant.expires_at)}. Contact Duolink to renew.
      </p>
    );
  }
  return null;
}
