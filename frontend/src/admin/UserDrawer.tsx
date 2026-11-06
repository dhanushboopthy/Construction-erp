import { useEffect, useRef, useState } from "react";

import { toFormError } from "@/api/errors";
import { Button } from "@/components/Button";
import { SelectField, TextAreaField, TextField } from "@/components/Field";
import styles from "@/components/Ledger.module.css";
import { formatDateTime } from "@/lib/format";

import {
  useRemoveUser,
  useResetUserPassword,
  useRevokeSession,
  useUpdateUser,
  useUserAction,
  useUserSessions,
  type UserAction,
} from "./api";
import adminStyles from "./Admin.module.css";
import { useAdminAuth } from "./AdminAuthContext";
import { ROLE } from "./labels";
import type { PlatformUser } from "./types";
import { UserStatus } from "./UserStatus";

const DONE: Record<UserAction, string> = {
  deactivate: "Deactivated. They are signed out and cannot sign in.",
  activate: "Reactivated. They can sign in again.",
  unlock: "Unlocked. They can try their password again.",
  "sign-out": "Signed out everywhere. They must sign in again.",
};

/** One user, for Duolink support: facts, sessions and (for a Super Admin) the actions. */
export function UserDrawer({ user, onClose }: { user: PlatformUser; onClose: () => void }) {
  const { isSuperAdmin } = useAdminAuth();
  const action = useUserAction();
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const panelRef = useRef<HTMLElement>(null);
  const removed = user.removed_at !== null && user.removed_at !== undefined;

  useEffect(() => {
    panelRef.current?.querySelector<HTMLElement>("button")?.focus();
  }, []);

  async function run(kind: UserAction) {
    setNotice(null);
    setError(null);
    try {
      await action.mutateAsync({ id: user.id, action: kind });
      setNotice(DONE[kind]);
    } catch (err) {
      setError(toFormError(err).message);
    }
  }

  const busy = action.isPending;

  return (
    <aside
      ref={panelRef}
      className={styles.panel}
      aria-labelledby={`support-${user.id}`}
      onKeyDown={(e) => {
        if (e.key === "Escape") onClose();
      }}
    >
      <div className={styles.panelHead}>
        <h2 id={`support-${user.id}`}>{user.full_name}</h2>
        <Button variant="ghost" onClick={onClose}>
          Close
        </Button>
      </div>
      <dl className={adminStyles.facts}>
        <dt>Company</dt>
        <dd>{user.tenant_name}</dd>
        <dt>Username</dt>
        <dd>{user.username}</dd>
        <dt>Mobile</dt>
        <dd>{user.mobile ?? "Not given"}</dd>
        <dt>Role</dt>
        <dd>{ROLE[user.role]}</dd>
        <dt>Status</dt>
        <dd>
          <UserStatus user={user} />
        </dd>
        {removed ? (
          <>
            <dt>Removed</dt>
            <dd>{formatDateTime(user.removed_at)}</dd>
          </>
        ) : null}
        <dt>Wrong passwords</dt>
        <dd>{user.failed_login_count} since the last sign-in</dd>
        <dt>Last sign-in</dt>
        <dd>{user.last_login_at ? formatDateTime(user.last_login_at) : "Never signed in"}</dd>
      </dl>

      {removed ? (
        <p className={styles.note}>
          This account was removed. Their name stays on the documents they made, and nothing can
          change it now.
        </p>
      ) : null}

      {isSuperAdmin && !removed ? (
        <div className={adminStyles.rowActions}>
          {user.is_active ? (
            <Button disabled={busy} onClick={() => void run("deactivate")}>
              Deactivate
            </Button>
          ) : (
            <Button disabled={busy} onClick={() => void run("activate")}>
              Reactivate
            </Button>
          )}
          {user.locked ? (
            <Button disabled={busy} onClick={() => void run("unlock")}>
              Unlock
            </Button>
          ) : null}
          <Button disabled={busy || !user.is_active} onClick={() => void run("sign-out")}>
            Sign out everywhere
          </Button>
        </div>
      ) : null}

      {notice ? (
        <p role="status" className={styles.saved}>
          {notice}
        </p>
      ) : null}
      {error ? (
        <p role="alert" className={styles.formError}>
          {error}
        </p>
      ) : null}

      {removed ? null : <Sessions user={user} canEnd={isSuperAdmin} />}
      {isSuperAdmin && !removed ? (
        <>
          <EditUser user={user} />
          <ResetPassword user={user} />
          <RemoveAccess user={user} onRemoved={() => setNotice(null)} />
        </>
      ) : null}
    </aside>
  );
}

