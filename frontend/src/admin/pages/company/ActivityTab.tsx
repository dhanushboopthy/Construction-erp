import styles from "@/components/Ledger.module.css";

import type { TenantDetail } from "../../types";
import { AdminActions, SignIns } from "../ActivityPage";

/** Sign-ins at this company, and what Duolink admins did to it. */
export function ActivityTab({ tenant }: { tenant: TenantDetail }) {
  return (
    <>
      <h2 className={styles.title}>Sign-ins</h2>
      <SignIns tenantId={tenant.id} />
      <h2 className={styles.title}>What Duolink admins did here</h2>
      <AdminActions tenantId={tenant.id} />
    </>
  );
}
