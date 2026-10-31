import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router";

import { toFormError } from "@/api/errors";
import { Button } from "@/components/Button";
import styles from "@/components/Ledger.module.css";
import { moveRowFocus } from "@/hooks/useKeys";
import { formatDateTime } from "@/lib/format";

import { useAdminUsers, useResetUserPassword, useUserAction, type UserAction } from "./api";
import adminStyles from "./Admin.module.css";
import { useAdminAuth } from "./AdminAuthContext";
import { Badge } from "./Badge";
import { ROLE } from "./labels";
import type { PlatformUser } from "./types";

/** Users as a ledger with a support panel beside it (DESIGN.md "List + editor"). With
 * `tenantId`, only that company's users and no company column. */
export function UsersView({
  tenantId,
  q,
  state,
}: {
  tenantId?: number;
  q?: string;
  state?: string;
}) {
  const users = useAdminUsers({ tenant_id: tenantId, q, state });
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const listRef = useRef<HTMLTableSectionElement>(null);

  const close = useCallback(() => {
    const id = selectedId;
    setSelectedId(null);
    requestAnimationFrame(() =>
      listRef.current?.querySelector<HTMLElement>(`[data-row="${id}"]`)?.focus(),
    );
  }, [selectedId]);

  if (users.isPending) return <p role="status">Loading users…</p>;
  if (users.isError) return <p className={styles.formError}>Users could not be loaded.</p>;

  const selected = users.data.items.find((u) => u.id === selectedId);
  const columns = tenantId ? 5 : 6;

  return (
    <div className={styles.split}>
      <div className={styles.tableWrap}>
        <table className={styles.table}>
          <thead>
            <tr>
              <th scope="col">Name</th>
              {tenantId ? null : <th scope="col">Company</th>}
              <th scope="col">Username</th>
              <th scope="col">Role</th>
              <th scope="col">Status</th>
              <th scope="col">Last sign-in</th>
            </tr>
          </thead>
          <tbody ref={listRef} onKeyDown={moveRowFocus}>
            {users.data.items.length ? (
              users.data.items.map((u) => (
                <tr
                  key={u.id}
                  className={[
                    selected?.id === u.id ? styles.selected : "",
                    u.is_active ? "" : styles.inactive,
                  ].join(" ")}
                >
                  <td>
                    <button
                      type="button"
                      className={styles.rowButton}
                      data-row={u.id}
                      aria-current={selected?.id === u.id ? "true" : undefined}
                      onClick={() => setSelectedId(u.id)}
                    >
                      {u.full_name}
                    </button>
                  </td>
                  {tenantId ? null : (
                    <td>
                      <Link to={`/admin/companies/${u.tenant_id}`}>{u.tenant_name}</Link>
                    </td>
                  )}
                  <td>{u.username}</td>
                  <td>{ROLE[u.role]}</td>
                  <td>
                    <UserStatus user={u} />
                  </td>
                  <td>{formatDateTime(u.last_login_at)}</td>
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan={columns} className={styles.empty}>
                  No user matches.
                </td>
              </tr>
            )}
          </tbody>
        </table>
        <p className={styles.results}>
          {users.data.total} {users.data.total === 1 ? "user" : "users"}
        </p>
      </div>
      {selected ? <SupportPanel key={selected.id} user={selected} onClose={close} /> : null}
    </div>
  );
}

function UserStatus({ user }: { user: PlatformUser }) {
  if (!user.is_active) return <Badge tone="neutral">Deactivated</Badge>;
  if (user.locked) return <Badge tone="warn">Locked out</Badge>;
  return <Badge tone="good">Active</Badge>;
}

const DONE: Record<UserAction, string> = {
  deactivate: "Deactivated. They are signed out and cannot sign in.",
  activate: "Reactivated. They can sign in again.",
  unlock: "Unlocked. They can try their password again.",
  "sign-out": "Signed out everywhere. They must sign in again.",
};

function SupportPanel({ user, onClose }: { user: PlatformUser; onClose: () => void }) {
  const { isSuperAdmin } = useAdminAuth();
  const action = useUserAction();
  const reset = useResetUserPassword();
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [password, setPassword] = useState<string | null>(null);
  const panelRef = useRef<HTMLElement>(null);

  useEffect(() => {
    panelRef.current?.querySelector<HTMLElement>("button")?.focus();
  }, []);

  async function run(kind: UserAction) {
    setNotice(null);
    setError(null);
    setPassword(null);
    try {
      await action.mutateAsync({ id: user.id, action: kind });
      setNotice(DONE[kind]);
    } catch (err) {
      setError(toFormError(err).message);
    }
  }

  async function resetPassword() {
    setNotice(null);
    setError(null);
    try {
      const made = await reset.mutateAsync(user.id);
      setPassword(made.temporary_password);
    } catch (err) {
      setError(toFormError(err).message);
    }
  }

  const busy = action.isPending || reset.isPending;

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
        <dt>Role</dt>
        <dd>{ROLE[user.role]}</dd>
        <dt>Wrong passwords</dt>
        <dd>{user.failed_login_count} since the last sign-in</dd>
        <dt>Last sign-in</dt>
        <dd>{formatDateTime(user.last_login_at)}</dd>
      </dl>

      {isSuperAdmin ? (
        <>
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

          <div className={styles.subsection}>
            <h3>Reset password</h3>
            <p className={styles.note}>
              Makes a temporary password and signs them out everywhere. You see it once.
            </p>
            <div className={styles.actions}>
              <Button disabled={busy} onClick={() => void resetPassword()}>
                Reset password
              </Button>
            </div>
            {password ? (
              <>
                <p role="status" className={styles.saved}>
                  Password reset. Give them this one in person; they should change it.
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
      {error ? (
        <p role="alert" className={styles.formError}>
          {error}
        </p>
      ) : null}
    </aside>
  );
}
