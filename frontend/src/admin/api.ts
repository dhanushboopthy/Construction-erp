import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { json } from "@/api/client";

import { adminApi, adminClient } from "./client";
import type {
  AccessStatus,
  AdminAction,
  Backup,
  BackupJob,
  BackupSchedule,
  BackupScheduleIn,
  BackupSummary,
  AuditFilters,
  Maintenance,
  Notifications,
  PlatformSettings,
  SystemHealth,
  BillDiagnostics,
  BillRegistry,
  BillTemplate,
  BillTemplateList,
  BillUpload,
  AdminTicketDetail,
  AdminTicketFilters,
  AdminTicketPage,
  AdminTicketPatch,
  AdminTicketReply,
  BillingDashboard,
  CompanyUsageRow,
  DataDeleteResult,
  DataInventory,
  DataPreview,
  DataView,
  GstinDetails,
  Integration,
  IntegrationConnect,
  IntegrationFailure,
  IntegrationKind,
  IntegrationLimits,
  IntegrationTest,
  IntegrationUsage,
  NumberingList,
  NumberingRow,
  NumberingSet,
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
  SupportSessionPage,
  SupportSessionStarted,
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

export const ACCESS_POLL_MS = 30_000;

/** Whether the company's owner has let Duolink in now, and until when (M23). */
export function useAccessStatus(tenantId: number) {
  return useQuery({
    queryKey: [...keys.tenant(tenantId), "support-access"],
    queryFn: () => adminApi<AccessStatus>(`/tenants/${tenantId}/support-access`),
    refetchInterval: ACCESS_POLL_MS,
  });
}

/** Enter the company read-only. The answer holds the address to open: its token is in the
 * fragment, so no server log ever sees it. */
export function useEnterCompany(tenantId: number) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (reason: string) =>
      adminApi<SupportSessionStarted>(`/tenants/${tenantId}/support-session`, {
        method: "POST",
        body: json({ reason }),
      }),
    onSuccess: () => client.invalidateQueries({ queryKey: ["admin"] }),
  });
}

/** Every support session at every company (or one), newest first: Activity, Company access. */
export function useSupportSessions(filters: { tenant_id?: number } = {}) {
  return useQuery({
    queryKey: [...keys.audit, "support-sessions", filters],
    queryFn: () =>
      adminApi<SupportSessionPage>(`/audit/support-sessions${query({ ...filters, limit: 100 })}`),
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

// ------------------------------------------------------------------ Milestone 25

const BACKUP_POLL_MS = 2_000;
const backupKeys = {
  list: ["admin", "backups"] as const,
  summary: ["admin", "backups-summary"] as const,
  schedule: ["admin", "backups-schedule"] as const,
};

export function useBackups() {
  return useQuery({
    queryKey: backupKeys.list,
    queryFn: () => adminApi<{ items: Backup[] }>("/backups"),
    staleTime: 0,
  });
}

export function useBackupSummary() {
  return useQuery({
    queryKey: backupKeys.summary,
    queryFn: () => adminApi<BackupSummary>("/backups/summary"),
    staleTime: 0,
  });
}

export function useBackupSchedule() {
  return useQuery({
    queryKey: backupKeys.schedule,
    queryFn: () => adminApi<BackupSchedule>("/backups/schedule"),
  });
}

function useRefreshBackups() {
  const client = useQueryClient();
  return () => {
    void client.invalidateQueries({ queryKey: backupKeys.list });
    void client.invalidateQueries({ queryKey: backupKeys.summary });
    void client.invalidateQueries({ queryKey: keys.audit });
  };
}

/** A job is asked about every two seconds until it has succeeded or failed. */
export function useBackupJob(id: number | null) {
  const refresh = useRefreshBackups();
  return useQuery({
    queryKey: ["admin", "backup-job", id],
    enabled: id !== null,
    queryFn: async () => {
      const job = await adminApi<BackupJob>(`/backups/jobs/${id}`);
      if (job.status === "succeeded" || job.status === "failed") refresh();
      return job;
    },
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "succeeded" || status === "failed" ? false : BACKUP_POLL_MS;
    },
  });
}

export function useCreateBackup() {
  const refresh = useRefreshBackups();
  return useMutation({
    mutationFn: (body: { kind: "platform" | "company"; company_id?: number; note?: string }) =>
      adminApi<BackupJob>("/backups", { method: "POST", body: json(body) }),
    onSuccess: refresh,
  });
}

export function useRestoreBackup(backupId: number) {
  const refresh = useRefreshBackups();
  return useMutation({
    mutationFn: (body: { company_id: number; confirm: string }) =>
      adminApi<BackupJob>(`/backups/${backupId}/restore`, { method: "POST", body: json(body) }),
    onSuccess: refresh,
  });
}

export function useDeleteBackup(backupId: number) {
  const refresh = useRefreshBackups();
  return useMutation({
    mutationFn: (confirm: string) =>
      adminApi<undefined>(`/backups/${backupId}`, { method: "DELETE", body: json({ confirm }) }),
    onSuccess: refresh,
  });
}

export function useUploadBackup() {
  const refresh = useRefreshBackups();
  return useMutation({
    mutationFn: (file: File) => {
      const form = new FormData();
      form.append("file", file);
      return adminApi<Backup>("/backups/upload", { method: "POST", body: form });
    },
    onSuccess: refresh,
  });
}

export function useSetBackupSchedule() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: BackupScheduleIn) =>
      adminApi<BackupSchedule>("/backups/schedule", { method: "PUT", body: json(body) }),
    onSuccess: (data) => {
      client.setQueryData(backupKeys.schedule, data);
      void client.invalidateQueries({ queryKey: backupKeys.summary });
      void client.invalidateQueries({ queryKey: keys.audit });
    },
  });
}

