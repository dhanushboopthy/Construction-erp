import { useState, type FormEvent } from "react";

import { toFormError } from "@/api/errors";
import { useCostComponents, useCreateComponent, useUpdateComponent } from "@/api/purchasing";
import type { ChargeBasis } from "@/api/types";
import { Button } from "@/components/Button";
import { SelectField, TextField } from "@/components/Field";
import styles from "@/components/Ledger.module.css";
import { trimDecimal } from "@/lib/format";

const BASIS: { value: ChargeBasis; label: string; hint: string }[] = [
  { value: "per_ton", label: "Per ton", hint: "Unloading at ₹250 a ton" },
  { value: "per_base_unit", label: "Per kg, bag or piece", hint: "Unloading at ₹3 a bag" },
  { value: "per_trip", label: "Per trip", hint: "Truck rent for the load" },
  { value: "flat", label: "Flat", hint: "Weighbridge ₹150 a weighing" },
];
const basisLabel = (b: ChargeBasis) => BASIS.find((x) => x.value === b)?.label ?? b;

/** The kinds of charge a purchase line can carry (rule B2). Amounts here are suggestions. */
export function ChargeTypesPage() {
  const query = useCostComponents(true);
  const create = useCreateComponent();
  const update = useUpdateComponent();
  const [name, setName] = useState("");
  const [basis, setBasis] = useState<ChargeBasis>("flat");
  const [amount, setAmount] = useState("0");
  const [error, setError] = useState<{ field: string | null; message: string } | null>(null);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (!name.trim()) return setError({ field: "name", message: "Enter a name, e.g. Crane hire." });
    if (!/^\d+(\.\d{1,2})?$/.test(amount))
      return setError({ field: "amount", message: "Enter an amount like 250." });
    setError(null);
    try {
      await create.mutateAsync({ name: name.trim(), basis, default_amount: amount });
      setName("");
      setAmount("0");
    } catch (err) {
      setError(toFormError(err));
    }
  }

  return (
    <section aria-labelledby="charges-title" className={styles.stack}>
      <div className={styles.toolbar}>
        <h2 id="charges-title">Charge types</h2>
      </div>
      <p className={styles.sub}>
        These are the extra costs you can add to a purchase line. The amount is only suggested; each
        purchase stores what was really paid.
      </p>
      <form className={styles.entryRow} onSubmit={(e) => void onSubmit(e)} noValidate>
        <TextField
          label="Name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          error={error?.field === "name" ? error.message : null}
        />
        <SelectField
          label="Charged"
          value={basis}
          onChange={(e) => setBasis(e.target.value as ChargeBasis)}
          hint={BASIS.find((b) => b.value === basis)?.hint}
        >
          {BASIS.map((b) => (
            <option key={b.value} value={b.value}>
              {b.label}
            </option>
          ))}
        </SelectField>
        <TextField
          label="Usual amount (₹)"
          inputMode="decimal"
          className={styles.amount}
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
          error={error?.field === "amount" ? error.message : null}
        />
        <Button type="submit" variant="primary" disabled={create.isPending}>
          Add charge type
        </Button>
      </form>
      {error && error.field !== "name" && error.field !== "amount" ? (
        <p role="alert" className={styles.formError}>
          {error.message}
        </p>
      ) : null}
      <div className={styles.tableWrap}>
        {query.isPending ? (
          <p role="status" className={styles.empty}>
            Loading…
          </p>
        ) : null}
        {query.data && query.data.length === 0 ? (
          <p className={styles.empty}>No charge types yet. Add the first above.</p>
        ) : null}
        {query.data && query.data.length > 0 ? (
          <table className={styles.table}>
            <thead>
              <tr>
                <th scope="col">Name</th>
                <th scope="col">Charged</th>
                <th scope="col" className="num">
                  Usual amount (₹)
                </th>
                <th scope="col">Status</th>
                <th scope="col">
                  <span className="visually-hidden">Actions</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {query.data.map((c) => (
                <tr key={c.id} className={c.is_active ? "" : styles.inactive}>
                  <td>{c.name}</td>
                  <td>{basisLabel(c.basis)}</td>
                  <td className="num">{trimDecimal(c.default_amount)}</td>
                  <td className={styles.status}>
                    <span className={c.is_active ? styles.statusActive : styles.statusInactive}>
                      {c.is_active ? "In use" : "Hidden"}
                    </span>
                  </td>
                  <td>
                    <Button
                      variant="quiet"
                      aria-label={`${c.is_active ? "Hide" : "Show"} ${c.name}`}
                      onClick={() =>
                        void update.mutateAsync({ id: c.id, body: { is_active: !c.is_active } })
                      }
                    >
                      {c.is_active ? "Hide" : "Show"}
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : null}
      </div>
    </section>
  );
}
