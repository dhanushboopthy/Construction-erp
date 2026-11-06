import { useState } from "react";
import { useSearchParams } from "react-router";

import { CheckField, SelectField, TextField } from "@/components/Field";
import styles from "@/components/Ledger.module.css";

import { useTenants, type UserFilters } from "../api";
import { ROLE } from "../labels";
import { UsersView } from "../UsersView";

/** One choice in the address (?status=locked) becomes the API's filters. */
const STATUS: { value: string; label: string; filters: UserFilters }[] = [
  { value: "", label: "Any status", filters: {} },
  { value: "active", label: "Active", filters: { active: "true" } },
  { value: "inactive", label: "Deactivated", filters: { active: "false" } },
  { value: "locked", label: "Locked out", filters: { locked: "true" } },
  { value: "never", label: "Never signed in", filters: { never_signed_in: "true" } },
];

export function UsersPage() {
  const [params, setParams] = useSearchParams();
  const [q, setQ] = useState(params.get("q") ?? "");
  const status = params.get("status") ?? "";
  const role = params.get("role") ?? "";
  const company = params.get("company") ?? "";
  const removed = params.get("removed") === "1";
  const companies = useTenants({ limit: 100, sort: "name" });

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

  const filters: Omit<UserFilters, "tenant_id" | "offset"> = {
    q: params.get("q") ?? "",
    role,
    include_removed: removed ? "true" : "",
    ...(STATUS.find((s) => s.value === status)?.filters ?? {}),
  };

  return (
    <section aria-labelledby="users-title" className={styles.page}>
      <div className={styles.toolbar}>
        <h1 id="users-title" className={styles.title}>
          Users
        </h1>
        <p className={styles.keys}>↑↓ move · Enter open · Esc close</p>
      </div>
      <form
        className={styles.filters}
        role="search"
        onSubmit={(e) => {
          e.preventDefault();
          setFilter("q", q.trim());
        }}
      >
        <div className={styles.search}>
          <TextField
            label="Search"
            type="search"
            placeholder="Name, username or company"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onBlur={() => setFilter("q", q.trim())}
          />
        </div>
        <SelectField
          label="Company"
          value={company}
          onChange={(e) => setFilter("company", e.target.value)}
        >
          <option value="">Every company</option>
          {companies.data?.items.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </SelectField>
        <SelectField label="Role" value={role} onChange={(e) => setFilter("role", e.target.value)}>
          <option value="">Any role</option>
          {(Object.keys(ROLE) as (keyof typeof ROLE)[]).map((r) => (
            <option key={r} value={r}>
              {ROLE[r]}
            </option>
          ))}
        </SelectField>
        <SelectField
          label="Status"
          value={status}
          onChange={(e) => setFilter("status", e.target.value)}
        >
          {STATUS.map((s) => (
            <option key={s.value} value={s.value}>
              {s.label}
            </option>
          ))}
        </SelectField>
        <CheckField
          label="Show removed"
          checked={removed}
          onChange={(e) => setFilter("removed", e.target.checked ? "1" : "")}
        />
      </form>
      <UsersView
        key={JSON.stringify([filters, company])}
        tenantId={company ? Number(company) : undefined}
        filters={filters}
      />
    </section>
  );
}
