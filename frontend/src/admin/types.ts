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
export type TenantPlan = Schemas["TenantPlan"];
export type TrialState = Schemas["TrialState"];
export type PlatformUser = Schemas["PlatformUserRow"];
export type SignInEvent = Schemas["SignInEvent"];
export type AdminAction = Schemas["PlatformAuditRow"];
export type AdminActionKind = Schemas["PlatformAction"];
export type Page<T> = { items: T[]; total: number; limit: number; offset: number };
