import { useState, type FormEvent } from "react";

import { toFormError } from "@/api/errors";
import { useSupplierPayment } from "@/api/purchasing";
import { useLocations } from "@/api/setup";
import type { Party, PaymentMode } from "@/api/types";
import { useAuth } from "@/auth/AuthContext";
import { Button } from "@/components/Button";
import { SelectField, TextField } from "@/components/Field";
import styles from "@/components/Ledger.module.css";

function todayISO(): string {
  const d = new Date();
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
}

/** Pay a supplier or give an advance (owner only). Sending twice never pays twice: each form
 * carries one Idempotency-Key until it succeeds (G19). */
export function SupplierPayment({ party }: { party: Party }) {
  const { user } = useAuth();
  const locations = useLocations();
  const pay = useSupplierPayment();
  const [amount, setAmount] = useState("");
  const [mode, setMode] = useState<PaymentMode>("bank");
  const [reference, setReference] = useState("");
  const [date, setDate] = useState(todayISO());
  const [locationId, setLocationId] = useState("");
  const [key, setKey] = useState(() => crypto.randomUUID());
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);

  if (user?.role !== "owner" || party.type === "customer") return null;

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setDone(null);
    if (!/^\d+(\.\d{1,2})?$/.test(amount) || Number(amount) <= 0)
      return setError("Enter the amount paid, like 50000.");
    if (!locationId) return setError("Pick the shop or godown the money went from.");
    setError(null);
    try {
      const paid = await pay.mutateAsync({
        key,
        body: {
          direction: "paid",
          party_id: party.id,
          location_id: Number(locationId),
          amount,
          mode,
          reference: reference.trim() || null,
          payment_date: date,
        },
      });
      setDone(
        `Recorded ${paid.number}. Bills are settled oldest first; any extra stays as an advance.`,
      );
      setAmount("");
      setReference("");
      setKey(crypto.randomUUID());
    } catch (err) {
      setError(toFormError(err).message);
    }
  }

  return (
    <form
      className={styles.subsection}
      onSubmit={(e) => void onSubmit(e)}
      noValidate
      aria-labelledby={`pay-${party.id}`}
    >
      <h3 id={`pay-${party.id}`}>Pay this supplier</h3>
      <TextField
        label="Amount (₹)"
        inputMode="decimal"
        className={styles.amount}
        value={amount}
        onChange={(e) => setAmount(e.target.value)}
      />
      <SelectField
        label="Paid by"
        value={mode}
        onChange={(e) => setMode(e.target.value as PaymentMode)}
      >
        <option value="bank">Bank transfer</option>
        <option value="upi">UPI</option>
        <option value="cash">Cash</option>
      </SelectField>
      <TextField
        label="Reference"
        value={reference}
        onChange={(e) => setReference(e.target.value)}
        hint="UTR or UPI reference."
      />
      <TextField label="Date" type="date" value={date} onChange={(e) => setDate(e.target.value)} />
      <SelectField label="From" value={locationId} onChange={(e) => setLocationId(e.target.value)}>
        <option value="">Choose a place</option>
        {(locations.data ?? []).map((l) => (
          <option key={l.id} value={l.id}>
            {l.code} {l.name}
          </option>
        ))}
      </SelectField>
      {error ? (
        <p role="alert" className={styles.formError}>
          {error}
        </p>
      ) : null}
      {done ? (
        <p role="status" className={styles.saved}>
          {done}
        </p>
      ) : null}
      <div className={styles.actions}>
        <Button type="submit" variant="primary" disabled={pay.isPending}>
          Record payment
        </Button>
      </div>
    </form>
  );
}
