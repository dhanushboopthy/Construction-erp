import { useState } from "react";
import { Link, useSearchParams } from "react-router";

import { Button } from "@/components/Button";
import { SelectField, TextField } from "@/components/Field";
import styles from "@/components/Ledger.module.css";
import { formatDateTime, formatDay } from "@/lib/format";

import { PAYMENT_PAGE_SIZE, usePayments, useTenants } from "../api";
import adminStyles from "../Admin.module.css";
import { useAdminAuth } from "../AdminAuthContext";
import { Badge } from "../Badge";
import { METHODS, methodLabel, rupees } from "../labels";
import { ReversePaymentDialog } from "../SubscriptionDialogs";
import type { Payment } from "../types";

/** Money Duolink has received for subscriptions. Entries are never edited: a mistake is reversed
 * by a second, negative entry. Support reads; a Super Admin reverses. */
export function PaymentsPage() {
  const { isSuperAdmin } = useAdminAuth();
  const [params, setParams] = useSearchParams();
  const from = params.get("from") ?? "";
  const to = params.get("to") ?? "";
  const method = params.get("method") ?? "";
  const company = params.get("tenant_id") ?? "";
  const page = Math.max(0, Number(params.get("page") ?? 0) || 0);
  const payments = usePayments({
    from,
    to,
    method,
    tenant_id: company ? Number(company) : undefined,
    offset: page * PAYMENT_PAGE_SIZE,
  });
  const companies = useTenants({ sort: "name", limit: 200 });
  const [reversing, setReversing] = useState<Payment | null>(null);

  const setFilter = (key: string, value: string) =>
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        if (value) next.set(key, value);
        else next.delete(key);
        if (key !== "page") next.delete("page");
        return next;
      },
      { replace: true },
    );

  const columns = isSuperAdmin ? 8 : 7;

  return (
    <section aria-labelledby="payments-title" className={styles.page}>
      <div className={styles.toolbar}>
        <h1 id="payments-title" className={styles.title}>
          Payments
        </h1>
      </div>

      <form className={styles.filters} role="search" onSubmit={(e) => e.preventDefault()}>
        <TextField
          label="From"
          type="date"
          value={from}
          onChange={(e) => setFilter("from", e.target.value)}
        />
        <TextField
          label="To"
          type="date"
          value={to}
          onChange={(e) => setFilter("to", e.target.value)}
        />
        <SelectField
          label="Method"
          value={method}
          onChange={(e) => setFilter("method", e.target.value)}
        >
          <option value="">Any method</option>
          {METHODS.map((m) => (
            <option key={m.value} value={m.value}>
              {m.label}
            </option>
          ))}
        </SelectField>
        <SelectField
          label="Company"
          value={company}
          onChange={(e) => setFilter("tenant_id", e.target.value)}
        >
          <option value="">Any company</option>
          {(companies.data?.items ?? []).map((t) => (
            <option key={t.id} value={t.id}>
              {t.name}
            </option>
          ))}
        </SelectField>
      </form>

      {payments.data ? (
        <dl className={adminStyles.stats} aria-label="Totals for these filters">
          <div className={adminStyles.stat}>
            <dt>Received</dt>
            <dd className={adminStyles.statValue}>{rupees(payments.data.totals.received)}</dd>
          </div>
          <div className={adminStyles.stat}>
            <dt>Reversed</dt>
            <dd className={adminStyles.statValue}>{rupees(payments.data.totals.reversed)}</dd>
          </div>
          <div className={adminStyles.stat}>
            <dt>Net</dt>
            <dd className={adminStyles.statValue}>{rupees(payments.data.totals.net)}</dd>
          </div>
        </dl>
      ) : null}

      {reversing ? (
        <ReversePaymentDialog target={reversing} onClose={() => setReversing(null)} />
      ) : null}

      {payments.isPending ? (
        <p role="status">Loading payments…</p>
      ) : payments.isError ? (
        <p role="alert" className={styles.formError}>
          Payments could not be loaded. Reload the page.
        </p>
      ) : (
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <caption className="visually-hidden">Payments</caption>
            <thead>
              <tr>
                <th scope="col">Paid on</th>
                <th scope="col">Company</th>
                <th scope="col">Plan</th>
                <th scope="col" className="num">
                  Amount
                </th>
                <th scope="col">Method</th>
                <th scope="col">Paid for</th>
                <th scope="col">Recorded by</th>
                {isSuperAdmin ? <th scope="col">Actions</th> : null}
              </tr>
            </thead>
            <tbody>
              {payments.data.items.length ? (
                payments.data.items.map((p) => (
                  <tr key={p.id} className={p.reversed ? styles.inactive : ""}>
                    <td>{formatDateTime(p.paid_at)}</td>
                    <td>
                      <Link to={`/admin/companies/${p.tenant_id}?tab=subscription`}>
                        {p.tenant_name}
                      </Link>
                    </td>
                    <td>{p.plan_name}</td>
                    <td className="num">
                      {rupees(p.amount)}
                      {p.reverses_id !== null ? (
                        <div>
                          <Badge tone="warn">Reversal</Badge>
                        </div>
                      ) : p.reversed ? (
                        <div>
                          <Badge tone="neutral">Reversed</Badge>
                        </div>
                      ) : null}
                    </td>
                    <td>
                      {methodLabel(p.method)}
                      {p.reference ? <div className={styles.sub}>{p.reference}</div> : null}
                    </td>
                    <td>
                      {p.period_starts_at && p.period_ends_at
                        ? `${formatDay(p.period_starts_at)} to ${formatDay(p.period_ends_at)}`
                        : "—"}
                    </td>
                    <td>{p.recorded_by}</td>
                    {isSuperAdmin ? (
                      <td>
                        {p.reverses_id === null && !p.reversed ? (
                          <Button
                            aria-label={`Reverse payment from ${p.tenant_name}`}
                            onClick={() => setReversing(p)}
                          >
                            Reverse…
                          </Button>
                        ) : null}
                      </td>
                    ) : null}
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={columns} className={styles.empty}>
                    {params.toString()
                      ? "No payment matches. Clear the filters."
                      : "No payments recorded yet."}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
          <p className={styles.results}>
            {payments.data.total} {payments.data.total === 1 ? "entry" : "entries"}
          </p>
          {payments.data.total > PAYMENT_PAGE_SIZE ? (
            <nav aria-label="Pages" className={styles.actions}>
              <Button disabled={page === 0} onClick={() => setFilter("page", String(page - 1))}>
                Previous
              </Button>
              <Button
                disabled={(page + 1) * PAYMENT_PAGE_SIZE >= payments.data.total}
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
