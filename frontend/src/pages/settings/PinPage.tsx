import { useState, type FormEvent } from "react";

import { useSetPin } from "@/api/approvals";
import { toFormError } from "@/api/errors";
import { Button } from "@/components/Button";
import { TextField } from "@/components/Field";
import styles from "@/components/Ledger.module.css";

/** The owner's approval PIN: typed at the counter to allow credit, discounts and so on (G18). */
export function PinPage() {
  const set = useSetPin();
  const [password, setPassword] = useState("");
  const [pin, setPin] = useState("");
  const [again, setAgain] = useState("");
  const [error, setError] = useState<{ field: string | null; message: string } | null>(null);
  const [done, setDone] = useState(false);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setDone(false);
    if (!/^\d{4,12}$/.test(pin)) return setError({ field: "pin", message: "Use 4 to 12 digits." });
    if (pin !== again)
      return setError({ field: "again", message: "The two PINs are not the same." });
    if (!password)
      return setError({ field: "current_password", message: "Enter your password to confirm." });
    setError(null);
    try {
      await set.mutateAsync({ current_password: password, pin });
      setPassword("");
      setPin("");
      setAgain("");
      setDone(true);
    } catch (err) {
      setError(toFormError(err));
    }
  }

  return (
    <section aria-labelledby="pin-title" className={styles.stack} style={{ maxWidth: 420 }}>
      <h2 id="pin-title" style={{ margin: 0 }}>
        Approval PIN
      </h2>
      <p className={styles.sub}>
        When counter staff need your approval (credit for a customer, a discount, a lower price) you
        type this PIN on their screen. Keep it to yourself; every use is recorded with the reason.
      </p>
      <form className={styles.stack} onSubmit={(e) => void onSubmit(e)} noValidate>
        <TextField
          label="New PIN"
          type="password"
          inputMode="numeric"
          autoComplete="off"
          value={pin}
          onChange={(e) => setPin(e.target.value)}
          error={error?.field === "pin" ? error.message : null}
        />
        <TextField
          label="New PIN again"
          type="password"
          inputMode="numeric"
          autoComplete="off"
          value={again}
          onChange={(e) => setAgain(e.target.value)}
          error={error?.field === "again" ? error.message : null}
        />
        <TextField
          label="Your password"
          type="password"
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          error={error?.field === "current_password" ? error.message : null}
        />
        {error && !["pin", "again", "current_password"].includes(error.field ?? "") ? (
          <p role="alert" className={styles.formError}>
            {error.message}
          </p>
        ) : null}
        {done ? (
          <p role="status" className={styles.saved}>
            PIN saved.
          </p>
        ) : null}
        <div className={styles.actions}>
          <Button type="submit" variant="primary" disabled={set.isPending}>
            Save PIN
          </Button>
        </div>
      </form>
    </section>
  );
}
