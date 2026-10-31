// Words for the admin screens, kept in one place (Tamil or other labels can follow).

import type { AdminActionKind, PlatformRole, TenantPlan, TenantStatus, TrialState } from "./types";

export type Tone = "accent" | "good" | "warn" | "critical" | "neutral";

export const STATUS: Record<TenantStatus, { label: string; tone: Tone }> = {
  trial: { label: "On trial", tone: "accent" },
  active: { label: "Active", tone: "good" },
  suspended: { label: "Suspended", tone: "critical" },
  cancelled: { label: "Closed", tone: "neutral" },
};

export const STATUS_ORDER: TenantStatus[] = ["active", "trial", "suspended", "cancelled"];

export const PLAN: Record<TenantPlan, { label: string; note: string }> = {
  trial: { label: "Trial", note: "14 days, 5 users, 2 shops and godowns" },
  basic: { label: "Basic", note: "10 users, 3 shops and godowns" },
  pro: { label: "Pro", note: "50 users, 10 shops and godowns" },
};

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
