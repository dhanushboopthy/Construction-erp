import { useState } from "react";

import { Button } from "@/components/Button";
import { TextField } from "@/components/Field";
import styles from "@/components/Ledger.module.css";
import { formatDateTime } from "@/lib/format";

import { useAdminAuth } from "../AdminAuthContext";
import { useMaintenance, useSetMaintenance, useSystemHealth } from "../api";
import adminStyles from "../Admin.module.css";
import { Badge } from "../Badge";
import { formatBytes, formatUptime, type Tone } from "../labels";
import type { Maintenance } from "../types";

const CHECK_TONE: Record<string, Tone> = { ok: "good", warn: "warn", fail: "critical" };
const CHECK_WORD: Record<string, string> = { ok: "Fine", warn: "Check", fail: "Failing" };

function State({ state }: { state: string }) {
  return <Badge tone={CHECK_TONE[state] ?? "neutral"}>{CHECK_WORD[state] ?? state}</Badge>;
}

/**
 * Maintenance mode. Turning it on closes the ERP to every company (they see "Back soon" with
 * this message) while the admin and the health checks keep working. Super Admin only.
 */
function MaintenanceCard({ maintenance }: { maintenance: Maintenance }) {
  const { isSuperAdmin } = useAdminAuth();
  const set = useSetMaintenance();
  const [message, setMessage] = useState(maintenance.operator_message ?? "");
  const [confirming, setConfirming] = useState(false);
  const on = maintenance.operator_enabled;

  return (
    <section className={adminStyles.healthCard} aria-labelledby="maintenance-title">
      <h2 id="maintenance-title">Maintenance mode</h2>
      <p>
        {on ? (
          <Badge tone="warn">On: companies cannot use the ERP</Badge>
        ) : (
          <Badge tone="good">Off: companies are working</Badge>
        )}
      </p>
      {maintenance.restoring && (
        <p role="status">A restore is under way, so companies are closed out until it finishes.</p>
      )}
      {on && (
        <p className={adminStyles.maintenanceOn}>
          Companies see: <strong>{maintenance.operator_message ?? "the standard message"}</strong>
          {maintenance.enabled_at && <> (since {formatDateTime(maintenance.enabled_at)})</>}
          {maintenance.changed_by && <>, set by {maintenance.changed_by}</>}.
        </p>
      )}
      {isSuperAdmin ? (
        <>
          {!on && (
            <TextField
              label="Message for companies (optional)"
              hint="For example: Back at 9 pm."
              value={message}
              maxLength={300}
              onChange={(e) => setMessage(e.target.value)}
            />
          )}
          {confirming ? (
            <div className={adminStyles.confirm} role="alertdialog" aria-label="Confirm">
              <p>
                {on
                  ? "Open the ERP to companies again?"
                  : "Close the ERP to every company now? Anyone mid-bill will be turned away."}
              </p>
              <div className={styles.actions}>
                <Button
                  variant="primary"
                  autoFocus
                  disabled={set.isPending}
                  onClick={() =>
                    set.mutate(
                      { enabled: !on, message: on ? null : message || null },
                      { onSuccess: () => setConfirming(false) },
                    )
                  }
                >
                  {on ? "Turn maintenance off" : "Turn maintenance on"}
                </Button>
                <Button variant="ghost" onClick={() => setConfirming(false)}>
                  Cancel
                </Button>
              </div>
            </div>
          ) : (
            <div className={styles.actions}>
              <Button variant={on ? "primary" : "secondary"} onClick={() => setConfirming(true)}>
                {on ? "Turn maintenance off" : "Turn maintenance on"}
              </Button>
            </div>
          )}
          {set.isError && (
            <p role="alert" className={styles.formError}>
              {set.error.message}
            </p>
          )}
        </>
      ) : (
        <p className={styles.note}>Only a Super Admin can switch maintenance mode.</p>
      )}
    </section>
  );
}

