import { useState, type FormEvent } from "react";
import { Link } from "react-router";

import { useBookRebate, useCreateScheme, useSchemes } from "@/api/documents";
import { toFormError } from "@/api/errors";
import { useItems, useParties } from "@/api/masters";
import type { ItemCategory } from "@/api/types";
import { useAuth } from "@/auth/AuthContext";
import { Button } from "@/components/Button";
import { SelectField, TextField } from "@/components/Field";
import styles from "@/components/Ledger.module.css";
import { formatMoney, trimDecimal } from "@/lib/format";

const RULE_LABEL = {
  percent: "% of goods bought",
  per_unit: "₹ for each unit bought",
  flat: "Flat amount",
} as const;

const CATEGORIES: ItemCategory[] = ["tmt", "pipe", "cement", "wire", "angle", "channel", "other"];

/** Supplier target schemes: buy a volume in a period, earn a rebate (B15). */
export function SchemesPage() {
  const { user } = useAuth();
  const owner = user?.role === "owner";
  const schemes = useSchemes();
  const create = useCreateScheme();
  const book = useBookRebate();
  const parties = useParties("");
  const items = useItems("", "");
  const [supplier, setSupplier] = useState("");
  const [name, setName] = useState("");
  const [target, setTarget] = useState("");
  const [by, setBy] = useState("item");
  const [itemId, setItemId] = useState("");
  const [category, setCategory] = useState<ItemCategory>("tmt");
  const [unit, setUnit] = useState("kg");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [rule, setRule] = useState<keyof typeof RULE_LABEL>("percent");
  const [value, setValue] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);

  const suppliers = (parties.data?.items ?? []).filter((p) => p.type !== "customer");
  const rows = schemes.data ?? [];

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setDone(null);
    if (!supplier || name.trim().length < 2)
      return setError("Pick the supplier and name the scheme.");
    if (!/^\d+(\.\d{1,3})?$/.test(target) || Number(target) <= 0)
      return setError("Enter the target quantity.");
    if (by === "item" && !itemId) return setError("Pick the item.");
    if (!start || !end) return setError("Give the start and end dates.");
    if (!/^\d+(\.\d+)?$/.test(value)) return setError("Enter the rebate value.");
    setError(null);
    try {
      await create.mutateAsync({
        party_id: Number(supplier),
        name: name.trim(),
        item_id: by === "item" ? Number(itemId) : null,
        category: by === "category" ? category : null,
        unit: by === "category" ? unit.trim() : null,
        target_qty: target,
        period_start: start,
        period_end: end,
        rebate_rule: rule,
        rebate_value: value,
      });
      setDone("Scheme saved.");
      setName("");
      setTarget("");
      setValue("");
    } catch (err) {
      setError(toFormError(err).message);
    }
  }

  async function bookRebate(id: number) {
    setError(null);
    setDone(null);
    try {
      const made = await book.mutateAsync(id);
      setDone(
        `Rebate of ₹${formatMoney(made.rebate_amount ?? "0")} booked as a credit from ${made.party_name}.`,
      );
    } catch (err) {
      setError(toFormError(err).message);
    }
  }

  return (
    <section aria-labelledby="schemes-title" className={styles.page}>
      <div className={styles.toolbar}>
        <h1 id="schemes-title" className={styles.title}>
          Supplier schemes
        </h1>
        <Link to="/purchases">Back to purchases</Link>
      </div>
      {owner ? (
        <form className={styles.stack} onSubmit={(e) => void onSubmit(e)} aria-label="Add scheme">
          <div className={styles.inline}>
            <SelectField
              label="Supplier"
              value={supplier}
              onChange={(e) => setSupplier(e.target.value)}
            >
              <option value="">Choose</option>
              {suppliers.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </SelectField>
            <TextField label="Scheme name" value={name} onChange={(e) => setName(e.target.value)} />
            <SelectField label="Counts" value={by} onChange={(e) => setBy(e.target.value)}>
              <option value="item">One item</option>
              <option value="category">A whole category</option>
            </SelectField>
            {by === "item" ? (
              <SelectField label="Item" value={itemId} onChange={(e) => setItemId(e.target.value)}>
                <option value="">Choose</option>
                {(items.data?.items ?? []).map((i) => (
                  <option key={i.id} value={i.id}>
                    {i.name}
                  </option>
                ))}
              </SelectField>
            ) : (
              <>
                <SelectField
                  label="Category"
                  value={category}
                  onChange={(e) => setCategory(e.target.value as ItemCategory)}
                >
                  {CATEGORIES.map((c) => (
                    <option key={c} value={c}>
                      {c}
                    </option>
                  ))}
                </SelectField>
                <TextField
                  label="Counted in (kg, bag...)"
                  value={unit}
                  onChange={(e) => setUnit(e.target.value)}
                />
              </>
            )}
          </div>
          <div className={styles.inline}>
            <TextField
              label="Target quantity"
              inputMode="decimal"
              value={target}
              onChange={(e) => setTarget(e.target.value)}
            />
            <TextField
              label="From"
              type="date"
              value={start}
              onChange={(e) => setStart(e.target.value)}
            />
            <TextField
              label="To"
              type="date"
              value={end}
              onChange={(e) => setEnd(e.target.value)}
            />
            <SelectField
              label="Rebate"
              value={rule}
              onChange={(e) => setRule(e.target.value as keyof typeof RULE_LABEL)}
            >
              {(Object.keys(RULE_LABEL) as (keyof typeof RULE_LABEL)[]).map((r) => (
                <option key={r} value={r}>
                  {RULE_LABEL[r]}
                </option>
              ))}
            </SelectField>
            <TextField
              label="Rebate value"
              inputMode="decimal"
              value={value}
              onChange={(e) => setValue(e.target.value)}
            />
            <Button type="submit" variant="primary" disabled={create.isPending}>
              Save scheme
            </Button>
          </div>
        </form>
      ) : null}
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
      {schemes.isSuccess && rows.length === 0 ? (
        <p className={styles.empty}>No schemes yet.</p>
      ) : null}
      {rows.length > 0 ? (
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th scope="col">Scheme</th>
                <th scope="col">Supplier</th>
                <th scope="col">Period</th>
                <th scope="col" className="num">
                  Bought / target
                </th>
                <th scope="col" className="num">
                  Done
                </th>
                <th scope="col">Rebate</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((s) => (
                <tr key={s.id}>
                  <td>
                    {s.name}
                    <br />
                    <span className={styles.sub}>{s.item_name ?? `All ${s.category}`}</span>
                  </td>
                  <td>{s.party_name}</td>
                  <td>
                    {s.period_start} to {s.period_end}
                  </td>
                  <td className="num">
                    {trimDecimal(s.achieved)} / {trimDecimal(s.target_qty)} {s.unit}
                  </td>
                  <td className="num">
                    {s.pct}%{s.alert ? " · nearly there" : ""}
                  </td>
                  <td>
                    {s.rebate_booked_at ? (
                      `Booked ₹${formatMoney(s.rebate_amount ?? "0")}`
                    ) : s.reached ? (
                      <>
                        ₹{formatMoney(s.projected_rebate)} earned{" "}
                        {owner ? (
                          <Button variant="quiet" onClick={() => void bookRebate(s.id)}>
                            Book rebate for {s.name}
                          </Button>
                        ) : null}
                      </>
                    ) : (
                      `${trimDecimal(s.remaining)} ${s.unit} to go`
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </section>
  );
}
