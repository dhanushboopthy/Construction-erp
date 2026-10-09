import { useState, type FormEvent } from "react";

import { toFormError } from "@/api/errors";
import { convertQuantity, type ItemRow } from "@/api/masters";
import { Button } from "@/components/Button";
import { SelectField, TextField } from "@/components/Field";
import styles from "@/components/Ledger.module.css";

import { unitNames } from "./itemLabels";

export function Converter({ item }: { item: ItemRow }) {
  const names = unitNames(item);
  const [quantity, setQuantity] = useState("1");
  const [from, setFrom] = useState(names[1] ?? names[0] ?? "");
  const [to, setTo] = useState(item.base_unit);
  const [result, setResult] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setResult(null);
    if (!/^\d+(\.\d+)?$/.test(quantity)) {
      setError("Enter a number like 2.5.");
      return;
    }
    try {
      const out = await convertQuantity(item.id, quantity, from, to);
      setResult(`${quantity} ${from} = ${out.result} ${to}`);
    } catch (err) {
      setError(toFormError(err).message);
    }
  }

  return (
    <form className={styles.subsection} onSubmit={(e) => void onSubmit(e)} noValidate>
      <h3>Convert units</h3>
      <div className={styles.inline}>
        <TextField
          label="Quantity"
          inputMode="decimal"
          className={styles.amount}
          value={quantity}
          onChange={(e) => setQuantity(e.target.value)}
        />
        <SelectField label="From" value={from} onChange={(e) => setFrom(e.target.value)}>
          {names.map((n) => (
            <option key={n}>{n}</option>
          ))}
        </SelectField>
        <SelectField label="To" value={to} onChange={(e) => setTo(e.target.value)}>
          {names.map((n) => (
            <option key={n}>{n}</option>
          ))}
        </SelectField>
      </div>
      <div className={styles.actions}>
        <Button type="submit">Convert</Button>
      </div>
      {result ? (
        <p role="status" className={styles.resultBox}>
          {result}
        </p>
      ) : null}
      {error ? (
        <p role="alert" className={styles.formError}>
          {error}
        </p>
      ) : null}
    </form>
  );
}
