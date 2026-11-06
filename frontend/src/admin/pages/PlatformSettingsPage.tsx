import { Link } from "react-router";

import styles from "@/components/Ledger.module.css";

import { usePlatformSettings } from "../api";
import adminStyles from "../Admin.module.css";
import { Badge } from "../Badge";

function yesNo(value: boolean) {
  return value ? "Yes" : "No";
}

/** Platform settings (Milestone 24): read-only. How the platform is configured and how a plan's
 * life works, in plain words, with a link to each control. Never a secret. */
export function PlatformSettingsPage() {
  const settings = usePlatformSettings();
  if (settings.isPending) return <p role="status">Loading settings…</p>;
  if (settings.isError) {
    return (
      <p role="alert" className={styles.formError}>
        Platform settings could not be loaded.
      </p>
    );
  }
  const { security: s, lifecycle: l } = settings.data;

  return (
    <section aria-labelledby="settings-title" className={styles.page}>
      <h1 id="settings-title" className={styles.title}>
        Platform settings
      </h1>
      <p className={styles.note}>
        Read-only. These come from the server&apos;s environment and are changed there, never here.
      </p>

      <div className={adminStyles.healthGrid}>
        <section className={adminStyles.healthCard} aria-labelledby="security-title">
          <h2 id="security-title">Security</h2>
          <dl className={adminStyles.facts}>
            <dt>Environment</dt>
            <dd>{s.environment}</dd>
            <dt>Company addresses</dt>
            <dd>
              &lt;company&gt;.{s.base_domain}; admin at {s.admin_subdomain}.{s.base_domain}
            </dd>
            <dt>Secure cookies</dt>
            <dd>
              <Badge tone={s.cookie_secure ? "good" : "warn"}>{yesNo(s.cookie_secure)}</Badge>
            </dd>
            <dt>Row-level security role</dt>
            <dd>
              <Badge tone={s.row_level_security_role_set ? "good" : "critical"}>
                {yesNo(s.row_level_security_role_set)}
              </Badge>
            </dd>
            <dt>Sign-in window</dt>
            <dd>
              Access {s.access_token_minutes} min, session {s.refresh_token_hours} h
            </dd>
            <dt>Lock after</dt>
            <dd>
              {s.login_max_attempts} wrong passwords for {s.login_lock_minutes} min
            </dd>
            <dt>API docs open</dt>
            <dd>{yesNo(s.api_docs_enabled)}</dd>
            <dt>File storage</dt>
            <dd>{s.storage_provider}</dd>
            <dt>E-way bill provider</dt>
            <dd>{s.gsp_provider}</dd>
            <dt>Backups watched</dt>
            <dd>{yesNo(s.backups_watched)}</dd>
            <dt>Largest upload</dt>
            <dd>{s.max_upload_mb} MB</dd>
          </dl>
        </section>

        <section className={adminStyles.healthCard} aria-labelledby="lifecycle-title">
          <h2 id="lifecycle-title">How a company&apos;s plan runs</h2>
          <ol>
            <li>
              A new company starts a <strong>{l.trial_days}-day trial</strong> (longest{" "}
              {l.max_trial_days} days).
            </li>
            <li>
              From {l.banner_days} days before the end the company sees a banner, and Duolink&apos;s
              bell warns {l.notice_days} days ahead.
            </li>
            <li>
              When the date passes, the company becomes <strong>read-only</strong>: it can read and
              export its books, raise tickets and sign in, but cannot save.
            </li>
            <li>
              Recording a renewal lifts that at once, with no sign-out. Suspending or closing a
              company blocks it completely.
            </li>
          </ol>
          <p className={styles.note}>
            The bell also rings for a backup older than {l.backup_stale_hours} hours, a disk under{" "}
            {l.disk_low_free_percent}% free, and more than {l.failed_admin_sign_ins_limit} failed
            admin sign-ins in a day. Maintenance mode is read again every{" "}
            {l.maintenance_cache_seconds} seconds.
          </p>
        </section>

        <section className={adminStyles.healthCard} aria-labelledby="controls-title">
          <h2 id="controls-title">Where to change things</h2>
          <ul>
            <li>
              <Link to="/admin/plans">Plans and prices</Link>
            </li>
            <li>
              <Link to="/admin/subscriptions">Subscriptions and renewals</Link>
            </li>
            <li>
              <Link to="/admin/system">Maintenance mode and system health</Link>
            </li>
            <li>
              <Link to="/admin/staff">Duolink staff and roles</Link>
            </li>
            <li>
              <Link to="/admin/audit">The audit log</Link>
            </li>
          </ul>
        </section>
      </div>
    </section>
  );
}
