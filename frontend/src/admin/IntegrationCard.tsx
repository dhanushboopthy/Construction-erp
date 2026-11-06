import { useState } from "react";

import { toFormError } from "@/api/errors";
import { Button } from "@/components/Button";
import styles from "@/components/Ledger.module.css";
import { formatDateTime } from "@/lib/format";

import {
  useCompanyUsage,
  useDisconnectIntegration,
  useIntegrationFailures,
  useTestIntegration,
} from "./api";
import adminStyles from "./Admin.module.css";
import { Badge } from "./Badge";
import { ConnectionForm } from "./ConnectionForm";
import { INTEGRATION, INTEGRATION_STATUS, OUTCOME_LABEL, PROVIDER, SOURCE } from "./labels";
import { LimitsForm } from "./LimitsForm";
import type { Integration, IntegrationTest, IntegrationUsage } from "./types";

type Panel = "connect" | "limits" | "disconnect" | null;

/** One integration: its status, the connection (write-only keys), usage and the companies using
 * it. Support sees the status only; a Super Admin changes things and sees usage. */
export function IntegrationCard({
  integration,
  usage,
  canEdit,
}: {
  integration: Integration;
  usage: IntegrationUsage | undefined;
  canEdit: boolean;
}) {
  const kind = integration.kind;
  const [panel, setPanel] = useState<Panel>(null);
  const [tested, setTested] = useState<IntegrationTest | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const test = useTestIntegration(kind);
  const disconnect = useDisconnectIntegration(kind);
  const companies = useCompanyUsage(kind, canEdit);
  const failures = useIntegrationFailures(kind, canEdit);
  const text = INTEGRATION[kind];
  const status = INTEGRATION_STATUS[integration.status];
  const titleId = `integration-${kind}`;

  async function runTest() {
    setProblem(null);
    setTested(null);
    try {
      setTested(await test.mutateAsync());
    } catch (err) {
      setProblem(toFormError(err).message);
    }
  }

  async function runDisconnect() {
    setProblem(null);
    try {
      await disconnect.mutateAsync();
      setPanel(null);
    } catch (err) {
      setProblem(toFormError(err).message);
    }
  }

  const tiles: { label: string; value: number | undefined; tone?: string }[] = usage
    ? [
        { label: "Calls today", value: usage.today.total },
        { label: "This week", value: usage.week.total },
        { label: "This month", value: usage.month.total },
        { label: OUTCOME_LABEL.cached + " (month)", value: usage.month.cached },
        { label: OUTCOME_LABEL.failed + " (month)", value: usage.month.failed, tone: "critical" },
        { label: OUTCOME_LABEL.blocked + " (month)", value: usage.month.blocked, tone: "warn" },
      ]
    : [];

  return (
    <article className={styles.sheet} aria-labelledby={titleId}>
      <div className={adminStyles.heading}>
        <div>
          <h2 id={titleId}>{text.title}</h2>
          <p className={styles.note}>{text.about}</p>
        </div>
        <Badge tone={status.tone}>{status.label}</Badge>
      </div>

      <dl className={adminStyles.facts}>
        <div>
          <dt>In force</dt>
          <dd>{SOURCE[integration.source]}</dd>
        </div>
        <div>
          <dt>Provider</dt>
          <dd>
            {integration.provider
              ? PROVIDER[integration.provider]
              : integration.effective_provider
                ? PROVIDER[integration.effective_provider]
                : "None"}
          </dd>
        </div>
        {integration.base_url ? (
          <div>
            <dt>Address</dt>
            <dd>{integration.base_url}</dd>
          </div>
        ) : null}
        {integration.key_last4 ? (
          <div>
            <dt>Key</dt>
            <dd>
              <span aria-hidden="true">••••</span>
              <span className="visually-hidden">Ends in </span>
              {integration.key_last4}
            </dd>
          </div>
        ) : null}
        <div>
          <dt>Last success</dt>
          <dd>{integration.last_success_at ? formatDateTime(integration.last_success_at) : "—"}</dd>
        </div>
        <div>
          <dt>Last failure</dt>
          <dd>
            {integration.last_failure_at ? formatDateTime(integration.last_failure_at) : "—"}
            {integration.last_failure_message ? (
              <span className={adminStyles.statNote}> {integration.last_failure_message}</span>
            ) : null}
          </dd>
        </div>
        <div>
          <dt>Limits per company</dt>
          <dd>
            {integration.daily_limit} a day, {integration.monthly_limit} a month, warn at{" "}
            {integration.warn_at_percent}%
            {kind === "gstin_lookup" ? `, keep answers ${integration.cache_hours} h` : ""}
          </dd>
        </div>
      </dl>

      {!integration.secret_key_set && canEdit ? (
        <p role="note" className={styles.callout}>
          INTEGRATION_SECRET_KEY is not set on the server, so provider keys cannot be saved yet.
        </p>
      ) : null}

      {canEdit ? (
        <div className={adminStyles.rowActions}>
          <Button variant="primary" onClick={() => setPanel("connect")}>
            {integration.provider ? "Edit connection" : "Connect"}
          </Button>
          <Button onClick={() => void runTest()} disabled={test.isPending}>
            {test.isPending ? "Testing…" : "Test connection"}
          </Button>
          <Button onClick={() => setPanel("limits")}>Limits</Button>
          {integration.provider ? (
            <Button onClick={() => setPanel("disconnect")}>Disconnect</Button>
          ) : null}
        </div>
      ) : null}

      {tested ? (
        <p
          role="status"
          className={tested.ok ? styles.saved : styles.formError}
          data-testid={`${kind}-test`}
        >
          {tested.ok
            ? `Connection works (${tested.latency_ms ?? 0} ms).`
            : `Connection failed: ${tested.message ?? tested.error_code ?? "unknown error"}`}
        </p>
      ) : null}
      {problem ? (
        <p role="alert" className={styles.formError}>
          {problem}
        </p>
      ) : null}

      {panel === "connect" ? (
        <ConnectionForm integration={integration} onClose={() => setPanel(null)} />
      ) : null}
      {panel === "limits" ? (
        <LimitsForm integration={integration} onClose={() => setPanel(null)} />
      ) : null}
      {panel === "disconnect" ? (
        <div className={adminStyles.confirm} role="group" aria-label="Confirm disconnect">
          <p>
            Forget the saved keys for {text.title}? The server&apos;s environment settings are used
            again. This does not delete any bill.
          </p>
          <div className={adminStyles.rowActions}>
            <Button
              variant="primary"
              className={adminStyles.danger}
              onClick={() => void runDisconnect()}
              disabled={disconnect.isPending}
            >
              Disconnect
            </Button>
            <Button onClick={() => setPanel(null)}>Keep it</Button>
          </div>
        </div>
      ) : null}

      {canEdit ? (
        <>
          <dl className={adminStyles.stats} aria-label={`${text.title} usage`}>
            {tiles.map((t) => (
              <div
                key={t.label}
                className={adminStyles.stat}
                data-tone={t.value ? t.tone : undefined}
              >
                <dt>{t.label}</dt>
                <dd className={adminStyles.statValue}>{t.value ?? "—"}</dd>
              </div>
            ))}
          </dl>

          <h3>Companies this month</h3>
          {companies.data && companies.data.length > 0 ? (
            <div className={styles.tableWrap}>
              <table className={styles.table}>
                <caption className="visually-hidden">{text.title}: calls per company</caption>
                <thead>
                  <tr>
                    <th scope="col">Company</th>
                    <th scope="col" className={styles.amount}>
                      Today
                    </th>
                    <th scope="col" className={styles.amount}>
                      Month
                    </th>
                    <th scope="col" className={styles.amount}>
                      Cached
                    </th>
                    <th scope="col" className={styles.amount}>
                      Failed
                    </th>
                    <th scope="col" className={styles.amount}>
                      Blocked
                    </th>
                    <th scope="col">Limit</th>
                  </tr>
                </thead>
                <tbody>
                  {companies.data.map((c) => (
                    <tr key={c.tenant_id}>
                      <th scope="row">{c.name}</th>
                      <td className={styles.amount}>{c.calls_today}</td>
                      <td className={styles.amount}>{c.calls_month}</td>
                      <td className={styles.amount}>{c.cached_month}</td>
                      <td className={styles.amount}>{c.failed_month}</td>
                      <td className={styles.amount}>{c.blocked_month}</td>
                      <td>
                        {c.over_limit ? (
                          <Badge tone="critical">Over</Badge>
                        ) : c.near_limit ? (
                          <Badge tone="warn">Near</Badge>
                        ) : (
                          <Badge tone="good">Within</Badge>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className={styles.empty}>No company has used it this month.</p>
          )}

          <h3>Recent failures</h3>
          {failures.data && failures.data.length > 0 ? (
            <ul className={styles.errorList}>
              {failures.data.map((f) => (
                <li key={f.id}>
                  {formatDateTime(f.at)} · {f.tenant_name ?? "Duolink"} · {f.operation} ·{" "}
                  {f.error_code ?? "error"}
                </li>
              ))}
            </ul>
          ) : (
            <p className={styles.empty}>No failed calls.</p>
          )}
        </>
      ) : null}
    </article>
  );
}