// ------------------------------------------------------------------ sessions

function Sessions({ user, canEnd }: { user: PlatformUser; canEnd: boolean }) {
  const sessions = useUserSessions(user.id);
  const revoke = useRevokeSession(user.id);
  const [error, setError] = useState<string | null>(null);

  return (
    <div className={styles.subsection}>
      <h3>Signed in on</h3>
      {sessions.isPending ? <p role="status">Loading sessions…</p> : null}
      {sessions.isError ? <p className={styles.formError}>Sessions could not be loaded.</p> : null}
      {sessions.data && sessions.data.length === 0 ? (
        <p className={styles.note}>Not signed in anywhere.</p>
      ) : null}
      {sessions.data && sessions.data.length ? (
        <table className={styles.table}>
          <thead>
            <tr>
              <th scope="col">Device</th>
              <th scope="col">Address</th>
              <th scope="col">Signed in</th>
              <th scope="col">Last used</th>
              {canEnd ? <th scope="col">Action</th> : null}
            </tr>
          </thead>
          <tbody>
            {sessions.data.map((s) => (
              <tr key={s.id}>
                <td>{s.device}</td>
                <td>{s.ip ?? "Unknown"}</td>
                <td>{formatDateTime(s.signed_in_at)}</td>
                <td>{formatDateTime(s.last_used_at)}</td>
                {canEnd ? (
                  <td>
                    <Button
                      disabled={revoke.isPending}
                      aria-label={`End session on ${s.device}`}
                      onClick={() => {
                        setError(null);
                        revoke.mutate(s.id, { onError: (e) => setError(toFormError(e).message) });
                      }}
                    >
                      End
                    </Button>
                  </td>
                ) : null}
              </tr>
            ))}
          </tbody>
        </table>
      ) : null}
      {error ? (
        <p role="alert" className={styles.formError}>
          {error}
        </p>
      ) : null}
    </div>
  );
}

// ------------------------------------------------------------------ edit

function EditUser({ user }: { user: PlatformUser }) {
  const update = useUpdateUser(user.id);
  const [fullName, setFullName] = useState(user.full_name);
  const [mobile, setMobile] = useState(user.mobile ?? "");
  const [username, setUsername] = useState(user.username);
  const [role, setRole] = useState(user.role);
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  function submit() {
    setSaved(false);
    if (reason.trim().length < 3) {
      setError("Write why, in a few words. The company's owner may ask.");
      return;
    }
    setError(null);
    update.mutate(
      {
        full_name: fullName.trim(),
        mobile: mobile.trim() || null,
        username: username.trim(),
        role,
        reason: reason.trim(),
      },
      {
        onSuccess: () => {
          setReason("");
          setSaved(true);
        },
        onError: (err) => setError(toFormError(err).message),
      },
    );
  }

  return (
    <form
      className={styles.subsection}
      onSubmit={(e) => {
        e.preventDefault();
        submit();
      }}
      noValidate
    >
      <h3>Edit user</h3>
      <TextField
        label="Full name"
        value={fullName}
        onChange={(e) => setFullName(e.target.value)}
        maxLength={100}
      />
      <TextField
        label="Mobile"
        type="tel"
        value={mobile}
        onChange={(e) => setMobile(e.target.value)}
        hint="Optional. Leave blank to clear it."
      />
      <TextField
        label="Username"
        value={username}
        onChange={(e) => setUsername(e.target.value)}
        hint="Lowercase letters, digits, dot, dash and underscore. They sign in with this."
      />
      <SelectField
        label="Role"
        value={role}
        onChange={(e) => setRole(e.target.value as typeof role)}
      >
        {(Object.keys(ROLE) as (keyof typeof ROLE)[]).map((r) => (
          <option key={r} value={r}>
            {ROLE[r]}
          </option>
        ))}
      </SelectField>
      <TextAreaField
        label="Reason for the change"
        value={reason}
        onChange={(e) => setReason(e.target.value)}
        hint="For example: the owner asked by phone."
      />
      {error ? (
        <p role="alert" className={styles.formError}>
          {error}
        </p>
      ) : null}
      {saved ? (
        <p role="status" className={styles.saved}>
          Saved. It is in both audit logs.
        </p>
      ) : null}
      <div className={styles.actions}>
        <Button type="submit" variant="primary" disabled={update.isPending}>
          Save changes
        </Button>
      </div>
    </form>
  );
}

