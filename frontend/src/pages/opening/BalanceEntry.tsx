import { useState, type FormEvent } from "react";

import { toFormError } from "@/api/errors";
import { useCreateOpening } from "@/api/ledger";
import { useParties } from "@/api/masters";
import type { OpeningKind } from "@/api/types";
import { Button } from "@/components/Button";
import { SelectField, TextField } from "@/components/Field";
import styles from "@/components/Ledger.module.css";

/** One row of a due or advance for a customer (with site) or a supplier. */
export function BalanceEntry({ asOf, step }: { asOf: string; step: "customers" | "suppliers" }) {
  const isCustomer = step === "customers";
  const parties = useParties("", isCustomer ? "customer" : "supplier");
  const create = useCreateOpening();
  const [partyId, setPartyId] = useState("");
  const [siteId, setSiteId] = useState("");
  const [kind, setKind] = useState<OpeningKind>(isCustomer ? "receivable" : "payable");
  const [amount, setAmount] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [added, setAdded] = useState<string | null>(null);

  const list = (parties.data?.items ?? []).filter((p) => p.is_active);
  const party = list.find((p) => String(p.id) === partyId);
  const sites = (party?.sites ?? []).filter((s) => s.is_active);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setAdded(null);
    if (!partyId) return setError(`Pick the ${isCustomer ? "customer" : "supplier"}.`);
    if (!/^\d+(\.\d{1,2})?$/.test(amount) || Number(amount) <= 0)
      return setError("Enter an amount above 0, like 12500 or 12500.50.");
    setError(null);
    try {
      await create.mutateAsync({
        kind,
        as_of: asOf,
        party_id: Number(partyId),
        site_id: isCustomer && siteId ? Number(siteId) : null,
        amount,
      });
      setAdded(`Added ${party?.name ?? "entry"}.`);
      setPartyId("");
      setSiteId("");
      setAmount("");
      document.getElementById("opening-party")?.focus();
    } catch (err) {
      setError(toFormError(err).message);
    }
  }

  return (
    <form className={styles.stack} onSubmit={(e) => void onSubmit(e)} noValidate>
      <div className={styles.entryRow}>
        <SelectField
          label="What is it"
          value={kind}
          onChange={(e) => setKind(e.target.value as OpeningKind)}
        >
          {isCustomer ? (
            <>
              <option value="receivable">Unpaid bills (they owe us)</option>
              <option value="customer_advance">Advance they paid us</option>
            </>
          ) : (
            <>
              <option value="payable">Unpaid bills (we owe them)</option>
              <option value="supplier_advance">Advance we paid them</option>
            </>
          )}
        </SelectField>
        <SelectField
          id="opening-party"
          label={isCustomer ? "Customer" : "Supplier"}
          value={partyId}
          onChange={(e) => {
            setPartyId(e.target.value);
            setSiteId("");
          }}
        >
          <option value="">{isCustomer ? "Choose a customer" : "Choose a supplier"}</option>
          {list.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </SelectField>
        {isCustomer ? (
          <SelectField label="Site" value={siteId} onChange={(e) => setSiteId(e.target.value)}>
            <option value="">Whole customer</option>
            {sites.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </SelectField>
        ) : null}
        <TextField
          label="Amount (₹)"
          inputMode="decimal"
          className={styles.amount}
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
        />
        <Button type="submit" variant="primary" disabled={create.isPending}>
          Add row
        </Button>
      </div>
      {error ? (
        <p role="alert" className={styles.formError}>
          {error}
        </p>
      ) : null}
      {added ? (
        <p role="status" className={styles.saved}>
          {added}
        </p>
      ) : null}
    </form>
  );
}
