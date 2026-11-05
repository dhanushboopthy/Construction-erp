import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { json } from "@/api/client";

import { adminApi, adminClient } from "./client";
import type {
  AdminAction,
  AuditFilters,
  Maintenance,
  Notifications,
  PlatformSettings,
  SystemHealth,
  AdminTicketDetail,
  AdminTicketFilters,
  AdminTicketPage,
  AdminTicketPatch,
  AdminTicketReply,
  BillingDashboard,
  Overview,
  Page,
  Payment,
  PaymentFilters,
  PaymentPage,
  Plan,
  RenewBody,
  SubscriptionFilters,
  SubscriptionPage,
  SubscriptionRow,
  PlanCreate,
  PlanFeature,
  PlanUpdate,
  PlatformUser,
  PlatformUserUpdate,
  SignInEvent,
  StaffCreate,
  StaffMember,
  StaffUpdate,
  SellerDetails,
  SellerDetailsUpdate,
  TenantCreate,
  TenantCreated,
  TenantDetail,
  TenantRow,
  TenantUpdate,
  TenantUsage,
  UserSession,
} from "./types";

/** Query string from the filters that are set. */
function query(params: Record<string, string | number | null | undefined>): string {
  const set = Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== "");
  return set.length ? `?${new URLSearchParams(set.map(([k, v]) => [k, String(v)]))}` : "";
}

const keys = {
  overview: ["admin", "overview"] as const,
  tenants: ["admin", "tenants"] as const,
  tenant: (id: number) => ["admin", "tenants", id] as const,
  users: ["admin", "users"] as const,
  activity: ["admin", "activity"] as const,
  audit: ["admin", "audit"] as const,
  staff: ["admin", "staff"] as const,
  plans: ["admin", "plans"] as const,
  subscriptions: ["admin", "subscriptions"] as const,
  payments: ["admin", "payments"] as const,
  billingDashboard: ["admin", "billing-dashboard"] as const,
  support: ["admin", "support"] as const,
};

export function useOverview() {
  return useQuery({ queryKey: keys.overview, queryFn: () => adminApi<Overview>("/overview") });
}

export interface TenantFilters {
  q?: string;
  status?: string;
  plan?: string;
  trial?: string;
  expiring?: boolean;
  sort?: string;
  order?: string;
  limit?: number;
  offset?: number;
}

export const COMPANY_PAGE_SIZE = 25;

export function useTenants(filters: TenantFilters = {}) {
  const { expiring, ...rest } = filters;
  return useQuery({
    queryKey: [...keys.tenants, filters],
    queryFn: () =>
      adminApi<Page<TenantRow>>(
        `/tenants${query({ limit: COMPANY_PAGE_SIZE, ...rest, expiring: expiring ? "true" : "" })}`,
      ),
    placeholderData: keepPreviousData,
  });
}

export function useTenant(id: number) {
  return useQuery({
    queryKey: keys.tenant(id),
    queryFn: () => adminApi<TenantDetail>(`/tenants/${id}`),
  });
}

/** After a change to a company, every admin view may be stale. */
function useRefreshAll() {
  const client = useQueryClient();
  return (detail?: TenantDetail) => {
    if (detail) client.setQueryData(keys.tenant(detail.id), detail);
    void client.invalidateQueries({ queryKey: ["admin"] });
  };
}

export function useCreateTenant() {
  const refresh = useRefreshAll();
  return useMutation({
    mutationFn: (body: TenantCreate) =>
      adminApi<TenantCreated>("/tenants", { method: "POST", body: json(body) }),
    onSuccess: refresh,
  });
}

export function useUpdateTenant(id: number) {
  const refresh = useRefreshAll();
  return useMutation({
    mutationFn: (body: TenantUpdate) =>
      adminApi<TenantDetail>(`/tenants/${id}`, { method: "PATCH", body: json(body) }),
    onSuccess: refresh,
  });
}

export function useSuspendTenant(id: number) {
  const refresh = useRefreshAll();
  return useMutation({
    mutationFn: (reason: string) =>
      adminApi<TenantDetail>(`/tenants/${id}/suspend`, {
        method: "POST",
        body: json({ reason }),
      }),
    onSuccess: refresh,
  });
}

export function useReactivateTenant(id: number) {
  const refresh = useRefreshAll();
  return useMutation({
    mutationFn: (reason?: string) =>
      adminApi<TenantDetail>(`/tenants/${id}/reactivate`, {
        method: "POST",
        body: json(reason ? { reason } : {}),
      }),
    onSuccess: refresh,
  });
}

export function useCancelTenant(id: number) {
  const refresh = useRefreshAll();
  return useMutation({
    mutationFn: (reason: string) =>
      adminApi<TenantDetail>(`/tenants/${id}/cancel`, { method: "POST", body: json({ reason }) }),
    onSuccess: refresh,
  });
}

