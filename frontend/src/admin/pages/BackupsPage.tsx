import { useRef, useState } from "react";

import { Button } from "@/components/Button";
import { SelectField, TextField } from "@/components/Field";
import styles from "@/components/Ledger.module.css";
import { formatDateTime } from "@/lib/format";

import { useAdminAuth } from "../AdminAuthContext";
import {
  downloadBackup,
  useBackupJob,
  useBackups,
  useBackupSchedule,
  useBackupSummary,
  useCreateBackup,
  useDeleteBackup,
  useRestoreBackup,
  useSetBackupSchedule,
  useTenants,
  useUploadBackup,
} from "../api";
import adminStyles from "../Admin.module.css";
import { Badge } from "../Badge";
import { formatBytes, type Tone } from "../labels";
import type { Backup } from "../types";

const STATUS_TONE: Record<string, Tone> = {
  verified: "good",
  running: "accent",
  failed: "critical",
};
const STATUS_WORD: Record<string, string> = {
  verified: "Verified",
  running: "Running",
  failed: "Failed",
};
const SOURCE_WORD: Record<string, string> = {
  scheduled: "Nightly",
  manual: "Manual",
  safety: "Safety copy",
  uploaded: "Uploaded",
};

/** The job a button started: its step, and how it ended. Polled until it is over. */
function JobStatus({ id }: { id: number }) {
  const job = useBackupJob(id);
  if (!job.data) return <p role="status">Starting…</p>;
  const { status, step, error_message: error } = job.data;
  if (status === "failed")
    return (
      <p role="alert" className={styles.formError}>
        Failed{step ? ` at "${step}"` : ""}: {error}
      </p>
    );
  if (status === "succeeded") return <p role="status">Done.</p>;
  return <p role="status">{step ?? "Waiting"}…</p>;
}

function Tiles() {
  const summary = useBackupSummary();
  const s = summary.data;
  if (!s) return <p role="status">Loading…</p>;
  return (
    <>
      <div className={adminStyles.healthGrid} aria-label="Backup summary">
        <section className={adminStyles.healthCard} aria-labelledby="tile-last">
          <h2 id="tile-last">Last backup</h2>
          <p>{s.last_backup_at ? formatDateTime(s.last_backup_at) : "None yet"}</p>
        </section>
        <section className={adminStyles.healthCard} aria-labelledby="tile-verified">
          <h2 id="tile-verified">Verified</h2>
          <p>
            {s.verified_count} verified
            {s.failed_count > 0 ? `, ${s.failed_count} failed` : ""}
          </p>
        </section>
        <section className={adminStyles.healthCard} aria-labelledby="tile-storage">
          <h2 id="tile-storage">Storage used</h2>
          <p>{formatBytes(s.storage_bytes)}</p>
        </section>
        <section className={adminStyles.healthCard} aria-labelledby="tile-next">
          <h2 id="tile-next">Next scheduled</h2>
          <p>{formatDateTime(s.next_scheduled_at)}</p>
        </section>
      </div>
      {!s.folder_ready && (
        <p role="alert" className={styles.formError}>
          {s.folder_problem}
        </p>
      )}
      {s.tools.some((t) => !t.found) && (
        <p role="alert" className={styles.formError}>
          These tools are missing on the server, so backups cannot be made:{" "}
          {s.tools
            .filter((t) => !t.found)
            .map((t) => t.name)
            .join(", ")}
          .
        </p>
      )}
    </>
  );
}

function CreateBar() {
  const create = useCreateBackup();
  const companies = useTenants({ limit: 200 });
  const [company, setCompany] = useState("");
  const [jobId, setJobId] = useState<number | null>(null);
  const start = (body: { kind: "platform" | "company"; company_id?: number }) =>
    create.mutate(body, { onSuccess: (job) => setJobId(job.id) });
  return (
    <section aria-labelledby="create-title" className={adminStyles.healthCard}>
      <h2 id="create-title">Make a backup</h2>
      <div className={styles.actions}>
        <Button
          variant="primary"
          disabled={create.isPending}
          onClick={() => start({ kind: "platform" })}
        >
          Back up all companies
        </Button>
        <SelectField label="Company" value={company} onChange={(e) => setCompany(e.target.value)}>
          <option value="">Choose a company</option>
          {companies.data?.items.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </SelectField>
        <Button
          disabled={create.isPending || !company}
          onClick={() => start({ kind: "company", company_id: Number(company) })}
        >
          Back up one company
        </Button>
      </div>
      {create.isError && (
        <p role="alert" className={styles.formError}>
          {create.error.message}
        </p>
      )}
      {jobId !== null && <JobStatus id={jobId} />}
    </section>
  );
}

function UploadCard() {
  const upload = useUploadBackup();
  const input = useRef<HTMLInputElement>(null);
  return (
    <section aria-labelledby="upload-title" className={adminStyles.healthCard}>
      <h2 id="upload-title">Upload a company backup</h2>
      <p className={styles.note}>
        A .tar.gz made here, up to 200 MB. It is checked against the company and the database
        version before it is kept, and restored from the list below.
      </p>
      <input
        ref={input}
        type="file"
        accept=".gz,.tar.gz,application/gzip"
        aria-label="Company backup file"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) upload.mutate(file);
          if (input.current) input.current.value = "";
        }}
      />
      {upload.isError && (
        <p role="alert" className={styles.formError}>
          {upload.error.message}
        </p>
      )}
      {upload.isSuccess && <p role="status">Uploaded and checked.</p>}
    </section>
  );
}

