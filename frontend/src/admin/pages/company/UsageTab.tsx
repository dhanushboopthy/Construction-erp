import styles from "@/components/Ledger.module.css";

import { useTenantUsage } from "../../api";
import adminStyles from "../../Admin.module.css";
import type { TenantDetail } from "../../types";

/** Whole numbers only (ADR 0012). Storage is shown in KB or MB, never as an amount. */
function size(bytes: number): string {
  if (bytes < 1024) return `${bytes} bytes`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function UsageTab({ tenant }: { tenant: TenantDetail }) {
  const usage = useTenantUsage(tenant.id);
  if (usage.isPending) return <p role="status">Loading usage…</p>;
  if (usage.isError) return <p className={styles.formError}>Usage could not be loaded.</p>;
  const u = usage.data;
  return (
    <div className={styles.panel}>
      <h2 className={styles.panelHead}>Usage</h2>
      <dl className={adminStyles.facts}>
        <dt>Active users</dt>
        <dd>{u.users}</dd>
        <dt>Shops and godowns</dt>
        <dd>{u.shops}</dd>
        <dt>Bills, last 7 days</dt>
        <dd>{u.bills_7d}</dd>
        <dt>Bills, last 30 days</dt>
        <dd>{u.bills_30d}</dd>
        <dt>Bills, last 90 days</dt>
        <dd>{u.bills_90d}</dd>
        <dt>Supplier bills, last 30 days</dt>
        <dd>{u.purchases_30d}</dd>
        <dt>Attached files</dt>
        <dd>
          {u.attachments} ({size(u.attachment_bytes)})
        </dd>
      </dl>
      <p className={styles.note}>Counts only. Duolink never sees what a company sells or earns.</p>
    </div>
  );
}
