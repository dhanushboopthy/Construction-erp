// Short names for the Duolink admin API's generated shapes (src/api/schema.d.ts, `make gen-api`).

import type { components } from "@/api/schema";

type Schemas = components["schemas"];

export type Admin = Schemas["AdminOut"];
export type AdminTokenResponse = Schemas["AdminTokenResponse"];
export type Overview = Schemas["OverviewOut"];
export type TenantRow = Schemas["TenantRow"];
export type TenantDetail = Schemas["TenantDetail"];
export type TenantCreate = Schemas["TenantCreate"];
export type TenantUpdate = Schemas["TenantUpdate"];
export type TenantStatus = Schemas["TenantStatus"];
export type Plan = Schemas["PlanOut"];
export type PlanPrice = Schemas["PlanPriceOut"];
export type PlanCreate = Schemas["PlanCreate"];
export type PlanUpdate = Schemas["PlanUpdate"];
export type PlanFeature = Schemas["PlanFeatureOut"];
export type DurationUnit = Schemas["DurationUnit"];
export type TrialState = Schemas["TrialState"];
export type PlatformUser = Schemas["PlatformUserRow"];
export type PlatformUserUpdate = Schemas["PlatformUserUpdate"];
export type UserSession = Schemas["UserSessionRow"];
export type SignInEvent = Schemas["SignInEvent"];
export type AdminAction = Schemas["PlatformAuditRow"];
export type AdminActionKind = Schemas["PlatformAction"];
export type Page<T> = { items: T[]; total: number; limit: number; offset: number };
export type PlatformRole = Schemas["PlatformRole"];
export type StaffMember = Schemas["StaffRow"];
export type StaffCreate = Schemas["StaffCreate"];
export type StaffUpdate = Schemas["StaffUpdate"];
export type TenantCreated = Schemas["TenantCreated"];
export type SellerDetails = Schemas["SellerDetails"];
export type SellerDetailsUpdate = Schemas["SellerDetailsUpdate"];
export type TenantUsage = Schemas["TenantUsage"];

// Milestone 22 (support tickets): written by hand in src/support/types.ts, shared with the company app.
export type {
  AdminTicketDetail,
  AdminTicketFilters,
  AdminTicketPage,
  AdminTicketPatch,
  AdminTicketReply,
  AdminTicketRow,
  TicketCounts,
} from "@/support/types";

// Milestone 21 (subscriptions and payments). Written by hand until `make gen-api` runs; money
// is always the server's decimal text, never a number.
export type SubscriptionStatus = "trial" | "active" | "expired" | "cancelled";
export type PaymentMethod = "cash" | "bank" | "upi" | "cheque" | "razorpay";

export interface SubscriptionRow {
  id: number;
  tenant_id: number;
  tenant_slug: string;
  tenant_name: string;
  plan_id: number;
  plan_code: string;
  plan_name: string;
  status: SubscriptionStatus;
  starts_at: string;
  expires_at: string | null;
  days_left: number | null;
  needs_review: boolean;
  duration_value: number | null;
  duration_unit: DurationUnit | null;
  price: string | null;
  cancelled_at: string | null;
  cancel_reason: string | null;
}

export interface SubscriptionFilters {
  status?: string;
  plan?: string;
  expiring_within?: number | string;
  tenant_id?: number;
  search?: string;
  limit?: number;
  offset?: number;
}

export interface RenewBody {
  plan_id: number;
  price_id: number | null;
  custom_days: number | null;
  amount: string;
  method: PaymentMethod;
  reference?: string;
  notes?: string;
  paid_at?: string;
}

export interface Payment {
  id: number;
  subscription_id: number;
  tenant_id: number;
  tenant_name: string;
  plan_code: string;
  plan_name: string;
  /** Negative on a reversal. */
  amount: string;
  method: PaymentMethod;
  reference: string | null;
  notes: string | null;
  paid_at: string;
  period_starts_at: string | null;
  period_ends_at: string | null;
  reverses_id: number | null;
  reversed: boolean;
  recorded_by: string;
}

export interface PaymentFilters {
  from?: string;
  to?: string;
  method?: string;
  tenant_id?: number;
  limit?: number;
  offset?: number;
}

export interface PaymentTotals {
  received: string;
  reversed: string;
  net: string;
}

export interface PaymentPage {
  items: Payment[];
  total: number;
  totals: PaymentTotals;
}

export interface SubscriptionPage {
  items: SubscriptionRow[];
  total: number;
}

export interface TrendPoint {
  /** "2026-11" */
  month: string;
  revenue: string;
  signups: number;
}

export interface BillingDashboard {
  companies_by_status: Record<TenantStatus, number>;
  active_subscriptions: number;
  revenue_month: string;
  revenue_fy: string;
  new_companies_month: number;
  renewals_month: number;
  expiring_30: number;
  trend: TrendPoint[];
  plan_breakdown: { plan_id: number; plan_code: string; plan_name: string; companies: number }[];
  expiring_soon: {
    tenant_id: number;
    tenant_name: string;
    plan_code: string;
    expires_at: string;
    days_left: number;
  }[];
}