function ScheduleCard() {
  const { isSuperAdmin } = useAdminAuth();
  const schedule = useBackupSchedule();
  const save = useSetBackupSchedule();
  const [draft, setDraft] = useState<Record<string, string> | null>(null);
  const s = schedule.data;
  if (!s) return null;
  const value = (key: "daily_time" | "keep_daily" | "keep_weekly" | "keep_monthly") =>
    draft?.[key] ?? String(s[key]);
  const edit = (key: string, v: string) => setDraft({ ...(draft ?? {}), [key]: v });
  return (
    <section aria-labelledby="schedule-title" className={adminStyles.healthCard}>
      <h2 id="schedule-title">Nightly schedule</h2>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate(
            {
              daily_time: value("daily_time"),
              keep_daily: Number(value("keep_daily")),
              keep_weekly: Number(value("keep_weekly")),
              keep_monthly: Number(value("keep_monthly")),
            },
            { onSuccess: () => setDraft(null) },
          );
        }}
      >
        <TextField
          label="Time of day (shop time, HH:MM)"
          value={value("daily_time")}
          disabled={!isSuperAdmin}
          onChange={(e) => edit("daily_time", e.target.value)}
        />
        <TextField
          label="Daily copies to keep"
          inputMode="numeric"
          value={value("keep_daily")}
          disabled={!isSuperAdmin}
          onChange={(e) => edit("keep_daily", e.target.value)}
        />
        <TextField
          label="Weekly copies to keep"
          inputMode="numeric"
          value={value("keep_weekly")}
          disabled={!isSuperAdmin}
          onChange={(e) => edit("keep_weekly", e.target.value)}
        />
        <TextField
          label="Monthly copies to keep"
          inputMode="numeric"
          value={value("keep_monthly")}
          disabled={!isSuperAdmin}
          onChange={(e) => edit("keep_monthly", e.target.value)}
        />
        <p className={styles.note}>
          Pruning only removes nightly copies. Manual, safety and uploaded backups stay.
        </p>
        {isSuperAdmin ? (
          <Button type="submit" variant="primary" disabled={save.isPending || draft === null}>
            Save schedule
          </Button>
        ) : (
          <p className={styles.note}>Only a Super Admin can change the schedule.</p>
        )}
        {save.isError && (
          <p role="alert" className={styles.formError}>
            {save.error.message}
          </p>
        )}
      </form>
    </section>
  );
}

/** Restore one company from one archive: names the target and the backup's date, asks for
 * RESTORE, and polls the job. The numbers shown are read when the dialog opens. */
function RestoreDialog({ backup, onClose }: { backup: Backup; onClose: () => void }) {
  const restore = useRestoreBackup(backup.id);
  const [typed, setTyped] = useState("");
  const [jobId, setJobId] = useState<number | null>(null);
  const company = backup.company;
  if (!company) return null;
  return (
    <div className={adminStyles.confirm} role="alertdialog" aria-label="Restore a company">
      <p>
        Replace all of <strong>{company.name}</strong>&apos;s data with the backup made on{" "}
        <strong>{formatDateTime(backup.started_at)}</strong>? A protected safety copy of
        today&apos;s data is taken first. {company.name} is closed while this runs, everyone there
        signs in again, and any failure leaves the company exactly as it is now.
      </p>
      <TextField
        label="Type RESTORE to continue"
        value={typed}
        autoFocus
        onChange={(e) => setTyped(e.target.value)}
      />
      <div className={styles.actions}>
        <Button
          variant="primary"
          className={adminStyles.danger}
          disabled={restore.isPending || jobId !== null}
          onClick={() =>
            restore.mutate(
              { company_id: company.id, confirm: typed },
              { onSuccess: (job) => setJobId(job.id) },
            )
          }
        >
          Restore {company.name}
        </Button>
        <Button variant="ghost" onClick={onClose}>
          Close
        </Button>
      </div>
      {restore.isError && (
        <p role="alert" className={styles.formError}>
          {restore.error.message}
        </p>
      )}
      {jobId !== null && <JobStatus id={jobId} />}
    </div>
  );
}