export function useTenantUsage(id: number) {
  return useQuery({
    queryKey: [...keys.tenant(id), "usage"],
    queryFn: () => adminApi<TenantUsage>(`/tenants/${id}/usage`),
  });
}

export function useSellerDetails(id: number) {
  return useQuery({
    queryKey: [...keys.tenant(id), "seller"],
    queryFn: () => adminApi<SellerDetails>(`/tenants/${id}/seller-details`),
  });
}

export function useUpdateSellerDetails(id: number) {
  const refresh = useRefreshAll();
  return useMutation({
    mutationFn: (body: Partial<SellerDetailsUpdate> & { reason: string }) =>
      adminApi<SellerDetails>(`/tenants/${id}/seller-details`, {
        method: "PATCH",
        body: json(body),
      }),
    onSuccess: () => refresh(),
  });
}

export function useSetCompanyLogo(id: number) {
  const refresh = useRefreshAll();
  return useMutation({
    mutationFn: (file: File) => {
      const form = new FormData();
      form.append("file", file);
      return adminApi<TenantDetail>(`/tenants/${id}/logo`, { method: "POST", body: form });
    },
    onSuccess: refresh,
  });
}

export function useRemoveCompanyLogo(id: number) {
  const refresh = useRefreshAll();
  return useMutation({
    mutationFn: () => adminApi<TenantDetail>(`/tenants/${id}/logo`, { method: "DELETE" }),
    onSuccess: refresh,
  });
}

export interface UserFilters {
  tenant_id?: number;
  q?: string;
  role?: string;
  /** "true" or "false", as the API takes them. */
  active?: string;
  locked?: string;
  never_signed_in?: string;
  include_removed?: string;
  offset?: number;
}

export const USER_PAGE_SIZE = 50;

export function useAdminUsers(filters: UserFilters = {}) {
  return useQuery({
    queryKey: [...keys.users, filters],
    queryFn: () =>
      adminApi<Page<PlatformUser>>(`/users${query({ ...filters, limit: USER_PAGE_SIZE })}`),
    placeholderData: keepPreviousData,
  });
}

export function useUpdateUser(id: number) {
  const refresh = useRefreshAll();
  return useMutation({
    mutationFn: (body: PlatformUserUpdate) =>
      adminApi<PlatformUser>(`/users/${id}`, { method: "PATCH", body: json(body) }),
    onSuccess: () => refresh(),
  });
}

/** Fetched each time the panel (or the remove dialog) opens, never served from earlier. */
export function useUserSessions(id: number) {
  return useQuery({
    queryKey: [...keys.users, id, "sessions"],
    queryFn: () => adminApi<UserSession[]>(`/users/${id}/sessions`),
    staleTime: 0,
    gcTime: 0,
  });
}

export function useRevokeSession(userId: number) {
  const refresh = useRefreshAll();
  return useMutation({
    mutationFn: (sessionId: string) =>
      adminApi<undefined>(`/users/${userId}/sessions/${sessionId}`, { method: "DELETE" }),
    onSuccess: () => refresh(),
  });
}

export function useRemoveUser(id: number) {
  const refresh = useRefreshAll();
  return useMutation({
    mutationFn: (body: { confirm_username: string; reason: string }) =>
      adminApi<PlatformUser>(`/users/${id}/remove`, { method: "POST", body: json(body) }),
    onSuccess: () => refresh(),
  });
}

// ------------------------------------------------------------------ plans (Milestone 20)

/** Every plan, archived ones too unless `includeArchived` is false (the onboarding picker). */
export function usePlans(includeArchived = true) {
  return useQuery({
    queryKey: [...keys.plans, includeArchived],
    queryFn: () =>
      adminApi<Plan[]>(
        `/billing/plans${query({ include_archived: includeArchived ? "" : "false" })}`,
      ),
  });
}

/** One plan, fetched afresh each time it is asked for (dialogs show the live count). */
export function usePlan(id: number) {
  return useQuery({
    queryKey: [...keys.plans, "one", id],
    queryFn: () => adminApi<Plan>(`/billing/plans/${id}`),
    staleTime: 0,
    gcTime: 0,
  });
}

export function usePlanFeatures() {
  return useQuery({
    queryKey: [...keys.plans, "features"],
    queryFn: () => adminApi<PlanFeature[]>("/billing/plans/features"),
    staleTime: Infinity,
  });
}

export function useCreatePlan() {
  const refresh = useRefreshAll();
  return useMutation({
    mutationFn: (body: PlanCreate) =>
      adminApi<Plan>("/billing/plans", { method: "POST", body: json(body) }),
    onSuccess: () => refresh(),
  });
}

