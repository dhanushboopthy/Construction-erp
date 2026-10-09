import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";

import { toFormError, type FormError } from "@/api/errors";
import {
  useCreateUser,
  useLocations,
  useResetPassword,
  useUpdateUser,
  useUsers,
} from "@/api/setup";
import type { Location, Role, User } from "@/api/types";
import { useAuth } from "@/auth/AuthContext";
import { Button } from "@/components/Button";
import { CheckField, TextField } from "@/components/Field";
import { moveRowFocus, useAltKey } from "@/hooks/useKeys";
import { formatDateTime } from "@/lib/format";

import styles from "@/components/Ledger.module.css";

const MIN_PASSWORD = 8; // backend app/core/security.py MIN_PASSWORD_LENGTH

const ROLES: { value: Role; label: string; note: string }[] = [
  {
    value: "counter",
    label: "Counter staff",
    note: "Bills and purchases at their own shop. Never sees cost.",
  },
  { value: "accountant", label: "Accountant", note: "Reports and GST exports. Cannot bill." },
  { value: "owner", label: "Owner", note: "Everything, including cost, margin and settings." },
];
const ROLE_LABEL: Record<Role, string> = {
  owner: "Owner",
  counter: "Counter staff",
  accountant: "Accountant",
};

const T = {
  heading: "Users",
  add: "Add user",
  keys: "Alt+N new · ↑↓ move · Enter open · Esc close",
  loading: "Loading users…",
  loadFailed: "Users could not be loaded.",
  newTitle: "New user",
  create: "Create user",
  saveChanges: "Save changes",
  saved: "Changes saved.",
  created: "User created. Share the password with them in person.",
  close: "Close",
  resetTitle: "Reset password",
  resetHint: "Signs them out everywhere. They use the new password next time.",
  resetButton: "Reset password",
  resetDone: "Password reset. Share it with them in person.",
};

type Mode = { kind: "closed" } | { kind: "new" } | { kind: "edit"; id: number };

