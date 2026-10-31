import { useEffect, useRef, useState, type FormEvent } from "react";

import { toFormError, type FormError } from "@/api/errors";
import { Button } from "@/components/Button";
import { SelectField, TextField } from "@/components/Field";
import styles from "@/components/Ledger.module.css";
import { moveRowFocus } from "@/hooks/useKeys";
import { formatDateTime } from "@/lib/format";

import {
  useCreateStaff,
  useResetStaffPassword,
  useStaff,
  useStaffAction,
  useUpdateStaff,
  type StaffAction,
} from "../api";
import adminStyles from "../Admin.module.css";
import { useAdminAuth } from "../AdminAuthContext";
import { Badge } from "../Badge";
import { ADMIN_ROLE } from "../labels";
import type { PlatformRole, StaffMember } from "../types";

const MIN_PASSWORD = 8; // backend app/core/security.py MIN_PASSWORD_LENGTH
const ROLES = Object.keys(ADMIN_ROLE) as PlatformRole[];

function StaffStatus({ member }: { member: StaffMember }) {
  if (!member.is_active) return <Badge tone="neutral">Deactivated</Badge>;
  if (member.locked) return <Badge tone="warn">Locked out</Badge>;
  if (member.must_change_password) return <Badge tone="accent">Must change password</Badge>;
  return <Badge tone="good">Active</Badge>;
}

