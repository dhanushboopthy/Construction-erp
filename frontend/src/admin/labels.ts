// Words for the admin screens, kept in one place (Tamil or other labels can follow).

import type {
  AdminActionKind,
  DurationUnit,
  PlatformRole,
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
  const [whole = "0", fraction] = price.split(".");
  const last3 = whole.slice(-3);
  const rest = whole.slice(0, -3).replace(/\B(?=(\d{2})+(?!\d))/g, ",");
  const grouped = rest ? `${rest},${last3}` : last3;
  return `₹${grouped}${fraction === undefined ? "" : `.${fraction}`}`;
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
};

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
