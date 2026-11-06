// Words for the admin screens, kept in one place (Tamil or other labels can follow).

import type {
  AdminActionKind,
  DurationUnit,
  PaymentMethod,
  PlatformRole,
  SubscriptionStatus,
  TenantStatus,
  TrialState,
} from "./types";

export type Tone = "accent" | "good" | "warn" | "critical" | "neutral";

export const STATUS: Record<TenantStatus, { label: string; tone: Tone }> = {
  trial: { label: "On trial", tone: "accent" },
  active: { label: "Active", tone: "good" },
  suspended: { label: "Suspended", tone: "critical" },
  cancelled: { label: "Closed", tone: "neutral" },
};

export const STATUS_ORDER: TenantStatus[] = ["active", "trial", "suspended", "cancelled"];

/** The plan a new company starts on; the only one that has a trial. */
export const TRIAL_PLAN = "TRIAL";

/** "10 users, 3 shops and godowns": a plan's limits in words. */
export function limitsNote(plan: { max_users: number; max_locations: number }): string {
  const users = plan.max_users === 1 ? "1 user" : `${plan.max_users} users`;
  return `${users}, ${plan.max_locations} ${plan.max_locations === 1 ? "shop or godown" : "shops and godowns"}`;
}

/** "1 month", "14 days", "1 year". */
export function durationLabel(value: number, unit: DurationUnit): string {
  return `${value} ${unit}${value === 1 ? "" : "s"}`;
}

/** A price kept as the text the server sent: "9999.00" becomes "₹9,999.00" (Indian grouping).
 * Never parsed to a number, so no digit can change on the way to the screen. */
export function rupees(price: string): string {
  if (price.startsWith("-")) return `-${rupees(price.slice(1))}`;
  const [whole = "0", fraction] = price.split(".");
  const last3 = whole.slice(-3);
  const rest = whole.slice(0, -3).replace(/\B(?=(\d{2})+(?!\d))/g, ",");
  const grouped = rest ? `${rest},${last3}` : last3;
  return `₹${grouped}${fraction === undefined ? "" : `.${fraction}`}`;
}

export const SUBSCRIPTION: Record<SubscriptionStatus, { label: string; tone: Tone }> = {
  trial: { label: "On trial", tone: "accent" },
  active: { label: "Active", tone: "good" },
  expired: { label: "Expired", tone: "critical" },
  cancelled: { label: "Cancelled", tone: "neutral" },
};

export const SUBSCRIPTION_ORDER: SubscriptionStatus[] = ["active", "trial", "expired", "cancelled"];

export const METHODS: { value: PaymentMethod; label: string }[] = [
  { value: "cash", label: "Cash" },
  { value: "bank", label: "Bank transfer" },
  { value: "upi", label: "UPI" },
  { value: "cheque", label: "Cheque" },
  { value: "razorpay", label: "Razorpay" },
];

export const methodLabel = (m: PaymentMethod) => METHODS.find((o) => o.value === m)?.label ?? m;

/** "2026-11" as "Nov 2026" (no time zone shift: it is a calendar month). */
export function monthLabel(month: string): string {
  const [y = "1970", m = "1"] = month.split("-");
  const name = new Intl.DateTimeFormat("en-IN", { timeZone: "UTC", month: "short" }).format(
    new Date(Date.UTC(Number(y), Number(m) - 1, 1)),
  );
  return `${name} ${y}`;
}

/** Days left as words: "12 days left", "ended 3 days ago", "ends today". */
export function daysLeftLabel(days: number | null): string {
  if (days === null) return "No end date";
  if (days === 0) return "Ends today";
  if (days > 0) return `${days} ${days === 1 ? "day" : "days"} left`;
  const ago = -days;
  return `Ended ${ago} ${ago === 1 ? "day" : "days"} ago`;
}

export const TRIAL: Record<TrialState, { label: string; tone: Tone } | null> = {
  none: null,
  running: { label: "Trial running", tone: "accent" },
  ending: { label: "Trial ends this week", tone: "warn" },
  ended: { label: "Trial ended", tone: "critical" },
};

export const ROLE = { owner: "Owner", counter: "Counter staff", accountant: "Accountant" } as const;

