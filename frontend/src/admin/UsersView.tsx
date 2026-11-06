import { useCallback, useRef, useState } from "react";
import { Link } from "react-router";

import { Button } from "@/components/Button";
import styles from "@/components/Ledger.module.css";
import { moveRowFocus } from "@/hooks/useKeys";
import { formatDateTime } from "@/lib/format";

import { USER_PAGE_SIZE, useAdminUsers, type UserFilters } from "./api";
import { ROLE } from "./labels";
import { UserDrawer } from "./UserDrawer";
import { UserStatus } from "./UserStatus";

/** Users as a ledger with a support drawer beside it (DESIGN.md "List + editor"). With
 * `tenantId`, only that company's users and no company column. The parent gives the view a new
 * `key` when the filters change, so paging starts again from the first page. */
export function UsersView({
  tenantId,
  filters = {},
}: {
  tenantId?: number;
  filters?: Omit<UserFilters, "tenant_id" | "offset">;
}) {
  const [page, setPage] = useState(0);
  const users = useAdminUsers({ ...filters, tenant_id: tenantId, offset: page * USER_PAGE_SIZE });
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

  const { items, total } = users.data;
  const selected = items.find((u) => u.id === selectedId);
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
            {items.length ? (
              items.map((u) => (
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
                  <td>{u.last_login_at ? formatDateTime(u.last_login_at) : "Never signed in"}</td>
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
          {total} {total === 1 ? "user" : "users"}
          {total > USER_PAGE_SIZE
            ? `, showing ${page * USER_PAGE_SIZE + 1} to ${Math.min(total, (page + 1) * USER_PAGE_SIZE)}`
            : ""}
        </p>
        {total > USER_PAGE_SIZE ? (
          <nav aria-label="Pages" className={styles.actions}>
            <Button disabled={page === 0} onClick={() => setPage(page - 1)}>
              Previous
            </Button>
            <Button
              disabled={(page + 1) * USER_PAGE_SIZE >= total}
              onClick={() => setPage(page + 1)}
            >
              Next
            </Button>
          </nav>
        ) : null}
      </div>
      {selected ? <UserDrawer key={selected.id} user={selected} onClose={close} /> : null}
    </div>
  );
}
