import { Link } from "react-router";

import ledger from "@/components/Ledger.module.css";
import { moveRowFocus } from "@/hooks/useKeys";
import { formatDateTime } from "@/lib/format";
import { CATEGORY } from "@/support/labels";
import styles from "@/support/Support.module.css";
import { PriorityLabel, StatusLabel } from "@/support/Thread";

import type { AdminTicketRow } from "./types";

/** Tickets as a table, for the Support page and a company's Support tab. */
export function TicketTable({
  rows,
  showCompany = true,
  empty,
}: {
  rows: AdminTicketRow[];
  showCompany?: boolean;
  empty: string;
}) {
  return (
    <table className={ledger.table}>
      <caption className="visually-hidden">Tickets</caption>
      <thead>
        <tr>
          <th scope="col">Ticket</th>
          <th scope="col">Subject</th>
          {showCompany ? <th scope="col">Company</th> : null}
          <th scope="col">Category</th>
          <th scope="col">Priority</th>
          <th scope="col">Status</th>
          <th scope="col">Assigned to</th>
          <th scope="col">Last reply</th>
        </tr>
      </thead>
      <tbody onKeyDown={moveRowFocus}>
        {rows.length ? (
          rows.map((t) => (
            <tr key={t.id}>
              <td className={styles.number}>{t.number}</td>
              <td>
                {t.unread ? (
                  <>
                    <span className={styles.unread} aria-hidden="true" />
                    <span className="visually-hidden">New message: </span>
                  </>
                ) : null}
                <Link to={`/admin/support/${t.id}`} data-row={t.id}>
                  {t.subject}
                </Link>
                <div className={ledger.sub}>Raised by {t.raised_by_name}</div>
              </td>
              {showCompany ? (
                <td>
                  <Link to={`/admin/companies/${t.tenant_id}?tab=support`}>{t.tenant_name}</Link>
                </td>
              ) : null}
              <td>{CATEGORY[t.category]}</td>
              <td>
                <PriorityLabel priority={t.priority} />
              </td>
              <td>
                <StatusLabel status={t.status} />
              </td>
              <td>{t.assigned_admin_name ?? "Unassigned"}</td>
              <td>{formatDateTime(t.last_reply_at ?? t.created_at)}</td>
            </tr>
          ))
        ) : (
          <tr>
            <td colSpan={showCompany ? 8 : 7} className={ledger.empty}>
              {empty}
            </td>
          </tr>
        )}
      </tbody>
    </table>
  );
}
