import { useState, type KeyboardEvent } from "react";

import { useRequestApproval } from "@/api/approvals";
import { toFormError } from "@/api/errors";
import type { ApprovalAction } from "@/api/types";
import { Button } from "./Button";
import { TextField } from "./Field";
import styles from "./Ledger.module.css";

const WHAT: Record<ApprovalAction, string> = {
  credit_override: "sell on credit",
  below_cost: "sell at this price",
  discount: "give a discount or change the price",
  backdate: "back-date the bill",
};

/** The counter hands the screen to the owner, who types a PIN and a reason (G18). One approval
 * is made for each thing that needs it and is good for this bill only. */
export function ApprovalPrompt({
  actions,
  partyId,
  messages,
  onApproved,
}: {
  actions: ApprovalAction[];
  partyId: number | null;
  messages: string[];
  onApproved: (ids: number[]) => void;
}) {
  const request = useRequestApproval();
  const [pin, setPin] = useState("");
  const [reason, setReason] = useState("");
  const [error, setError] = useState<{ field: string | null; message: string } | null>(null);

  async function approve() {
    if (!/^\d{4,12}$/.test(pin))
      return setError({ field: "pin", message: "The PIN is 4 to 12 digits." });
    if (reason.trim().length < 3)
      return setError({ field: "reason", message: "Write why, so the owner's record is clear." });
    setError(null);
    try {
      const ids: number[] = [];
      for (const action of actions) {
        const made = await request.mutateAsync({
          pin,
          action,
          reason: reason.trim(),
          party_id: partyId,
        });
        ids.push(made.id);
      }
      setPin("");
      onApproved(ids);
    } catch (err) {
      setError(toFormError(err));
    }
  }

  // A plain group, not a form: it sits inside the bill form, and a nested submit would also
  // try to save the bill.
  function onKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === "Enter") {
      event.preventDefault();
      event.stopPropagation();
      void approve();
    }
  }

  return (
    <div
      className={styles.callout}
      role="group"
      aria-labelledby="approval-title"
      onKeyDown={onKeyDown}
    >
      <p id="approval-title" style={{ margin: 0, fontWeight: 600 }}>
        Owner approval needed to {actions.map((a) => WHAT[a]).join(" and ")}
      </p>
      {messages.map((m) => (
        <p key={m} style={{ margin: "4px 0" }}>
          {m}
        </p>
      ))}
      <div className={styles.inline}>
        <TextField
          label="Owner PIN"
          type="password"
          inputMode="numeric"
          autoComplete="off"
          value={pin}
          onChange={(e) => setPin(e.target.value)}
          error={error?.field === "pin" ? error.message : null}
        />
        <TextField
          label="Reason"
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          error={error?.field === "reason" ? error.message : null}
        />
        <Button variant="primary" onClick={() => void approve()} disabled={request.isPending}>
          Approve with PIN
        </Button>
      </div>
      {error && error.field !== "pin" && error.field !== "reason" ? (
        <p role="alert" className={styles.formError}>
          {error.message}
        </p>
      ) : null}
    </div>
  );
}
