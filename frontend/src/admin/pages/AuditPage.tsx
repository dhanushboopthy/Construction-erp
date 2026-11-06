import { useState } from "react";
import { Link, useSearchParams } from "react-router";

import { Button } from "@/components/Button";
import { SelectField, TextField } from "@/components/Field";
import styles from "@/components/Ledger.module.css";

import { useAdminAuth } from "../AdminAuthContext";
import { downloadAuditCsv, useStaff, useTenants } from "../api";
import { ACTION, SIGN_IN } from "../labels";
import { SupportSessions } from "../SupportSessions";
import type { AdminActionKind, AuditFilters } from "../types";
import { AdminActions, SignIns } from "./ActivityPage";

const TABS = [
  { value: "admin", label: "Admin actions" },
  { value: "access", label: "Company access" },
  { value: "sign-ins", label: "Sign-ins" },
] as const;
type Tab = (typeof TABS)[number]["value"];

/**
 * The audit log (Milestone 24): what Duolink's admins did, company access sessions, and
 * sign-ins at companies, with filters by dates, admin, company and action. A Super Admin exports
 * the filtered admin actions as CSV; the file has the same rows as the screen.
 */
export function AuditPage() {
  const [params, setParams] = useSearchParams();
  const { isSuperAdmin } = useAdminAuth();
  const tab: Tab = TABS.find((t) => t.value === params.get("tab"))?.value ?? "admin";
  const staff = useStaff();
  const companies = useTenants({ limit: 200 });
  const [exportError, setExportError] = useState<string | null>(null);

  const get = (key: string) => params.get(key) ?? "";
  const setFilter = (key: string, value: string) =>
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        if (value) next.set(key, value);
        else next.delete(key);
        return next;
      },
      { replace: true },
    );

  const filters: AuditFilters = {
    admin_id: get("admin_id") ? Number(get("admin_id")) : undefined,
    tenant_id: get("tenant_id") ? Number(get("tenant_id")) : undefined,
    action: tab === "admin" ? get("action") || undefined : undefined,
    date_from: get("date_from") || undefined,
    date_to: get("date_to") || undefined,
  };

  const exportCsv = () => {
    setExportError(null);
    downloadAuditCsv(filters).catch((e: Error) => setExportError(e.message));
  };

  return (
    <section aria-labelledby="audit-title" className={styles.page}>
      <h1 id="audit-title" className={styles.title}>
        Audit log
      </h1>
      <nav aria-label="Audit views">
        <ul className={styles.tabs}>
          {TABS.map((t) => (
            <li key={t.value}>
              <Link
                to={`/admin/audit?tab=${t.value}`}
                className={tab === t.value ? styles.tabActive : styles.tab}
                aria-current={tab === t.value ? "page" : undefined}
              >
                {t.label}
              </Link>
            </li>
          ))}
        </ul>
      </nav>

      <div className={styles.filters}>
        <TextField
          label="From"
          type="date"
          value={get("date_from")}
          onChange={(e) => setFilter("date_from", e.target.value)}
        />
        <TextField
          label="To"
          type="date"
          value={get("date_to")}
          onChange={(e) => setFilter("date_to", e.target.value)}
        />
        {tab === "admin" && (
          <SelectField
            label="Admin"
            value={get("admin_id")}
            onChange={(e) => setFilter("admin_id", e.target.value)}
          >
            <option value="">Every admin</option>
            {staff.data?.map((m) => (
              <option key={m.id} value={m.id}>
                {m.full_name}
              </option>
            ))}
          </SelectField>
        )}
        <SelectField
          label="Company"
          value={get("tenant_id")}
          onChange={(e) => setFilter("tenant_id", e.target.value)}
        >
          <option value="">Every company</option>
          {companies.data?.items.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </SelectField>
        {tab === "admin" && (
          <SelectField
            label="Action"
            value={get("action")}
            onChange={(e) => setFilter("action", e.target.value)}
          >
            <option value="">Every action</option>
            {(Object.entries(ACTION) as [AdminActionKind, string][]).map(([key, label]) => (
              <option key={key} value={key}>
                {label}
              </option>
            ))}
          </SelectField>
        )}
        {tab === "sign-ins" && (
          <SelectField
            label="Show"
            value={get("action")}
            onChange={(e) => setFilter("action", e.target.value)}
          >
            <option value="">Every sign-in</option>
            {Object.entries(SIGN_IN).map(([key, s]) => (
              <option key={key} value={key}>
                {s.label}
              </option>
            ))}
          </SelectField>
        )}
      </div>

      {tab === "admin" && (
        <>
          {isSuperAdmin && (
            <div className={styles.actions}>
              <Button allowWhenReadOnly onClick={exportCsv}>
                Export CSV
              </Button>
              {exportError && (
                <span role="alert" className={styles.formError}>
                  {exportError}
                </span>
              )}
            </div>
          )}
          <AdminActions filters={filters} />
        </>
      )}
      {tab === "access" && <SupportSessions tenantId={filters.tenant_id} />}
      {tab === "sign-ins" && (
        <SignIns
          action={get("action")}
          tenantId={filters.tenant_id}
          dateFrom={filters.date_from}
          dateTo={filters.date_to}
        />
      )}
    </section>
  );
}
