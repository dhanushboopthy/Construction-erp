import type { ReactNode } from "react";

import { ActivityTab } from "./pages/company/ActivityTab";
import { OverviewTab } from "./pages/company/OverviewTab";
import { SubscriptionTab } from "./pages/company/SubscriptionTab";
import { UsageTab } from "./pages/company/UsageTab";
import type { TenantDetail } from "./types";
import { UsersView } from "./UsersView";

export interface CompanyTab {
  /** In the address: /admin/companies/7?tab=usage */
  key: string;
  label: string;
  /** Hidden from Support. The server refuses Support as well; this is a courtesy. */
  superAdminOnly?: boolean;
  render: (tenant: TenantDetail) => ReactNode;
}

/**
 * Every tab of the company page, in one list. A later milestone adds its tab here and nothing
 * else changes: Numbering and Data (M26), Backups (M25), Bill design (M28), Support (M22) and
 * Access (M23).
 */
export const COMPANY_TABS: CompanyTab[] = [
  { key: "overview", label: "Overview", render: (t) => <OverviewTab tenant={t} /> },
  { key: "users", label: "Users", render: (t) => <UsersView tenantId={t.id} /> },
  { key: "subscription", label: "Subscription", render: (t) => <SubscriptionTab tenant={t} /> },
  { key: "usage", label: "Usage", render: (t) => <UsageTab tenant={t} /> },
  { key: "activity", label: "Activity", render: (t) => <ActivityTab tenant={t} /> },
];