export function useUpdatePlan(id: number) {
  const refresh = useRefreshAll();
  return useMutation({
    mutationFn: (body: PlanUpdate) =>
      adminApi<Plan>(`/billing/plans/${id}`, { method: "PATCH", body: json(body) }),
    onSuccess: () => refresh(),
  });
}

export function useDuplicatePlan() {
  const refresh = useRefreshAll();
  return useMutation({
    mutationFn: (id: number) =>
      adminApi<Plan>(`/billing/plans/${id}/duplicate`, { method: "POST" }),
    onSuccess: () => refresh(),
  });
}

export function useArchivePlan(id: number) {
  const refresh = useRefreshAll();
  return useMutation({
    mutationFn: (reason: string) =>
      adminApi<Plan>(`/billing/plans/${id}/archive`, {
        method: "POST",
        body: json({ reason }),
      }),
    onSuccess: () => refresh(),
  });
}

export function useDeletePlan(id: number) {
  const refresh = useRefreshAll();
  return useMutation({
    mutationFn: (body: { confirmation: string; reason: string }) =>
      adminApi<undefined>(`/billing/plans/${id}/delete`, { method: "POST", body: json(body) }),
    onSuccess: () => refresh(),
  });
}

export const SUBSCRIPTION_PAGE_SIZE = 25;
export const PAYMENT_PAGE_SIZE = 25;

export function useSubscriptions(filters: SubscriptionFilters = {}) {
  return useQuery({
    queryKey: [...keys.subscriptions, filters],
    queryFn: () =>
      adminApi<SubscriptionPage>(
        `/billing/subscriptions${query({ limit: SUBSCRIPTION_PAGE_SIZE, ...filters })}`,
      ),
    placeholderData: keepPreviousData,
  });
}

export function usePayments(filters: PaymentFilters = {}) {
  return useQuery({
    queryKey: [...keys.payments, filters],
    queryFn: () =>
      adminApi<PaymentPage>(`/billing/payments${query({ limit: PAYMENT_PAGE_SIZE, ...filters })}`),
    placeholderData: keepPreviousData,
  });
}

/** Revenue and sign-up figures. Only this call feeds money onto the Overview. */
export function useBillingDashboard() {
  return useQuery({
    queryKey: keys.billingDashboard,
    queryFn: () => adminApi<BillingDashboard>("/billing/dashboard"),
  });
}

export function useRenewSubscription(id: number) {
  const refresh = useRefreshAll();
  return useMutation({
    mutationFn: (body: RenewBody) =>
      adminApi<SubscriptionRow>(`/billing/subscriptions/${id}/renew`, {
        method: "POST",
        body: json(body),
      }),
    onSuccess: () => refresh(),
  });
}

export function useCancelSubscription(id: number) {
  const refresh = useRefreshAll();
  return useMutation({
    mutationFn: (reason: string) =>
      adminApi<SubscriptionRow>(`/billing/subscriptions/${id}/cancel`, {
        method: "POST",
        body: json({ reason }),
      }),
    onSuccess: () => refresh(),
  });
}

export function useReversePayment(id: number) {
  const refresh = useRefreshAll();
  return useMutation({
    mutationFn: (reason: string) =>
      adminApi<Payment>(`/billing/payments/${id}/reverse`, {
        method: "POST",
        body: json({ reason }),
      }),
    onSuccess: () => refresh(),
  });
}

export type UserAction = "deactivate" | "activate" | "unlock" | "sign-out";

export function useUserAction() {
  const refresh = useRefreshAll();
  return useMutation({
    mutationFn: ({ id, action }: { id: number; action: UserAction }) =>
      adminApi<PlatformUser>(`/users/${id}/${action}`, { method: "POST" }),
    onSuccess: () => refresh(),
  });
}

export function useResetUserPassword() {
  const refresh = useRefreshAll();
  return useMutation({
    mutationFn: (id: number) =>
      adminApi<{ temporary_password: string }>(`/users/${id}/reset-password`, {
        method: "POST",
      }),
    onSuccess: () => refresh(),
  });
}

export function useSignIns(
  filters: { tenant_id?: number; action?: string; date_from?: string; date_to?: string } = {},
) {
  return useQuery({
    queryKey: [...keys.activity, filters],
    queryFn: () => adminApi<Page<SignInEvent>>(`/activity${query({ ...filters, limit: 100 })}`),
    placeholderData: keepPreviousData,
  });
}

export function useAdminActions(filters: AuditFilters = {}) {
  return useQuery({
    queryKey: [...keys.audit, filters],
    queryFn: () => adminApi<Page<AdminAction>>(`/audit${query({ ...filters, limit: 100 })}`),
    placeholderData: keepPreviousData,
  });
}