/** Streams the file through the signed-in API (never a static link) and saves it. */
export async function downloadBackup(backup: Backup, part: "dump" | "files" = "dump") {
  const blob = await adminClient.fetchFile(`/backups/${backup.id}/download?part=${part}`);
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = part === "files" && backup.files_name ? backup.files_name : backup.file_name;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
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

// ------------------------------------------------------------------ bill designs (M28)

const designs = (tenantId: number) => `/tenants/${tenantId}/bill-templates`;
const designKeys = (tenantId: number) => ["admin", "bill-templates", tenantId] as const;

export function useBillDesigns(tenantId: number) {
  return useQuery({
    queryKey: [...designKeys(tenantId), "list"],
    queryFn: () => adminApi<BillTemplateList>(designs(tenantId)),
  });
}

export function useBillRegistry(tenantId: number, enabled: boolean) {
  return useQuery({
    queryKey: [...designKeys(tenantId), "registry"],
    queryFn: () => adminApi<BillRegistry>(`${designs(tenantId)}/field-registry`),
    enabled,
  });
}

export function useBillDiagnostics(tenantId: number, templateId: number | null) {
  return useQuery({
    queryKey: [...designKeys(tenantId), "diagnostics", templateId],
    queryFn: () => adminApi<BillDiagnostics>(`${designs(tenantId)}/${templateId}/diagnostics`),
    enabled: templateId !== null,
  });
}

/** The design drawn with sample figures. Fetched with the access token (an iframe cannot send
 * one), and fresh every time. */
export function previewBillDesign(tenantId: number, templateId: number): Promise<Blob> {
  return adminClient.fetchFile(`${designs(tenantId)}/${templateId}/preview`, { method: "POST" });
}

export interface DesignUpload {
  slot: string;
  name: string;
  html: File;
  images: File[];
}

function useDesignChange<T, V>(tenantId: number, run: (v: V) => Promise<T>) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: run,
    onSuccess: () => client.invalidateQueries({ queryKey: designKeys(tenantId) }),
  });
}

export function useUploadBillDesign(tenantId: number) {
  return useDesignChange(tenantId, (v: DesignUpload) => {
    const form = new FormData();
    form.append("slot", v.slot);
    form.append("name", v.name);
    form.append("html", v.html);
    for (const image of v.images) form.append("images", image);
    return adminApi<BillUpload>(designs(tenantId), { method: "POST", body: form });
  });
}

export function useChangeBillDesign(tenantId: number) {
  return useDesignChange(tenantId, (v: { id: number; action: "activate" | "deactivate" }) =>
    adminApi<BillTemplate>(`${designs(tenantId)}/${v.id}/${v.action}`, { method: "POST" }),
  );
}

export function useDeleteBillDesign(tenantId: number) {
  return useDesignChange(tenantId, (id: number) =>
    adminApi<undefined>(`${designs(tenantId)}/${id}`, { method: "DELETE" }),
  );
}

export function useSetSecondaryLogo(tenantId: number) {
  return useDesignChange(tenantId, (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return adminApi<BillTemplateList>(`${designs(tenantId)}/secondary-logo`, {
      method: "PUT",
      body: form,
    });
  });
}