export const SIGN_IN: Record<string, { label: string; tone: Tone }> = {
  login: { label: "Signed in", tone: "good" },
  login_failed: { label: "Wrong password", tone: "warn" },
  token_reuse: { label: "Reused session (possible theft)", tone: "critical" },
};

export const ACTION: Record<AdminActionKind, string> = {
  login: "Signed in",
  login_failed: "Failed sign-in",
  logout: "Signed out",
  token_reuse: "Reused session",
  tenant_create: "Created company",
  tenant_update: "Changed plan or limits",
  tenant_suspend: "Suspended company",
  tenant_reactivate: "Reactivated company",
  user_activate: "Reactivated user",
  user_deactivate: "Deactivated user",
  user_unlock: "Unlocked user",
  user_reset_password: "Reset password",
  user_sign_out: "Signed user out",
  staff_create: "Added staff member",
  staff_update: "Changed staff member",
  staff_reset_password: "Reset staff password",
  staff_unlock: "Unlocked staff member",
  staff_sign_out: "Signed staff member out",
  password_change: "Changed own password",
  tenant_cancel: "Closed company",
  tenant_seller_update: "Corrected seller details",
  tenant_logo_set: "Set company logo",
  tenant_logo_remove: "Removed company logo",
  user_update: "Edited user",
  user_session_revoke: "Ended one session",
  user_remove: "Removed user's access",
  plan_create: "Added a plan",
  plan_update: "Edited a plan",
  plan_duplicate: "Copied a plan",
  plan_archive: "Archived a plan",
  plan_delete: "Deleted a plan",
  subscription_renew: "Renewed a subscription",
  subscription_cancel: "Cancelled a subscription",
  payment_reverse: "Reversed a payment",
  support_reply: "Replied to a ticket",
  support_update: "Changed a ticket",
  support_session_start: "Entered a company (read-only)",
  support_session_end: "Left a company",
  maintenance_on: "Turned maintenance mode on",
  maintenance_off: "Turned maintenance mode off",
  audit_export: "Exported the audit log",
  backup_create: "Started a backup",
  backup_download: "Downloaded a backup",
  backup_upload: "Uploaded a company backup",
  backup_delete: "Deleted a backup",
  backup_restore: "Restored a company from a backup",
  backup_restore_failed: "A company restore failed and was rolled back",
  backup_schedule_update: "Changed the backup schedule",
  numbering_set: "Set a document number series",
  company_data_deleted: "Deleted selected company data",
  company_data_deleted_all: "Deleted all of a company's data",
  company_data_delete_failed: "A company data deletion failed and was rolled back",
};

/** How serious a bell item is, in words as well as colour (Milestone 24). */
export const NOTIFICATION_LEVEL: Record<
  "critical" | "warning" | "info",
  { label: string; tone: Tone }
> = {
  critical: { label: "Urgent", tone: "critical" },
  warning: { label: "Warning", tone: "warn" },
  info: { label: "For information", tone: "neutral" },
};

/** Bytes as "12.4 GB", for the health page's disk and database figures. */
export function formatBytes(bytes: number | null | undefined): string {
  if (bytes === null || bytes === undefined) return "—";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${unit === 0 ? value : value.toFixed(1)} ${units[unit]}`;
}

/** "3 d 4 h" or "12 min": how long the API has been up. */
export function formatUptime(seconds: number): string {
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  if (days > 0) return `${days} d ${hours} h`;
  if (hours > 0) return `${hours} h ${minutes} min`;
  return `${minutes} min`;
}

/** Duolink staff roles: what each may do, in words (ADR 0013). */
export const ADMIN_ROLE: Record<PlatformRole, { label: string; note: string; tone: Tone }> = {
  super_admin: {
    label: "Super Admin",
    note: "Can change companies, users and staff.",
    tone: "accent",
  },
  support: {
    label: "Support",
    note: "Can read everything and answer tickets. Changes nothing else.",
    tone: "neutral",
  },
};

/** The company's own address: acme on admin.duolink.app is acme.duolink.app. */
export function companyAddress(slug: string, location: Location = window.location): string {
  const base = location.hostname.replace(/^admin\./, "");
  const port = location.port ? `:${location.port}` : "";
  return `${location.protocol}//${slug}.${base}${port}`;
}