/** The audit CSV for the same filters as the screen (Super Admin). Saved through the browser. */
export async function downloadAuditCsv(filters: AuditFilters): Promise<void> {
  const blob = await adminClient.fetchFile(`/audit/export${query({ ...filters })}`);
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "duolink-audit.csv";
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
}

// ------------------------------------------------------------------ Milestone 24

const NOTIFICATION_REFRESH_MS = 60_000;

/** The bell: worked out by the server on every read, asked again each minute. */
export function useNotifications() {
  return useQuery({
    queryKey: ["admin", "notifications"],
    queryFn: () => adminApi<Notifications>("/notifications"),
    refetchInterval: NOTIFICATION_REFRESH_MS,
    retry: false,
  });
}

export function useSystemHealth() {
  return useQuery({
    queryKey: ["admin", "system-health"],
    queryFn: () => adminApi<SystemHealth>("/system/health"),
    refetchInterval: NOTIFICATION_REFRESH_MS,
  });
}

export function useMaintenance() {
  return useQuery({
    queryKey: ["admin", "maintenance"],
    queryFn: () => adminApi<Maintenance>("/system/maintenance"),
  });
}

export function useSetMaintenance() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: { enabled: boolean; message: string | null }) =>
      adminApi<Maintenance>("/system/maintenance", { method: "POST", body: json(body) }),
    onSuccess: (data) => {
      client.setQueryData(["admin", "maintenance"], data);
      void client.invalidateQueries({ queryKey: ["admin", "system-health"] });
      void client.invalidateQueries({ queryKey: keys.audit });
    },
  });
}

export function usePlatformSettings() {
  return useQuery({
    queryKey: ["admin", "platform-settings"],
    queryFn: () => adminApi<PlatformSettings>("/system/settings"),
    staleTime: 5 * 60_000,
  });
}

export function useStaff(enabled = true) {
  return useQuery({
    queryKey: keys.staff,
    queryFn: () => adminApi<StaffMember[]>("/staff"),
    enabled,
  });
}

export const TICKET_PAGE_SIZE = 25;

export function useAdminTickets(filters: AdminTicketFilters = {}) {
  return useQuery({
    queryKey: [...keys.support, "list", filters],
    queryFn: () =>
      adminApi<AdminTicketPage>(
        `/support/tickets${query({ limit: TICKET_PAGE_SIZE, ...filters })}`,
      ),
    placeholderData: keepPreviousData,
  });
}

export function useAdminTicket(id: number) {
  return useQuery({
    queryKey: [...keys.support, "ticket", id],
    queryFn: () => adminApi<AdminTicketDetail>(`/support/tickets/${id}`),
  });
}

function useAfterTicketChange() {
  const client = useQueryClient();
  return (detail: AdminTicketDetail) => {
    client.setQueryData([...keys.support, "ticket", detail.id], detail);
    void client.invalidateQueries({ queryKey: keys.support });
  };
}

export function useAdminTicketReply(id: number) {
  const after = useAfterTicketChange();
  return useMutation({
    mutationFn: (body: AdminTicketReply) =>
      adminApi<AdminTicketDetail>(`/support/tickets/${id}/reply`, {
        method: "POST",
        body: json(body),
      }),
    onSuccess: after,
  });
}

export function useAdminTicketPatch(id: number) {
  const after = useAfterTicketChange();
  return useMutation({
    mutationFn: (body: AdminTicketPatch) =>
      adminApi<AdminTicketDetail>(`/support/tickets/${id}`, {
        method: "PATCH",
        body: json(body),
      }),
    onSuccess: after,
  });
}

export function useCreateStaff() {
  const refresh = useRefreshAll();
  return useMutation({
    mutationFn: (body: StaffCreate) =>
      adminApi<StaffMember>("/staff", { method: "POST", body: json(body) }),
    onSuccess: () => refresh(),
  });
}

export function useUpdateStaff() {
  const refresh = useRefreshAll();
  return useMutation({
    mutationFn: ({ id, ...body }: StaffUpdate & { id: number }) =>
      adminApi<StaffMember>(`/staff/${id}`, { method: "PATCH", body: json(body) }),
    onSuccess: () => refresh(),
  });
}

export type StaffAction = "unlock" | "sign-out";

export function useStaffAction() {
  const refresh = useRefreshAll();
  return useMutation({
    mutationFn: ({ id, action }: { id: number; action: StaffAction }) =>
      adminApi<StaffMember>(`/staff/${id}/${action}`, { method: "POST" }),
    onSuccess: () => refresh(),
  });
}

export function useResetStaffPassword() {
  const refresh = useRefreshAll();
  return useMutation({
    mutationFn: (id: number) =>
      adminApi<{ temporary_password: string }>(`/staff/${id}/reset-password`, {
        method: "POST",
      }),
    onSuccess: () => refresh(),
  });
}
