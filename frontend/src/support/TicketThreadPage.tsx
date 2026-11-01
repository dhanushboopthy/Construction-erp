import { useState, type FormEvent } from "react";
import { Link, useParams } from "react-router";

import { Button } from "@/components/Button";
import { TextAreaField } from "@/components/Field";
import ledger from "@/components/Ledger.module.css";

import { useCloseTicket, useReplyToTicket, useTicket } from "./api";
import { CATEGORY, ticketError } from "./labels";
import styles from "./Support.module.css";
import { MessageList, PriorityLabel, StatusLabel } from "./Thread";

/** One ticket: the conversation, a reply box, and Close ticket for the person who raised it. */
export function TicketThreadPage() {
  const id = Number(useParams().id);
  const ticket = useTicket(id);
  const reply = useReplyToTicket(id);
  const close = useCloseTicket(id);
  const [body, setBody] = useState("");
  const [error, setError] = useState<string | null>(null);

  if (ticket.isPending) return <p role="status">Loading the ticket…</p>;
  if (ticket.isError) {
    return (
      <p role="alert" className={ledger.formError}>
        This ticket could not be loaded. <Link to="/help">Back to Help</Link>
      </p>
    );
  }
  const t = ticket.data;
  const closed = t.status === "closed";

  const send = (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    if (!body.trim()) return setError("Write a reply first.");
    reply.mutate(body.trim(), {
      onSuccess: () => setBody(""),
      onError: (e) => setError(ticketError(e)),
    });
  };

  return (
    <section aria-labelledby="ticket-title" className={ledger.page}>
      <p>
        <Link to="/help">Help</Link>
      </p>
      <h1 id="ticket-title" className={ledger.title}>
        {t.subject}
      </h1>
      <p className={styles.meta}>
        <span className={styles.number}>{t.number}</span>
        <StatusLabel status={t.status} />
        <PriorityLabel priority={t.priority} />
        <span>{CATEGORY[t.category]}</span>
        <span>Raised by {t.raised_by_name}</span>
        {t.assigned_admin_name ? <span>With {t.assigned_admin_name}</span> : null}
      </p>

      <MessageList messages={t.messages} />

      {closed ? (
        <p className={ledger.note}>
          This ticket is closed. Raise a new ticket if the problem returns.
        </p>
      ) : (
        <form className={styles.panel} onSubmit={send} aria-label="Reply">
          <TextAreaField
            label="Your reply"
            rows={4}
            value={body}
            maxLength={5000}
            onChange={(e) => setBody(e.target.value)}
          />
          {error ? (
            <p role="alert" className={ledger.formError}>
              {error}
            </p>
          ) : null}
          <div className={styles.buttons}>
            <Button type="submit" variant="primary" allowWhenReadOnly disabled={reply.isPending}>
              Send reply
            </Button>
            {t.can_close ? (
              <Button
                allowWhenReadOnly
                disabled={close.isPending}
                onClick={() =>
                  close.mutate(undefined, { onError: (e) => setError(ticketError(e)) })
                }
              >
                Close ticket
              </Button>
            ) : null}
          </div>
        </form>
      )}
    </section>
  );
}
