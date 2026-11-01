import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router";

import { Button } from "@/components/Button";
import { SelectField } from "@/components/Field";
import ledger from "@/components/Ledger.module.css";
import { moveRowFocus } from "@/hooks/useKeys";
import { formatDateTime, plural } from "@/lib/format";

import { useTickets } from "./api";
import { CATEGORY, TICKET_STATUS, TICKET_STATUS_ORDER } from "./labels";
import { NewTicketForm } from "./NewTicketForm";
import styles from "./Support.module.css";
import { PriorityLabel, StatusLabel } from "./Thread";

/** Help: the company's tickets to Duolink, and a form to raise one. Open to every role. */
export function HelpPage() {
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const status = params.get("status") ?? "";
  const [raising, setRaising] = useState(false);
  const tickets = useTickets(status);

  const setStatus = (value: string) => setParams(value ? { status: value } : {}, { replace: true });

  return (
    <section aria-labelledby="help-title" className={ledger.page}>
      <div className={ledger.toolbar}>
        <h1 id="help-title" className={ledger.title}>
          Help
        </h1>
        {raising ? null : (
          <Button variant="primary" allowWhenReadOnly onClick={() => setRaising(true)}>
            New ticket
          </Button>
        )}
        <p className={ledger.keys}>↑↓ move · Enter open</p>
      </div>
      <p className={ledger.note}>
        Ask Duolink for help. Replies appear here, and a dot shows on Help when one arrives.
      </p>

      {raising ? (
        <NewTicketForm
          onCancel={() => setRaising(false)}
          onCreated={(t) => void navigate(`/help/${t.id}`)}
        />
      ) : null}

      <form className={ledger.filters} role="search" onSubmit={(e) => e.preventDefault()}>
        <SelectField label="Status" value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">Any status</option>
          {TICKET_STATUS_ORDER.map((s) => (
            <option key={s} value={s}>
              {TICKET_STATUS[s].label}
            </option>
          ))}
        </SelectField>
      </form>

      {tickets.isPending ? (
        <p role="status">Loading tickets…</p>
      ) : tickets.isError ? (
        <p role="alert" className={ledger.formError}>
          Tickets could not be loaded. Reload the page.
        </p>
      ) : (
        <div className={ledger.tableWrap}>
          <table className={ledger.table}>
            <caption className="visually-hidden">Tickets</caption>
            <thead>
              <tr>
                <th scope="col">Ticket</th>
                <th scope="col">Subject</th>
                <th scope="col">Category</th>
                <th scope="col">Priority</th>
                <th scope="col">Status</th>
                <th scope="col">Raised by</th>
                <th scope="col">Last reply</th>
              </tr>
            </thead>
            <tbody onKeyDown={moveRowFocus}>
              {tickets.data.items.length ? (
                tickets.data.items.map((t) => (
                  <tr key={t.id}>
                    <td className={styles.number}>{t.number}</td>
                    <td>
                      {t.unread ? (
                        <>
                          <span className={styles.unread} aria-hidden="true" />
                          <span className="visually-hidden">New reply: </span>
                        </>
                      ) : null}
                      <Link to={`/help/${t.id}`} data-row={t.id}>
                        {t.subject}
                      </Link>
                    </td>
                    <td>{CATEGORY[t.category]}</td>
                    <td>
                      <PriorityLabel priority={t.priority} />
                    </td>
                    <td>
                      <StatusLabel status={t.status} />
                    </td>
                    <td>{t.raised_by_name}</td>
                    <td>{formatDateTime(t.last_reply_at ?? t.created_at)}</td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={7} className={ledger.empty}>
                    {status
                      ? "No ticket has this status."
                      : "No tickets yet. Raise one with New ticket."}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
          <p className={ledger.results}>
            {tickets.data.total} {plural(tickets.data.total, "ticket")}
          </p>
        </div>
      )}
    </section>
  );
}
