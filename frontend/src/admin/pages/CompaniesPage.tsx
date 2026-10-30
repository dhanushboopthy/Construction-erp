import { useCallback, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router";

import { Button } from "@/components/Button";
import { SelectField, TextField } from "@/components/Field";
import styles from "@/components/Ledger.module.css";
import { moveRowFocus, useAltKey } from "@/hooks/useKeys";
import { formatDateTime } from "@/lib/format";

import { useTenants } from "../api";
import { Badge, Usage } from "../Badge";
import { PLAN, STATUS, STATUS_ORDER, TRIAL } from "../labels";
import type { TenantPlan } from "../types";

export function CompaniesPage() {
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const [q, setQ] = useState(params.get("q") ?? "");
  const status = params.get("status") ?? "";
  const plan = params.get("plan") ?? "";
  const tenants = useTenants({ q: params.get("q") ?? "", status, plan });

  const openNew = useCallback(() => void navigate("/admin/companies/new"), [navigate]);
  useAltKey("n", openNew);

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

  return (
    <section aria-labelledby="companies-title" className={styles.page}>
      <div className={styles.toolbar}>
        <h1 id="companies-title" className={styles.title}>
          Companies
        </h1>
        <Button variant="primary" onClick={openNew} aria-keyshortcuts="Alt+N">
          Add company
        </Button>
        <p className={styles.keys}>Alt+N new · ↑↓ move · Enter open</p>
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
            placeholder="Name or company code"
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
                <th scope="col">Status</th>
                <th scope="col">Plan</th>
                <th scope="col">Users</th>
                <th scope="col">Shops and godowns</th>
                <th scope="col" className="num">
                  Bills, 30 days
                </th>
                <th scope="col">Last sign-in</th>
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
                        <div className={styles.sub}>{t.slug}</div>
                      </td>
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
                      <td>{formatDateTime(t.last_sign_in_at)}</td>
                    </tr>
                  );
                })
              ) : (
                <tr>
                  <td colSpan={7} className={styles.empty}>
                    {params.toString()
                      ? "No company matches. Clear the search or filters."
                      : "No companies yet. Add the first one."}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
          <p className={styles.results}>
            {tenants.data.total} {tenants.data.total === 1 ? "company" : "companies"}
          </p>
        </div>
      )}
    </section>
  );
}
