import { useCallback, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router";

import { Button } from "@/components/Button";
import { CheckField, SelectField, TextField } from "@/components/Field";
import styles from "@/components/Ledger.module.css";
import { moveRowFocus, useAltKey } from "@/hooks/useKeys";
import { formatDateTime } from "@/lib/format";

import { COMPANY_PAGE_SIZE, useTenants } from "../api";
import { useAdminAuth } from "../AdminAuthContext";
import { Badge, Usage } from "../Badge";
import { PLAN, STATUS, STATUS_ORDER, TRIAL } from "../labels";

const TRIAL_STATES = [
  { value: "running", label: "Trial running" },
  { value: "ending", label: "Trial ends this week" },
  { value: "ended", label: "Trial ended" },
  { value: "none", label: "Not on a trial" },
];
const SORTS = [
  { value: "name", label: "Name" },
  { value: "created", label: "Joined" },
  { value: "last_activity", label: "Last activity" },
  { value: "users", label: "Users" },
];
import type { TenantPlan } from "../types";

export function CompaniesPage() {
  const navigate = useNavigate();
  const { isSuperAdmin } = useAdminAuth();
  const [params, setParams] = useSearchParams();
  const [q, setQ] = useState(params.get("q") ?? "");
  const status = params.get("status") ?? "";
  const plan = params.get("plan") ?? "";
  const trial = params.get("trial") ?? "";
  const expiring = params.get("expiring") === "1";
  const sort = params.get("sort") ?? "name";
  const order = params.get("order") === "desc" ? "desc" : "asc";
  const page = Math.max(0, Number(params.get("page") ?? 0) || 0);
  const tenants = useTenants({
    q: params.get("q") ?? "",
    status,
    plan,
    trial,
    expiring,
    sort,
    order,
    offset: page * COMPANY_PAGE_SIZE,
  });

  const openNew = useCallback(() => void navigate("/admin/companies/new"), [navigate]);
  useAltKey("n", isSuperAdmin ? openNew : () => undefined);

  const setFilter = (key: string, value: string) =>
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        if (value) next.set(key, value);
        else next.delete(key);
        if (key !== "page") next.delete("page"); // a new search starts at the first page
        return next;
      },
      { replace: true },
    );

  return (
    <section aria-labelledby="companies-title" className={styles.page}>
      <div className={styles.toolbar}>
        <h1 id="companies-title" className={styles.title}>
          Companies
        </h1>
        {isSuperAdmin ? (
          <Button variant="primary" onClick={openNew} aria-keyshortcuts="Alt+N">
            Add company
          </Button>
        ) : null}
        <p className={styles.keys}>{isSuperAdmin ? "Alt+N new · " : ""}↑↓ move · Enter open</p>
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
            placeholder="Name, code, owner or GSTIN"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onBlur={() => setFilter("q", q.trim())}
          />
        </div>
        <SelectField
          label="Status"
          value={status}
          onChange={(e) => setFilter("status", e.target.value)}
        >
          <option value="">Any status</option>
          {STATUS_ORDER.map((s) => (
            <option key={s} value={s}>
              {STATUS[s].label}
            </option>
          ))}
        </SelectField>
        <SelectField label="Plan" value={plan} onChange={(e) => setFilter("plan", e.target.value)}>
          <option value="">Any plan</option>
          {(Object.keys(PLAN) as TenantPlan[]).map((p) => (
            <option key={p} value={p}>
              {PLAN[p].label}
            </option>
          ))}
        </SelectField>
        <SelectField
          label="Trial"
          value={trial}
          onChange={(e) => setFilter("trial", e.target.value)}
        >
          <option value="">Any</option>
          {TRIAL_STATES.map((t) => (
            <option key={t.value} value={t.value}>
              {t.label}
            </option>
          ))}
        </SelectField>
        <SelectField
          label="Sort by"
          value={sort}
          onChange={(e) => setFilter("sort", e.target.value)}
        >
          {SORTS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </SelectField>
        <SelectField
          label="Order"
          value={order}
          onChange={(e) => setFilter("order", e.target.value === "desc" ? "desc" : "")}
        >
          <option value="asc">Smallest or oldest first</option>
          <option value="desc">Largest or newest first</option>
        </SelectField>
        <CheckField
          label="Ending within 30 days"
          checked={expiring}
          onChange={(e) => setFilter("expiring", e.target.checked ? "1" : "")}
        />
      </form>

      {tenants.isPending ? (
        <p role="status">Loading companies…</p>
      ) : tenants.isError ? (
        <p className={styles.formError}>Companies could not be loaded. Reload the page.</p>
      ) : (
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th scope="col">Company</th>
                <th scope="col">Owner</th>
                <th scope="col">Status</th>
                <th scope="col">Plan</th>
                <th scope="col">Users</th>
                <th scope="col">Shops and godowns</th>
                <th scope="col" className="num">
                  Bills, 30 days
                </th>
                <th scope="col">Last activity</th>
              </tr>
            </thead>
            <tbody onKeyDown={moveRowFocus}>
              {tenants.data.items.length ? (
                tenants.data.items.map((t) => {
                  const trial = TRIAL[t.trial_state];
                  return (
                    <tr key={t.id} className={t.status === "suspended" ? styles.inactive : ""}>
                      <td>
                        <Link to={`/admin/companies/${t.id}`} data-row={t.id}>
                          {t.name}
                        </Link>
                        <div className={styles.sub}>
                          {t.slug}
                          {t.city ? ` · ${t.city}` : ""}
                        </div>
                      </td>
                      <td>{t.owner_name ?? "—"}</td>
                      <td>
                        <Badge tone={STATUS[t.status].tone}>{STATUS[t.status].label}</Badge>
                        {trial && t.status === "trial" && t.trial_state !== "running" ? (
                          <div>
                            <Badge tone={trial.tone}>{trial.label}</Badge>
                          </div>
                        ) : null}
                      </td>
                      <td>{PLAN[t.plan].label}</td>
                      <td>
                        <Usage used={t.users} limit={t.max_users} label="active users" />
                      </td>
                      <td>
                        <Usage
                          used={t.locations}
                          limit={t.max_locations}
                          label="shops and godowns"
                        />
                      </td>
                      <td className="num">{t.bills_30d}</td>
                      <td>{formatDateTime(t.last_activity_at ?? t.last_sign_in_at)}</td>
                    </tr>
                  );
                })
              ) : (
                <tr>
                  <td colSpan={8} className={styles.empty}>
                    {params.toString()
                      ? "No company matches. Clear the search or filters."
                      : isSuperAdmin
                        ? "No companies yet. Add the first one."
                        : "No companies yet."}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
          <p className={styles.results}>
            {tenants.data.total} {tenants.data.total === 1 ? "company" : "companies"}
            {tenants.data.total > COMPANY_PAGE_SIZE
              ? `, showing ${page * COMPANY_PAGE_SIZE + 1} to ${Math.min(
                  tenants.data.total,
                  (page + 1) * COMPANY_PAGE_SIZE,
                )}`
              : ""}
          </p>
          {tenants.data.total > COMPANY_PAGE_SIZE ? (
            <nav aria-label="Pages" className={styles.actions}>
              <Button disabled={page === 0} onClick={() => setFilter("page", String(page - 1))}>
                Previous
              </Button>
              <Button
                disabled={(page + 1) * COMPANY_PAGE_SIZE >= tenants.data.total}
                onClick={() => setFilter("page", String(page + 1))}
              >
                Next
              </Button>
            </nav>
          ) : null}
        </div>
      )}
    </section>
  );
}
