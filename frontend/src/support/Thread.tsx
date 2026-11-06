import { StatusPill } from "@/components/StatusPill";
import { formatDateTime } from "@/lib/format";

import { PRIORITY, TICKET_STATUS } from "./labels";
import styles from "./Support.module.css";
import type { TicketMessage, TicketPriority, TicketStatus } from "./types";

/** The messages of a ticket, oldest first. Duolink's replies are marked in words as well as colour. */
export function MessageList({ messages }: { messages: TicketMessage[] }) {
  return (
    <ol className={styles.thread} aria-label="Messages">
      {messages.map((m) => (
        <li key={m.id} className={styles.message} data-kind={m.author_kind}>
          <div className={styles.messageHead}>
            <strong>{m.author_name}</strong>
            <span>{m.author_kind === "platform_admin" ? "Duolink support" : "Company"}</span>
            <time dateTime={m.created_at}>{formatDateTime(m.created_at)}</time>
          </div>
          <p className={styles.messageBody}>{m.body}</p>
        </li>
      ))}
    </ol>
  );
}

export function StatusLabel({ status }: { status: TicketStatus }) {
  const s = TICKET_STATUS[status];
  return <StatusPill tone={s.tone} label={s.label} />;
}

export function PriorityLabel({ priority }: { priority: TicketPriority }) {
  const p = PRIORITY[priority];
  return <StatusPill tone={p.tone} label={p.label} />;
}
