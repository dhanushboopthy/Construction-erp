import { useState, type FormEvent } from "react";
import { Link, useParams } from "react-router";

import { Button } from "@/components/Button";
import { SelectField, TextAreaField } from "@/components/Field";
import ledger from "@/components/Ledger.module.css";
import {
  CATEGORY,
  PRIORITY,
  PRIORITY_ORDER,
  TICKET_STATUS,
  TICKET_STATUS_ORDER,
  ticketError,
} from "@/support/labels";
import styles from "@/support/Support.module.css";
import { MessageList, PriorityLabel, StatusLabel } from "@/support/Thread";
import type { TicketPriority, TicketStatus } from "@/support/types";

import { useAdminTicket, useAdminTicketPatch, useAdminTicketReply, useStaff } from "../api";
import { useAdminAuth } from "../AdminAuthContext";

/** One ticket for Duolink staff: the conversation, a reply, and status, priority and owner. */
export function SupportThreadPage() {
  const id = Number(useParams().id);
  const { admin, isSuperAdmin } = useAdminAuth();
  const ticket = useAdminTicket(id);
  const reply = useAdminTicketReply(id);
  const patch = useAdminTicketPatch(id);
  // The staff list is a Super Admin's; Support gets only "Assign to me".
  const staff = useStaff(isSuperAdmin);
  const [body, setBody] = useState("");
  const [replyStatus, setReplyStatus] = useState<TicketStatus | "">("");
  const [error, setError] = useState<string | null>(null);

  if (ticket.isPending) return <p role="status">Loading the ticket…</p>;
  if (ticket.isError) {
    return (
      <p role="alert" className={ledger.formError}>
        This ticket could not be loaded. <Link to="/admin/support">Back to Support</Link>
      </p>
    );
  }
  const t = ticket.data;
  const change = (data: Parameters<typeof patch.mutate>[0]) => {
    setError(null);
    patch.mutate(data, { onError: (e) => setError(ticketError(e)) });
  };

  const send = (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    if (!body.trim() && !replyStatus) return setError("Write a reply or choose a status.");
    reply.mutate(
      {
        ...(body.trim() ? { body: body.trim() } : {}),
        ...(replyStatus ? { status: replyStatus } : {}),
      },
      {
        onSuccess: () => {
          setBody("");
          setReplyStatus("");
        },
        onError: (e) => setError(ticketError(e)),
      },
    );
  };

  return (
    <section aria-labelledby="ticket-title" className={ledger.page}>
      <p>
        <Link to="/admin/support">Support</Link>
      </p>
      <h1 id="ticket-title" className={ledger.title}>
        {t.subject}
      </h1>
      <p className={styles.meta}>
        <span className={styles.number}>{t.number}</span>
        <StatusLabel status={t.status} />
        <PriorityLabel priority={t.priority} />
        <span>{CATEGORY[t.category]}</span>
        <Link to={`/admin/companies/${t.tenant_id}?tab=support`}>{t.tenant_name}</Link>
        <span>Raised by {t.raised_by_name}</span>
        <span>{t.assigned_admin_name ? `With ${t.assigned_admin_name}` : "Unassigned"}</span>
      </p>

      <div className={styles.panel} role="group" aria-label="Handle ticket">
        <div className={styles.controls}>
          <SelectField
            label="Status"
            value={t.status}
            disabled={patch.isPending}
            onChange={(e) => change({ status: e.target.value as TicketStatus })}
          >
            {TICKET_STATUS_ORDER.map((s) => (
              <option key={s} value={s}>
                {TICKET_STATUS[s].label}
              </option>
            ))}
          </SelectField>
          <SelectField
            label="Priority"
            value={t.priority}
            disabled={patch.isPending}
            onChange={(e) => change({ priority: e.target.value as TicketPriority })}
          >
            {PRIORITY_ORDER.map((p) => (
              <option key={p} value={p}>
                {PRIORITY[p].label}
              </option>
            ))}
          </SelectField>
          {isSuperAdmin ? (
            <SelectField
              label="Assigned to"
              value={t.assigned_admin_id === null ? "" : String(t.assigned_admin_id)}
              disabled={patch.isPending}
              onChange={(e) =>
                change({ assigned_admin_id: e.target.value ? Number(e.target.value) : null })
              }
            >
              <option value="">Unassigned</option>
              {(staff.data ?? [])
                .filter((m) => m.is_active)
                .map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.full_name}
                  </option>
                ))}
            </SelectField>
          ) : null}
          {admin && t.assigned_admin_id !== admin.id ? (
            <Button
              disabled={patch.isPending}
              onClick={() => change({ assigned_admin_id: admin.id })}
            >
              Assign to me
            </Button>
          ) : null}
        </div>
      </div>

      <MessageList messages={t.messages} />

      <form className={styles.panel} onSubmit={send} aria-label="Reply">
        <TextAreaField
          label="Your reply"
          rows={4}
          value={body}
          maxLength={5000}
          onChange={(e) => setBody(e.target.value)}
          hint="Replying moves an open ticket to Waiting on company unless you choose another status."
        />
        <SelectField
          label="Set status with this reply"
          value={replyStatus}
          onChange={(e) => setReplyStatus(e.target.value as TicketStatus | "")}
        >
          <option value="">Leave to the default</option>
          {TICKET_STATUS_ORDER.map((s) => (
            <option key={s} value={s}>
              {TICKET_STATUS[s].label}
            </option>
          ))}
        </SelectField>
        {error ? (
          <p role="alert" className={ledger.formError}>
            {error}
          </p>
        ) : null}
        <div className={styles.buttons}>
          <Button type="submit" variant="primary" disabled={reply.isPending}>
            Send reply
          </Button>
        </div>
      </form>
    </section>
  );
}