export function UsersPage() {
  const users = useUsers();
  const locations = useLocations();
  const [mode, setMode] = useState<Mode>({ kind: "closed" });
  const [notice, setNotice] = useState<string | null>(null);
  const listRef = useRef<HTMLTableSectionElement>(null);

  const openNew = useCallback(() => {
    setNotice(null);
    setMode({ kind: "new" });
  }, []);
  useAltKey("n", openNew);

  const close = useCallback(() => {
    const id = mode.kind === "edit" ? mode.id : null;
    setMode({ kind: "closed" });
    // Return focus to the row the user came from so the keyboard flow continues.
    requestAnimationFrame(() => {
      const row = id ? listRef.current?.querySelector<HTMLElement>(`[data-row="${id}"]`) : null;
      (row ?? listRef.current?.querySelector<HTMLElement>("[data-row]"))?.focus();
    });
  }, [mode]);

  if (users.isPending || locations.isPending) return <p role="status">{T.loading}</p>;
  if (users.isError || locations.isError) return <p className={styles.formError}>{T.loadFailed}</p>;

  const selected = mode.kind === "edit" ? users.data.find((u) => u.id === mode.id) : undefined;

  return (
    <>
      <div className={styles.toolbar}>
        <h2>{T.heading}</h2>
        <Button variant="primary" onClick={openNew} aria-keyshortcuts="Alt+N">
          {T.add}
        </Button>
        <p className={styles.keys}>{T.keys}</p>
      </div>
      {notice ? (
        <p role="status" className={styles.saved}>
          {notice}
        </p>
      ) : null}
      <div className={styles.split}>
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th scope="col">Name</th>
                <th scope="col">Username</th>
                <th scope="col">Role</th>
                <th scope="col">Shops</th>
                <th scope="col">Status</th>
                <th scope="col">Last sign-in</th>
              </tr>
            </thead>
            <tbody ref={listRef} onKeyDown={moveRowFocus}>
              {users.data.map((u) => (
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
                      onClick={() => {
                        setNotice(null);
                        setMode({ kind: "edit", id: u.id });
                      }}
                    >
                      {u.full_name}
                    </button>
                  </td>
                  <td>{u.username}</td>
                  <td>{ROLE_LABEL[u.role]}</td>
                  <td>
                    {u.role === "counter"
                      ? u.locations.map((l) => l.code).join(", ") || "None"
                      : "All"}
                  </td>
                  <td className={styles.status}>
                    <span className={u.is_active ? styles.statusActive : styles.statusInactive}>
                      {u.is_active ? "Active" : "Inactive"}
                    </span>
                  </td>
                  <td className="num">{formatDateTime(u.last_login_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {mode.kind === "new" ? (
          <UserEditor
            key="new"
            locations={locations.data}
            onClose={close}
            onDone={(user) => {
              setNotice(T.created);
              setMode({ kind: "edit", id: user.id });
            }}
          />
        ) : selected ? (
          <UserEditor
            key={selected.id}
            user={selected}
            locations={locations.data}
            onClose={close}
            onDone={() => setNotice(T.saved)}
          />
        ) : null}
      </div>
    </>
  );
}

function UserEditor({
  user,
  locations,
  onClose,
  onDone,
}: {
  user?: User;
  locations: Location[];
  onClose: () => void;
  onDone: (user: User) => void;
}) {
  const { user: me, reloadUser } = useAuth();
  const create = useCreateUser();
  const update = useUpdateUser();
  const isSelf = user?.id === me?.id;

  const [username, setUsername] = useState("");
  const [fullName, setFullName] = useState(user?.full_name ?? "");
  const [role, setRole] = useState<Role>(user?.role ?? "counter");
  const [password, setPassword] = useState("");
  const [active, setActive] = useState(user?.is_active ?? true);
  const [shopIds, setShopIds] = useState<number[]>(user?.locations.map((l) => l.id) ?? []);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [serverError, setServerError] = useState<FormError | null>(null);
  const firstField = useRef<HTMLInputElement>(null);

  useEffect(() => firstField.current?.focus(), []);

  const titleId = `user-editor-${user?.id ?? "new"}`;
  const pending = create.isPending || update.isPending;

  function validate(): Record<string, string> {
    const found: Record<string, string> = {};
    if (!user && !/^[a-z0-9_.-]{3,50}$/.test(username)) {
      found.username = "Use 3–50 lowercase letters, digits, dot, dash or underscore.";
    }
    if (!fullName.trim()) found.full_name = "Enter their name as it should appear on bills.";
    if (!user && password.length < MIN_PASSWORD) {
      found.password = `Use at least ${MIN_PASSWORD} characters.`;
    }
    if (role === "counter" && shopIds.length === 0) {
      found.location_ids = "Counter staff need at least one shop.";
    }
    return found;
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    const found = validate();
    setErrors(found);
    setServerError(null);
    if (Object.keys(found).length > 0) return;
    const location_ids = role === "counter" ? shopIds : [];
    try {
      const saved = user
        ? await update.mutateAsync({
            id: user.id,
            body: { full_name: fullName.trim(), role, is_active: active, location_ids },
          })
        : await create.mutateAsync({
            username,
            full_name: fullName.trim(),
            role,
            password,
            location_ids,
          });
      if (isSelf) await reloadUser();
      onDone(saved);
    } catch (err) {
      setServerError(toFormError(err));
    }
  }

  const fieldError = (key: string) =>
    errors[key] ?? (serverError?.field === key ? serverError.message : null);
  const generalError =
    serverError &&
    !["username", "full_name", "password", "location_ids"].includes(serverError.field ?? "")
      ? serverError.message
      : null;

  return (
    <aside
      className={styles.panel}
      aria-labelledby={titleId}
      onKeyDown={(e) => {
        if (e.key === "Escape") onClose();
      }}
    >
      <div className={styles.panelHead}>
        <h2 id={titleId}>{user ? user.full_name : T.newTitle}</h2>
        <Button variant="quiet" onClick={onClose} aria-keyshortcuts="Escape">
          {T.close}
        </Button>
      </div>
      <form onSubmit={(e) => void onSubmit(e)} noValidate>
        {user ? (
          <TextField
            label="Username"
            value={user.username}
            readOnly
            hint="Usernames cannot change."
          />
        ) : (
          <TextField
            ref={firstField}
            label="Username"
            value={username}
            autoComplete="off"
            onChange={(e) => setUsername(e.target.value.toLowerCase())}
            error={fieldError("username")}
            hint="They type this to sign in, e.g. counter3."
          />
        )}
        <TextField
          ref={user ? firstField : undefined}
          label="Full name"
          value={fullName}
          onChange={(e) => setFullName(e.target.value)}
          error={fieldError("full_name")}
        />
        {user ? null : (
          <TextField
            label="Password"
            type="password"
            autoComplete="new-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            error={fieldError("password")}
            hint={`At least ${MIN_PASSWORD} characters.`}
          />
        )}
        <fieldset className={styles.choices}>
          <legend>Role</legend>
          {ROLES.map((r) => (
            <label key={r.value} className={styles.choice}>
              <input
                type="radio"
                name={`role-${titleId}`}
                value={r.value}
                checked={role === r.value}
                disabled={isSelf}
                onChange={() => setRole(r.value)}
              />
              <span>
                {r.label} <span className={styles.choiceNote}>{r.note}</span>
              </span>
            </label>
          ))}
        </fieldset>
        {role === "counter" ? (
          <fieldset className={styles.choices} aria-describedby={`${titleId}-shops-error`}>
            <legend>Works at</legend>
            {locations.map((l) => (
              <label key={l.id} className={styles.choice}>
                <input
                  type="checkbox"
                  checked={shopIds.includes(l.id)}
                  onChange={(e) =>
                    setShopIds((ids) =>
                      e.target.checked ? [...ids, l.id] : ids.filter((id) => id !== l.id),
                    )
                  }
                />
                <span>
                  <span className={styles.code}>{l.code}</span> {l.name}
                </span>
              </label>
            ))}
            {fieldError("location_ids") ? (
              <p id={`${titleId}-shops-error`} className={styles.formError}>
                {fieldError("location_ids")}
              </p>
            ) : null}
          </fieldset>
        ) : (
          <p className={styles.choiceNote}>Owners and accountants see every shop and the godown.</p>
        )}
        {user ? (
          <CheckField
            label="Active"
            checked={active}
            disabled={isSelf}
            onChange={(e) => setActive(e.target.checked)}
            hint={
              isSelf
                ? "You cannot deactivate or change the role of your own account."
                : "Inactive users cannot sign in and are signed out now."
            }
          />
        ) : null}
        {generalError ? (
          <p role="alert" className={styles.formError}>
            {generalError}
          </p>
        ) : null}
        <div className={styles.actions}>
          <Button type="submit" variant="primary" disabled={pending}>
            {pending ? "Saving…" : user ? T.saveChanges : T.create}
          </Button>
        </div>
      </form>
      {user ? <ResetPassword user={user} /> : null}
    </aside>
  );
}

function ResetPassword({ user }: { user: User }) {
  const reset = useResetPassword();
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setDone(false);
    if (password.length < MIN_PASSWORD) {
      setError(`Use at least ${MIN_PASSWORD} characters.`);
      return;
    }
    setError(null);
    try {
      await reset.mutateAsync({ id: user.id, password });
      setPassword("");
      setDone(true);
    } catch (err) {
      setError(toFormError(err).message);
    }
  }

  return (
    <form className={styles.subsection} onSubmit={(e) => void onSubmit(e)} noValidate>
      <h3>{T.resetTitle}</h3>
      <TextField
        label="New password"
        type="password"
        autoComplete="new-password"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        error={error}
        hint={T.resetHint}
      />
      <div className={styles.actions}>
        <Button type="submit" disabled={reset.isPending}>
          {T.resetButton}
        </Button>
        {done ? (
          <p role="status" className={styles.saved}>
            {T.resetDone}
          </p>
        ) : null}
      </div>
    </form>
  );
}
