import { useState, type FormEvent } from "react";

import { Button } from "@/components/Button";
import { SelectField, TextAreaField, TextField } from "@/components/Field";

import { useCreateTicket } from "./api";
import { CATEGORY, CATEGORY_ORDER, PRIORITY, PRIORITY_ORDER, ticketError } from "./labels";
import styles from "./Support.module.css";
import type { TicketCategory, TicketDetail, TicketPriority } from "./types";

/** Raise a ticket: what is wrong, which area, how urgent, and the details. */
export function NewTicketForm({
  onCreated,
  onCancel,
}: {
  onCreated: (ticket: TicketDetail) => void;
  onCancel: () => void;
}) {
  const create = useCreateTicket();
  const [subject, setSubject] = useState("");
  const [category, setCategory] = useState<TicketCategory>("other");
  const [priority, setPriority] = useState<TicketPriority>("normal");
  const [body, setBody] = useState("");
  const [error, setError] = useState<string | null>(null);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    if (subject.trim().length < 3) return setError("Write a subject of at least 3 letters.");
    if (!body.trim()) return setError("Describe the problem in the message.");
    create.mutate(
      { subject: subject.trim(), category, priority, body: body.trim() },
      { onSuccess: onCreated, onError: (e) => setError(ticketError(e)) },
    );
  };

  return (
    <form className={styles.panel} onSubmit={submit} aria-label="New ticket">
      <h2 className={styles.panelTitle}>New ticket</h2>
      <TextField
        label="Subject"
        value={subject}
        maxLength={200}
        autoFocus
        onChange={(e) => setSubject(e.target.value)}
      />
      <div className={styles.row}>
        <SelectField
          label="Category"
          value={category}
          onChange={(e) => setCategory(e.target.value as TicketCategory)}
        >
          {CATEGORY_ORDER.map((c) => (
            <option key={c} value={c}>
              {CATEGORY[c]}
            </option>
          ))}
        </SelectField>
        <SelectField
          label="Priority"
          value={priority}
          onChange={(e) => setPriority(e.target.value as TicketPriority)}
        >
          {PRIORITY_ORDER.map((p) => (
            <option key={p} value={p}>
              {PRIORITY[p].label}
            </option>
          ))}
        </SelectField>
      </div>
      <TextAreaField
        label="Message"
        rows={6}
        value={body}
        maxLength={5000}
        onChange={(e) => setBody(e.target.value)}
        hint="Say what you did, what you expected and what happened. Do not include passwords."
      />
      {error ? (
        <p role="alert" className={styles.meta}>
          {error}
        </p>
      ) : null}
      <div className={styles.buttons}>
        <Button type="submit" variant="primary" allowWhenReadOnly disabled={create.isPending}>
          Send ticket
        </Button>
        <Button variant="ghost" onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </form>
  );
}
