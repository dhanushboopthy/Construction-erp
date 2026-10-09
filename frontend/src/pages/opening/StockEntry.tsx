import { useState, type FormEvent } from "react";

import { toFormError } from "@/api/errors";
import { useCreateOpening } from "@/api/ledger";
import { useItems } from "@/api/masters";
import { useLocations } from "@/api/setup";
import { Button } from "@/components/Button";
import { SelectField, TextField } from "@/components/Field";
import styles from "@/components/Ledger.module.css";

/** One row of opening stock: item, place, quantity and cost per base unit. */
export function StockEntry({ asOf }: { asOf: string }) {
  const items = useItems("", "");
  const locations = useLocations();
  const create = useCreateOpening();
  const [itemId, setItemId] = useState("");
  const [locationId, setLocationId] = useState("");
  const [quantity, setQuantity] = useState("");
  const [cost, setCost] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [added, setAdded] = useState<string | null>(null);

  const active = (items.data?.items ?? []).filter((i) => i.is_active);
  const item = active.find((i) => String(i.id) === itemId);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setAdded(null);
    if (!itemId || !locationId) return setError("Pick the item and the place it is kept.");
    if (!/^\d+(\.\d{1,3})?$/.test(quantity) || Number(quantity) <= 0)
      return setError("Enter the quantity, up to 3 decimals.");
    if (!/^\d+(\.\d{1,4})?$/.test(cost)) return setError("Enter the cost per unit, like 55.50.");
    setError(null);
    try {
      await create.mutateAsync({
        kind: "stock",
        as_of: asOf,
        item_id: Number(itemId),
        location_id: Number(locationId),
        quantity,
        unit_cost: cost,
      });
      setAdded(`Added ${item?.name ?? "item"}.`);
      setItemId("");
      setQuantity("");
      setCost("");
      document.getElementById("opening-item")?.focus();
    } catch (err) {
      setError(toFormError(err).message);
    }
  }

  return (
    <form className={styles.stack} onSubmit={(e) => void onSubmit(e)} noValidate>
      <div className={styles.entryRow}>
        <SelectField
          id="opening-item"
          label="Item"
          value={itemId}
          onChange={(e) => setItemId(e.target.value)}
        >
          <option value="">Choose an item</option>
          {active.map((i) => (
            <option key={i.id} value={i.id}>
              {i.name}
            </option>
          ))}
        </SelectField>
        <SelectField
          label="Kept at"
          value={locationId}
          onChange={(e) => setLocationId(e.target.value)}
        >
          <option value="">Choose a place</option>
          {(locations.data ?? []).map((l) => (
            <option key={l.id} value={l.id}>
              {l.code} {l.name}
            </option>
          ))}
        </SelectField>
        <TextField
          label={`Quantity${item ? ` (${item.base_unit})` : ""}`}
          inputMode="decimal"
          className={styles.amount}
          value={quantity}
          onChange={(e) => setQuantity(e.target.value)}
        />
        <TextField
          label={`Cost per ${item?.base_unit ?? "unit"} (₹)`}
          inputMode="decimal"
          className={styles.amount}
          value={cost}
          onChange={(e) => setCost(e.target.value)}
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