// ------------------------------------------------------------------ reset password

function ResetPassword({ user }: { user: PlatformUser }) {
  const reset = useResetUserPassword();
  const [password, setPassword] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<string | null>(null);

  return (
    <div className={styles.subsection}>
      <h3>Reset password</h3>
      <p className={styles.note}>
        Makes a temporary password and signs them out everywhere. They must choose their own at the
        next sign-in. You see it once.
      </p>
      <div className={styles.actions}>
        <Button
          disabled={reset.isPending}
          onClick={() => {
            setError(null);
            setCopied(false);
            reset.mutate(user.id, {
              onSuccess: (made) => setPassword(made.temporary_password),
              onError: (err) => setError(toFormError(err).message),
            });
          }}
        >
          Reset password
        </Button>
      </div>
      {password ? (
        <>
          <p role="status" className={styles.saved}>
            Password reset. Give them this one in person; they must change it.
          </p>
          <p className={adminStyles.secret} aria-label="Temporary password">
            {password}
          </p>
          <div className={styles.actions}>
            <Button
              onClick={() => {
                void navigator.clipboard?.writeText(password).then(() => setCopied(true));
              }}
            >
              {copied ? "Copied" : "Copy password"}
            </Button>
          </div>
        </>
      ) : null}
      {error ? (
        <p role="alert" className={styles.formError}>
          {error}
        </p>
      ) : null}
    </div>
  );
}

// ------------------------------------------------------------------ remove access

function RemoveAccess({ user, onRemoved }: { user: PlatformUser; onRemoved: () => void }) {
  const [asking, setAsking] = useState(false);
  return (
    <div className={styles.subsection}>
      <h3>Remove access</h3>
      <p className={styles.note}>
        For someone who has left. The account is switched off and hidden from the company&apos;s
        list. It is never deleted, because their name stays on every document they made.
      </p>
      {asking ? (
        <RemoveDialog user={user} onCancel={() => setAsking(false)} onRemoved={onRemoved} />
      ) : (
        <div className={styles.actions}>
          <Button className={adminStyles.danger} onClick={() => setAsking(true)}>
            Remove access…
          </Button>
        </div>
      )}
    </div>
  );
}

/** Mounted only while open, so the sessions it shows are fetched when it opens. */
function RemoveDialog({
  user,
  onCancel,
  onRemoved,
}: {
  user: PlatformUser;
  onCancel: () => void;
  onRemoved: () => void;
}) {
  const sessions = useUserSessions(user.id);
  const remove = useRemoveUser(user.id);
  const [typed, setTyped] = useState("");
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const live = sessions.data?.length;

  return (
    <div className={adminStyles.confirm} role="alertdialog" aria-labelledby={`remove-${user.id}`}>
      <p id={`remove-${user.id}`}>
        Remove {user.full_name} from {user.tenant_name}?{" "}
        {live === undefined
          ? "Checking where they are signed in…"
          : live === 0
            ? "They are not signed in anywhere."
            : `${live} ${live === 1 ? "session ends" : "sessions end"} now.`}{" "}
        They can no longer sign in, and this cannot be undone from here.
      </p>
      <TextField
        label={`Type ${user.username} to confirm`}
        value={typed}
        onChange={(e) => setTyped(e.target.value)}
        autoComplete="off"
        autoFocus
      />
      <TextAreaField
        label="Reason for removing"
        value={reason}
        onChange={(e) => setReason(e.target.value)}
      />
      {error ? (
        <p role="alert" className={styles.formError}>
          {error}
        </p>
      ) : null}
      <div className={styles.actions}>
        <Button
          variant="primary"
          className={adminStyles.danger}
          disabled={remove.isPending || typed !== user.username || reason.trim().length < 3}
          onClick={() =>
            remove.mutate(
              { confirm_username: typed, reason: reason.trim() },
              {
                onSuccess: onRemoved,
                onError: (err) => setError(toFormError(err).message),
              },
            )
          }
        >
          Remove access
        </Button>
        <Button onClick={onCancel}>Keep the account</Button>
      </div>
    </div>
  );
}