/** Duolink's own staff (ADR 0013). Support may look; a Super Admin makes every change. */
export function StaffPage() {
  const { isSuperAdmin } = useAdminAuth();
  const staff = useStaff();
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [adding, setAdding] = useState(false);
  const listRef = useRef<HTMLTableSectionElement>(null);

  const closePanel = () => {
    const id = selectedId;
    setSelectedId(null);
    setAdding(false);
    requestAnimationFrame(() =>
      listRef.current?.querySelector<HTMLElement>(`[data-row="${id}"]`)?.focus(),
    );
  };

  const selected = staff.data?.find((m) => m.id === selectedId);

  return (
    <section aria-labelledby="staff-title" className={styles.page}>
      <div className={styles.toolbar}>
        <h1 id="staff-title" className={styles.title}>
          Staff
        </h1>
        {isSuperAdmin ? (
          <Button
            variant="primary"
            onClick={() => {
              setSelectedId(null);
              setAdding(true);
            }}
          >
            Add staff member
          </Button>
        ) : null}
        <p className={styles.keys}>↑↓ move · Enter open · Esc close</p>
      </div>
      <p className={styles.note}>
        {ADMIN_ROLE.super_admin.label}: {ADMIN_ROLE.super_admin.note} {ADMIN_ROLE.support.label}:{" "}
        {ADMIN_ROLE.support.note}
      </p>

      {staff.isPending ? <p role="status">Loading staff…</p> : null}
      {staff.isError ? <p className={styles.formError}>Staff could not be loaded.</p> : null}
      {staff.data ? (
        <div className={styles.split}>
          <div className={styles.tableWrap}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th scope="col">Name</th>
                  <th scope="col">Email</th>
                  <th scope="col">Role</th>
                  <th scope="col">Status</th>
                  <th scope="col">Last sign-in</th>
                </tr>
              </thead>
              <tbody ref={listRef} onKeyDown={moveRowFocus}>
                {staff.data.map((m) => (
                  <tr
                    key={m.id}
                    className={[
                      selected?.id === m.id ? styles.selected : "",
                      m.is_active ? "" : styles.inactive,
                    ].join(" ")}
                  >
                    <td>
                      <button
                        type="button"
                        className={styles.rowButton}
                        data-row={m.id}
                        aria-current={selected?.id === m.id ? "true" : undefined}
                        onClick={() => {
                          setAdding(false);
                          setSelectedId(m.id);
                        }}
                      >
                        {m.full_name}
                      </button>
                    </td>
                    <td>{m.email}</td>
                    <td>
                      <Badge tone={ADMIN_ROLE[m.role].tone}>{ADMIN_ROLE[m.role].label}</Badge>
                    </td>
                    <td>
                      <StaffStatus member={m} />
                    </td>
                    <td>{formatDateTime(m.last_login_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className={styles.results}>
              {staff.data.length} {staff.data.length === 1 ? "member" : "members"}
            </p>
          </div>
          {adding && isSuperAdmin ? (
            <CreatePanel
              onClose={closePanel}
              onCreated={(id) => {
                setAdding(false);
                setSelectedId(id);
              }}
            />
          ) : selected ? (
            <StaffPanel key={selected.id} member={selected} onClose={closePanel} />
          ) : null}
        </div>
      ) : null}
    </section>
  );
}

function CreatePanel({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: (id: number) => void;
}) {
  const create = useCreateStaff();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [mobile, setMobile] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<PlatformRole>("support");
  const [error, setError] = useState<FormError | null>(null);
  const fieldError = (key: string) => (error?.field === key ? error.message : null);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    if (password.length < MIN_PASSWORD) {
      setError({ field: "password", message: `Use at least ${MIN_PASSWORD} characters.` });
      return;
    }
    try {
      const made = await create.mutateAsync({
        full_name: name.trim(),
        email: email.trim(),
        mobile: mobile.trim() || null,
        password,
        role,
      });
      onCreated(made.id);
    } catch (err) {
      setError(toFormError(err));
    }
  }

  return (
    <form
      className={styles.panel}
      aria-labelledby="staff-new-title"
      onSubmit={(e) => void onSubmit(e)}
      onKeyDown={(e) => {
        if (e.key === "Escape") onClose();
      }}
      noValidate
    >
      <div className={styles.panelHead}>
        <h2 id="staff-new-title">Add staff member</h2>
        <Button variant="ghost" onClick={onClose}>
          Close
        </Button>
      </div>
      <TextField
        label="Full name"
        autoFocus
        value={name}
        onChange={(e) => setName(e.target.value)}
        error={fieldError("full_name")}
      />
      <TextField
        label="Email"
        type="email"
        autoComplete="off"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        error={fieldError("email")}
      />
      <TextField
        label="Mobile"
        inputMode="tel"
        value={mobile}
        onChange={(e) => setMobile(e.target.value)}
        error={fieldError("mobile")}
      />
      <SelectField
        label="Role"
        value={role}
        onChange={(e) => setRole(e.target.value as PlatformRole)}
        hint={ADMIN_ROLE[role].note}
        error={fieldError("role")}
      >
        {ROLES.map((r) => (
          <option key={r} value={r}>
            {ADMIN_ROLE[r].label}
          </option>
        ))}
      </SelectField>
      <TextField
        label="Temporary password"
        type="password"
        autoComplete="new-password"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        hint="They must change it at their first sign-in."
        error={fieldError("password")}
      />
      {error && !error.field ? (
        <p role="alert" className={styles.formError}>
          {error.message}
        </p>
      ) : null}
      <div className={styles.actions}>
        <Button type="submit" variant="primary" disabled={create.isPending}>
          {create.isPending ? "Adding…" : "Add staff member"}
        </Button>
      </div>
    </form>
  );
}

const DONE: Record<StaffAction, string> = {
  unlock: "Unlocked. They can try their password again.",
  "sign-out": "Signed out everywhere. They must sign in again.",
};

function StaffPanel({ member, onClose }: { member: StaffMember; onClose: () => void }) {
  const { admin, isSuperAdmin } = useAdminAuth();
  const isMe = admin?.id === member.id;
  const update = useUpdateStaff();
  const action = useStaffAction();
  const reset = useResetStaffPassword();
  const [name, setName] = useState(member.full_name);
  const [mobile, setMobile] = useState(member.mobile ?? "");
  const [role, setRole] = useState<PlatformRole>(member.role);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<FormError | null>(null);
  const [password, setPassword] = useState<string | null>(null);
  const panelRef = useRef<HTMLElement>(null);
  const fieldError = (key: string) => (error?.field === key ? error.message : null);

  useEffect(() => {
    panelRef.current?.querySelector<HTMLElement>("button")?.focus();
  }, []);

  const busy = update.isPending || action.isPending || reset.isPending;

  async function save(event: FormEvent) {
    event.preventDefault();
    setNotice(null);
    setError(null);
    setPassword(null);
    try {
      await update.mutateAsync({
        id: member.id,
        full_name: name.trim(),
        mobile: mobile.trim() || null,
        role,
      });
      setNotice("Saved.");
    } catch (err) {
      setError(toFormError(err));
    }
  }

  async function setActive(active: boolean) {
    setNotice(null);
    setError(null);
    setPassword(null);
    try {
      await update.mutateAsync({ id: member.id, is_active: active });
      setNotice(
        active ? "Reactivated. They can sign in again." : "Deactivated. They are signed out.",
      );
    } catch (err) {
      setError(toFormError(err));
    }
  }

  async function run(kind: StaffAction) {
    setNotice(null);
    setError(null);
    setPassword(null);
    try {
      await action.mutateAsync({ id: member.id, action: kind });
      setNotice(DONE[kind]);
    } catch (err) {
      setError(toFormError(err));
    }
  }

  async function resetPassword() {
    setNotice(null);
    setError(null);
    try {
      const made = await reset.mutateAsync(member.id);
      setPassword(made.temporary_password);
    } catch (err) {
      setError(toFormError(err));
    }
  }

  return (
    <aside
      ref={panelRef}
      className={styles.panel}
      aria-labelledby={`staff-${member.id}`}
      onKeyDown={(e) => {
        if (e.key === "Escape") onClose();
      }}
    >
      <div className={styles.panelHead}>
        <h2 id={`staff-${member.id}`}>{member.full_name}</h2>
        <Button variant="ghost" onClick={onClose}>
          Close
        </Button>
      </div>
      <dl className={adminStyles.facts}>
        <dt>Email</dt>
        <dd>{member.email}</dd>
        <dt>Mobile</dt>
        <dd>{member.mobile ?? "Not recorded"}</dd>
        <dt>Role</dt>
        <dd>{ADMIN_ROLE[member.role].label}</dd>
        <dt>Signed in now</dt>
        <dd>
          {member.open_sessions} {member.open_sessions === 1 ? "session" : "sessions"}
        </dd>
        <dt>Last sign-in</dt>
        <dd>{formatDateTime(member.last_login_at)}</dd>
      </dl>

      {isSuperAdmin ? (
        <>
          <form className={styles.subsection} onSubmit={(e) => void save(e)} noValidate>
            <h3>Details</h3>
            <TextField
              label="Full name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              error={fieldError("full_name")}
            />
            <TextField
              label="Mobile"
              inputMode="tel"
              value={mobile}
              onChange={(e) => setMobile(e.target.value)}
              error={fieldError("mobile")}
            />
            <SelectField
              label="Role"
              value={role}
              onChange={(e) => setRole(e.target.value as PlatformRole)}
              disabled={isMe}
              hint={isMe ? "You cannot change your own role." : ADMIN_ROLE[role].note}
              error={fieldError("role")}
            >
              {ROLES.map((r) => (
                <option key={r} value={r}>
                  {ADMIN_ROLE[r].label}
                </option>
              ))}
            </SelectField>
            <div className={styles.actions}>
              <Button type="submit" variant="primary" disabled={busy}>
                Save
              </Button>
            </div>
          </form>

          <div className={adminStyles.rowActions}>
            {member.is_active ? (
              <Button disabled={busy || isMe} onClick={() => void setActive(false)}>
                Deactivate
              </Button>
            ) : (
              <Button disabled={busy} onClick={() => void setActive(true)}>
                Reactivate
              </Button>
            )}
            {member.locked ? (
              <Button disabled={busy} onClick={() => void run("unlock")}>
                Unlock
              </Button>
            ) : null}
            <Button disabled={busy || !member.is_active} onClick={() => void run("sign-out")}>
              Sign out everywhere
            </Button>
          </div>

          <div className={styles.subsection}>
            <h3>Reset password</h3>
            <p className={styles.note}>
              Makes a temporary password and signs them out everywhere. You see it once, and they
              must change it at their next sign-in.
            </p>
            <div className={styles.actions}>
              <Button disabled={busy} onClick={() => void resetPassword()}>
                Reset password
              </Button>
            </div>
            {password ? (
              <>
                <p role="status" className={styles.saved}>
                  Password reset. Give them this one in person.
                </p>
                <p className={adminStyles.secret} aria-label="Temporary password">
                  {password}
                </p>
              </>
            ) : null}
          </div>
        </>
      ) : null}

      {notice ? (
        <p role="status" className={styles.saved}>
          {notice}
        </p>
      ) : null}
      {error && !error.field ? (
        <p role="alert" className={styles.formError}>
          {error.message}
        </p>
      ) : null}
    </aside>
  );
}