/** System health: the API, the database, the disks, the backups and counters across companies. */
export function SystemPage() {
  const health = useSystemHealth();
  const maintenance = useMaintenance();

  return (
    <section aria-labelledby="system-title" className={styles.page}>
      <h1 id="system-title" className={styles.title}>
        System health
      </h1>
      {health.isPending && <p role="status">Loading system health…</p>}
      {health.isError && (
        <p role="alert" className={styles.formError}>
          System health could not be loaded.
        </p>
      )}
      {health.data && (
        <div className={adminStyles.healthGrid}>
          <section className={adminStyles.healthCard} aria-labelledby="api-title">
            <h2 id="api-title">API</h2>
            <dl className={adminStyles.facts}>
              <dt>Up for</dt>
              <dd>{formatUptime(health.data.api.uptime_seconds)}</dd>
              <dt>Version</dt>
              <dd>
                {health.data.api.version}
                {health.data.api.changelog_version &&
                  health.data.api.changelog_version !== health.data.api.version &&
                  ` (release ${health.data.api.changelog_version})`}
              </dd>
              <dt>Python</dt>
              <dd>{health.data.api.python_version}</dd>
              <dt>Environment</dt>
              <dd>{health.data.api.environment}</dd>
            </dl>
          </section>

          <section className={adminStyles.healthCard} aria-labelledby="db-title">
            <h2 id="db-title">Database</h2>
            <p>
              <Badge tone={health.data.database.up ? "good" : "critical"}>
                {health.data.database.up ? "Up" : "Down"}
              </Badge>{" "}
              <State state={health.data.database.migrations.state} />
            </p>
            <dl className={adminStyles.facts}>
              <dt>Round trip</dt>
              <dd>{health.data.database.round_trip_ms} ms</dd>
              <dt>Size</dt>
              <dd>{formatBytes(health.data.database.size_bytes)}</dd>
              <dt>Connections in use</dt>
              <dd>{health.data.database.connections_in_use}</dd>
              <dt>Server</dt>
              <dd>PostgreSQL {health.data.database.server_version}</dd>
              <dt>Version of the data</dt>
              <dd>{health.data.database.migrations.detail}</dd>
            </dl>
          </section>

          <section className={adminStyles.healthCard} aria-labelledby="disk-title">
            <h2 id="disk-title">Disk space</h2>
            <dl className={adminStyles.facts}>
              {health.data.disks.map((d) => (
                <div key={d.name} style={{ display: "contents" }}>
                  <dt>{d.name === "backups" ? "Backups" : "Files"}</dt>
                  <dd>
                    {d.watched ? (
                      <>
                        {formatBytes(d.free_bytes)} free of {formatBytes(d.total_bytes)} (
                        {d.free_percent}%){" "}
                        <Badge tone={d.low ? "critical" : "good"}>{d.low ? "Low" : "Fine"}</Badge>
                      </>
                    ) : (
                      "Not watched here"
                    )}
                  </dd>
                </div>
              ))}
            </dl>
          </section>

          <section className={adminStyles.healthCard} aria-labelledby="backup-title">
            <h2 id="backup-title">Backups</h2>
            <p>
              <State state={health.data.backup.check.state} />
            </p>
            <dl className={adminStyles.facts}>
              <dt>Last success</dt>
              <dd>
                {health.data.backup.last_success_at
                  ? `${formatDateTime(health.data.backup.last_success_at)} (${health.data.backup.age_hours} h ago)`
                  : "None recorded"}
              </dd>
              <dt>Copied off-site</dt>
              <dd>
                {health.data.backup.offsite_synced_at
                  ? formatDateTime(health.data.backup.offsite_synced_at)
                  : "Not known"}
              </dd>
            </dl>
            <p className={styles.note}>{health.data.backup.check.detail}</p>
          </section>

          <section className={adminStyles.healthCard} aria-labelledby="counters-title">
            <h2 id="counters-title">Across every company</h2>
            <dl className={adminStyles.facts}>
              <dt>Companies</dt>
              <dd>{health.data.counters.companies}</dd>
              <dt>Active users</dt>
              <dd>{health.data.counters.active_users}</dd>
              <dt>Open sessions</dt>
              <dd>{health.data.counters.open_sessions}</dd>
              <dt>Audit events today</dt>
              <dd>{health.data.counters.audit_events_today}</dd>
              <dt>Admin actions today</dt>
              <dd>{health.data.counters.admin_actions_today}</dd>
              <dt>Open tickets</dt>
              <dd>{health.data.counters.open_tickets}</dd>
            </dl>
          </section>

          <section className={adminStyles.healthCard} aria-labelledby="gsp-title">
            <h2 id="gsp-title">E-way bill provider</h2>
            <p>
              <State state={health.data.gsp.state} />
            </p>
            <p className={styles.note}>{health.data.gsp.detail}</p>
          </section>
        </div>
      )}
      {maintenance.data && (
        <MaintenanceCard key={maintenance.dataUpdatedAt} maintenance={maintenance.data} />
      )}
    </section>
  );
}