export function useRemoveSecondaryLogo(tenantId: number) {
  return useDesignChange(tenantId, () =>
    adminApi<BillTemplateList>(`${designs(tenantId)}/secondary-logo`, { method: "DELETE" }),
  );
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

const integrationKeys = { all: ["admin", "integrations"] as const };

/** Both integrations. Support may read this; usage and the rest are a Super Admin's. */
export function useIntegrations() {
  return useQuery({
    queryKey: [...integrationKeys.all, "status"],
    queryFn: () => adminApi<Integration[]>("/integrations"),
  });
}

export function useIntegrationUsage(enabled: boolean) {
  return useQuery({
    queryKey: [...integrationKeys.all, "usage"],
    queryFn: () => adminApi<IntegrationUsage[]>("/integrations/usage"),
    enabled,
  });
}

export function useCompanyUsage(kind: IntegrationKind, enabled: boolean) {
  return useQuery({
    queryKey: [...integrationKeys.all, kind, "companies"],
    queryFn: () => adminApi<CompanyUsageRow[]>(`/integrations/${kind}/companies`),
    enabled,
  });
}

export function useIntegrationFailures(kind: IntegrationKind, enabled: boolean) {
  return useQuery({
    queryKey: [...integrationKeys.all, kind, "failures"],
    queryFn: () => adminApi<IntegrationFailure[]>(`/integrations/${kind}/failures`),
    enabled,
  });
}

function useAfterIntegrationChange() {
  const client = useQueryClient();
  return () => client.invalidateQueries({ queryKey: integrationKeys.all });
}

export function useConnectIntegration(kind: IntegrationKind) {
  const after = useAfterIntegrationChange();
  return useMutation({
    mutationFn: (body: IntegrationConnect) =>
      adminApi<Integration>(`/integrations/${kind}`, { method: "PUT", body: json(body) }),
    onSuccess: after,
  });
}

export function useTestIntegration(kind: IntegrationKind) {
  const after = useAfterIntegrationChange();
  return useMutation({
    mutationFn: () => adminApi<IntegrationTest>(`/integrations/${kind}/test`, { method: "POST" }),
    onSuccess: after,
  });
}

export function useDisconnectIntegration(kind: IntegrationKind) {
  const after = useAfterIntegrationChange();
  return useMutation({
    mutationFn: () => adminApi<Integration>(`/integrations/${kind}/disconnect`, { method: "POST" }),
    onSuccess: after,
  });
}

export function useIntegrationLimits(kind: IntegrationKind) {
  const after = useAfterIntegrationChange();
  return useMutation({
    mutationFn: (body: IntegrationLimits) =>
      adminApi<Integration>(`/integrations/${kind}/limits`, { method: "PATCH", body: json(body) }),
    onSuccess: after,
  });
}

/** "Fetch details" on the onboarding form: the registry's answer for a GSTIN. */
export function useAdminGstinLookup() {
  return useMutation({
    mutationFn: (gstin: string) =>
      adminApi<GstinDetails>("/integrations/gstin-lookup", {
        method: "POST",
        body: json({ gstin }),
      }),
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

// ------------------------------------------------------------- Milestone 26: data and numbering

const dataKeys = {
  inventory: (id: number) => ["admin", "company-data", id] as const,
  numbering: (id: number) => ["admin", "company-numbering", id] as const,
};

export function useCompanyData(id: number) {
  return useQuery({
    queryKey: dataKeys.inventory(id),
    queryFn: () => adminApi<DataInventory>(`/tenants/${id}/data`),
  });
}

export function useCompanyDataView(id: number, key: string | null) {
  return useQuery({
    queryKey: ["admin", "company-data-view", id, key],
    enabled: key !== null,
    gcTime: 0,
    queryFn: () => adminApi<DataView>(`/tenants/${id}/data/${key}`),
  });
}

/** Read again every time a dialog opens (never carried over from the tab): `gcTime: 0` and no
 * stale time, so a dialog opened twice asks twice. `keys` null means everything. */
export function useDataPreview(id: number, keys: string[] | null, enabled: boolean) {
  const search = keys ? keys.map((k) => `keys=${encodeURIComponent(k)}`).join("&") : "";
  return useQuery({
    queryKey: ["admin", "company-data-preview", id, search],
    enabled,
    gcTime: 0,
    staleTime: 0,
    queryFn: () =>
      adminApi<DataPreview>(`/tenants/${id}/data/preview${search ? `?${search}` : ""}`),
  });
}

function useRefreshData(id: number) {
  const client = useQueryClient();
  return () => {
    void client.invalidateQueries({ queryKey: dataKeys.inventory(id) });
    void client.invalidateQueries({ queryKey: dataKeys.numbering(id) });
    void client.invalidateQueries({ queryKey: ["admin", "company-data-view", id] });
    void client.invalidateQueries({ queryKey: keys.audit });
  };
}

export function useDeleteCompanyData(id: number) {
  const refresh = useRefreshData(id);
  return useMutation({
    mutationFn: (body: { keys: string[]; confirm: string }) =>
      adminApi<DataDeleteResult>(`/tenants/${id}/data/delete`, {
        method: "POST",
        body: json(body),
      }),
    onSuccess: refresh,
  });
}

export function useDeleteAllCompanyData(id: number) {
  const refresh = useRefreshData(id);
  return useMutation({
    mutationFn: (body: { confirm: string; company_name: string; acknowledged: boolean }) =>
      adminApi<DataDeleteResult>(`/tenants/${id}/data/delete-all`, {
        method: "POST",
        body: json(body),
      }),
    onSuccess: refresh,
  });
}

export function useNumbering(id: number) {
  return useQuery({
    queryKey: dataKeys.numbering(id),
    queryFn: () => adminApi<NumberingList>(`/tenants/${id}/numbering`),
  });
}

export function useSetNumbering(id: number) {
  const refresh = useRefreshData(id);
  return useMutation({
    mutationFn: (body: NumberingSet) =>
      adminApi<NumberingRow>(`/tenants/${id}/numbering`, { method: "PATCH", body: json(body) }),
    onSuccess: refresh,
  });
}
