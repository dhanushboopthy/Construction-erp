import styles from "@/components/Ledger.module.css";

import { useIntegrations, useIntegrationUsage } from "../api";
import { useAdminAuth } from "../AdminAuthContext";
import { IntegrationCard } from "../IntegrationCard";
import { INTEGRATION_ORDER } from "../labels";

/** Duolink's shared GSP account and GSTIN lookup (Milestone 27). Credentials are write-only:
 * only the last four characters of a saved key are ever shown. Support reads the status; a Super
 * Admin connects, tests, limits and watches usage. */
export function IntegrationsPage() {
  const { isSuperAdmin } = useAdminAuth();
  const integrations = useIntegrations();
  const usage = useIntegrationUsage(isSuperAdmin);

  return (
    <section aria-labelledby="integrations-title" className={styles.page}>
      <div className={styles.toolbar}>
        <h1 id="integrations-title" className={styles.title}>
          Integrations
        </h1>
      </div>
      {integrations.isPending ? (
        <p role="status">Loading integrations…</p>
      ) : integrations.isError ? (
        <p role="alert" className={styles.formError}>
          Integrations could not be loaded. Reload the page.
        </p>
      ) : (
        INTEGRATION_ORDER.map((kind) => {
          const integration = integrations.data.find((i) => i.kind === kind);
          return integration ? (
            <IntegrationCard
              key={kind}
              integration={integration}
              usage={usage.data?.find((u) => u.kind === kind)}
              canEdit={isSuperAdmin}
            />
          ) : null;
        })
      )}
    </section>
  );
}
