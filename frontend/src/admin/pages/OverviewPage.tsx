import { Link } from "react-router";

import styles from "@/components/Ledger.module.css";
import { formatDateTime, plural } from "@/lib/format";

import { useBillingDashboard, useOverview } from "../api";
import adminStyles from "../Admin.module.css";
import chartStyles from "../Chart.module.css";
import { STATUS, STATUS_ORDER, monthLabel, rupees } from "../labels";
import { TrendChart } from "../TrendChart";
import type { TenantStatus } from "../types";

/** Duolink's own income, from /billing/dashboard only: revenue, subscriptions and a 12-month trend. */
function RevenueSection() {
  const dash = useBillingDashboard();
  if (dash.isPending) return <p role="status">Loading revenue…</p>;
  if (dash.isError) {
    return (
      <p role="alert" className={styles.formError}>
        Revenue figures could not be loaded.
      </p>
    );
  }
  const d = dash.data;
  return (
    <>
      <dl className={adminStyles.stats} aria-label="Revenue and subscriptions">
        <div className={adminStyles.stat}>
          <dt>Revenue this month</dt>
          <dd className={adminStyles.statValue}>{rupees(d.revenue_month)}</dd>
          <dd className={adminStyles.statNote}>
            <Link to="/admin/payments">See payments</Link>
          </dd>
        </div>
        <div className={adminStyles.stat}>
          <dt>Revenue this financial year</dt>
          <dd className={adminStyles.statValue}>{rupees(d.revenue_fy)}</dd>
          <dd className={adminStyles.statNote}>April to March</dd>
        </div>
        <div className={adminStyles.stat}>
          <dt>Active subscriptions</dt>
          <dd className={adminStyles.statValue}>{d.active_subscriptions}</dd>
          <dd className={adminStyles.statNote}>
            <Link to="/admin/subscriptions?status=active">See them</Link>
          </dd>
        </div>
        <div className={adminStyles.stat}>
          <dt>Renewals this month</dt>
          <dd className={adminStyles.statValue}>{d.renewals_month}</dd>
          <dd className={adminStyles.statNote}>Payments recorded</dd>
        </div>
        <div className={adminStyles.stat}>
          <dt>New companies this month</dt>
          <dd className={adminStyles.statValue}>{d.new_companies_month}</dd>
          <dd className={adminStyles.statNote}>Signed up</dd>
        </div>
        <div className={adminStyles.stat} data-tone={d.expiring_30 > 0 ? "warn" : undefined}>
          <dt>Expiring in 30 days</dt>
          <dd className={adminStyles.statValue}>{d.expiring_30}</dd>
          <dd className={adminStyles.statNote}>
            <Link to="/admin/subscriptions?expiring_within=30">See who</Link>
          </dd>
        </div>
      </dl>
      <div className={chartStyles.charts}>
        <TrendChart
          title="Revenue, last 12 months"
          series="Revenue"
          tone={1}
          bars={d.trend.map((p) => ({
            label: monthLabel(p.month),
            // Height only; the figure written is the server's text.
            height: Number(p.revenue),
            text: rupees(p.revenue),
          }))}
        />
        <TrendChart
          title="New companies, last 12 months"
          series="Sign-ups"
          tone={2}
          bars={d.trend.map((p) => ({
            label: monthLabel(p.month),
            height: p.signups,
            text: String(p.signups),
          }))}
        />
      </div>
    </>
  );
}

/** What Duolink checks first: how many companies, in what state, and who is signing in. */
export function OverviewPage() {
  const overview = useOverview();

  if (overview.isPending) return <p role="status">Loading the overview…</p>;
  if (overview.isError) {
    return <p className={styles.formError}>The overview could not be loaded. Reload the page.</p>;
  }
  const o = overview.data;
  const count = (s: TenantStatus) => o.tenants_by_status[s] ?? 0;
  const shown = STATUS_ORDER.filter((s) => count(s) > 0);

  return (
    <section aria-labelledby="overview-title" className={styles.page}>
      <h1 id="overview-title" className={styles.title}>
        Overview
      </h1>

      <div className={adminStyles.hero}>
        <dl className={adminStyles.heroFigure}>
          <dt>Companies</dt>
          <dd>{o.tenants_total}</dd>
          <dd className={adminStyles.heroNote}>
            {o.new_tenants_this_month
              ? `${plural(o.new_tenants_this_month, "new company", "new companies")} this month`
              : "None new this month"}
          </dd>
        </dl>
        <div>
          {o.tenants_total ? (
            <div className={adminStyles.statusBar} aria-hidden="true">
              {shown.map((s) => (
                <span
                  key={s}
                  className={adminStyles.segment}
                  data-tone={STATUS[s].tone}
                  style={{ flexGrow: count(s) }}
                />
              ))}
            </div>
          ) : null}
          <ul className={adminStyles.legend} aria-label="Companies by status">
            {STATUS_ORDER.map((s) => (
              <li key={s}>
                <Link to={`/admin/companies?status=${s}`}>{STATUS[s].label}</Link>{" "}
                <strong>{count(s)}</strong>
              </li>
            ))}
          </ul>
        </div>
      </div>

      <dl className={adminStyles.stats}>
        <div className={adminStyles.stat}>
          <dt>Active users</dt>
          <dd className={adminStyles.statValue}>{o.active_users}</dd>
          <dd className={adminStyles.statNote}>Across every company</dd>
        </div>
        <div className={adminStyles.stat}>
          <dt>Signed in now</dt>
          <dd className={adminStyles.statValue}>{o.open_sessions}</dd>
          <dd className={adminStyles.statNote}>Open sessions</dd>
        </div>
        <div className={adminStyles.stat}>
          <dt>Sign-ins, last 24 hours</dt>
          <dd className={adminStyles.statValue}>{o.sign_ins_24h}</dd>
          <dd className={adminStyles.statNote}>{o.sign_ins_7d} in the last 7 days</dd>
        </div>
        <div
          className={adminStyles.stat}
          data-tone={o.failed_sign_ins_24h > 0 ? "critical" : undefined}
        >
          <dt>Wrong passwords, last 24 hours</dt>
          <dd className={adminStyles.statValue}>{o.failed_sign_ins_24h}</dd>
          <dd className={adminStyles.statNote}>
            {o.failed_sign_ins_7d} in the last 7 days.{" "}
            <Link to="/admin/activity?action=login_failed">See who</Link>
          </dd>
        </div>
      </dl>

      <RevenueSection />

      <div className={styles.tableWrap}>
        <table className={styles.table}>
          <caption className="visually-hidden">Trials ending within 7 days</caption>
          <thead>
            <tr>
              <th scope="col">Trial ends this week</th>
              <th scope="col">Ends</th>
            </tr>
          </thead>
          <tbody>
            {o.trials_ending.length ? (
              o.trials_ending.map((t) => (
                <tr key={t.id}>
                  <td>
                    <Link to={`/admin/companies/${t.id}`}>{t.name}</Link>{" "}
                    <span className={styles.sub}>{t.slug}</span>
                  </td>
                  <td>{formatDateTime(t.trial_ends_at)}</td>
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan={2} className={styles.empty}>
                  No trial ends in the next 7 days.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}