function DeleteDialog({ backup, onClose }: { backup: Backup; onClose: () => void }) {
  const del = useDeleteBackup(backup.id);
  const [typed, setTyped] = useState("");
  return (
    <div className={adminStyles.confirm} role="alertdialog" aria-label="Delete a backup">
      <p>
        Delete <strong>{backup.file_name}</strong>? The file is removed from the server.
      </p>
      <TextField
        label="Type DELETE to continue"
        value={typed}
        autoFocus
        onChange={(e) => setTyped(e.target.value)}
      />
      <div className={styles.actions}>
        <Button
          variant="primary"
          className={adminStyles.danger}
          disabled={del.isPending}
          onClick={() => del.mutate(typed, { onSuccess: onClose })}
        >
          Delete backup
        </Button>
        <Button variant="ghost" onClick={onClose}>
          Cancel
        </Button>
      </div>
      {del.isError && (
        <p role="alert" className={styles.formError}>
          {del.error.message}
        </p>
      )}
    </div>
  );
}

function BackupRow({ backup }: { backup: Backup }) {
  const { isSuperAdmin } = useAdminAuth();
  const [panel, setPanel] = useState<"restore" | "delete" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const download = (part: "dump" | "files") => {
    setError(null);
    downloadBackup(backup, part).catch((e: Error) => setError(e.message));
  };
  return (
    <>
      <tr>
        <td>{formatDateTime(backup.started_at)}</td>
        <td>
          {backup.kind === "platform" ? "All companies" : (backup.company?.name ?? "A company")}
        </td>
        <td>
          {SOURCE_WORD[backup.source]}
          {backup.protected && " (protected)"}
        </td>
        <td>
          <Badge tone={STATUS_TONE[backup.status] ?? "neutral"}>
            {STATUS_WORD[backup.status] ?? backup.status}
          </Badge>
          {!backup.file_present && backup.status === "verified" && " (file missing)"}
        </td>
        <td style={{ fontVariantNumeric: "tabular-nums" }}>{formatBytes(backup.size_bytes)}</td>
        <td>
          {isSuperAdmin && backup.status === "verified" && (
            <div className={styles.actions}>
              <Button variant="ghost" onClick={() => download("dump")}>
                Download
              </Button>
              {backup.files_name && (
                <Button variant="ghost" onClick={() => download("files")}>
                  Download files
                </Button>
              )}
              {backup.kind === "company" && (
                <Button variant="ghost" onClick={() => setPanel("restore")}>
                  Restore
                </Button>
              )}
              {!backup.protected && (
                <Button variant="ghost" onClick={() => setPanel("delete")}>
                  Delete
                </Button>
              )}
            </div>
          )}
          {error && (
            <p role="alert" className={styles.formError}>
              {error}
            </p>
          )}
          {backup.error && <span className={styles.note}>{backup.error}</span>}
        </td>
      </tr>
      {(backup.restore_command || panel) && (
        <tr>
          <td colSpan={6}>
            {backup.restore_command && panel === null && isSuperAdmin && (
              <details>
                <summary>How to restore the whole platform</summary>
                <p className={styles.note}>
                  Run this on the server, not from here. It replaces ALL data and asks for RESTORE:
                </p>
                <pre>
                  <code>{backup.restore_command}</code>
                </pre>
              </details>
            )}
            {panel === "restore" && (
              <RestoreDialog backup={backup} onClose={() => setPanel(null)} />
            )}
            {panel === "delete" && <DeleteDialog backup={backup} onClose={() => setPanel(null)} />}
          </td>
        </tr>
      )}
    </>
  );
}

/**
 * Backup and recovery (Milestone 25). Every admin sees the list and the status; only a Super
 * Admin makes, downloads, uploads, restores or deletes. A whole-platform restore is a command
 * on the server, shown beside the backup and never run from this page.
 */
export function BackupsPage() {
  const { isSuperAdmin } = useAdminAuth();
  const backups = useBackups();
  return (
    <section aria-labelledby="backups-title" className={styles.page}>
      <h1 id="backups-title" className={styles.title}>
        Backups
      </h1>
      <Tiles />
      {isSuperAdmin && (
        <div className={adminStyles.twoColumns}>
          <CreateBar />
          <UploadCard />
        </div>
      )}
      <ScheduleCard />
      {backups.isPending && <p role="status">Loading backups…</p>}
      {backups.isError && (
        <p role="alert" className={styles.formError}>
          Backups could not be loaded.
        </p>
      )}
      {backups.data && (
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <caption className="visually-hidden">Backups, newest first</caption>
            <thead>
              <tr>
                <th scope="col">Made</th>
                <th scope="col">Covers</th>
                <th scope="col">Kind</th>
                <th scope="col">Status</th>
                <th scope="col">Size</th>
                <th scope="col">Actions</th>
              </tr>
            </thead>
            <tbody>
              {backups.data.items.map((b) => (
                <BackupRow key={b.id} backup={b} />
              ))}
              {backups.data.items.length === 0 && (
                <tr>
                  <td colSpan={6}>No backups yet.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
