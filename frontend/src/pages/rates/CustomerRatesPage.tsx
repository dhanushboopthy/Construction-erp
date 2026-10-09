import { useState, type FormEvent } from "react";

import { toFormError } from "@/api/errors";
import { useItems, useParties } from "@/api/masters";
import { useCreateCustomerRate, useCustomerRates, useEndCustomerRate } from "@/api/rates";
import { Button } from "@/components/Button";
import { SelectField, TextField } from "@/components/Field";
import styles from "@/components/Ledger.module.css";
import { trimDecimal } from "@/lib/format";
import { unitNames } from "@/pages/items/itemLabels";

function todayISO(): string {
  const d = new Date();
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
}

/** An agreed rate for one customer and item, for a period. It beats the daily rate (B3). */
export function CustomerRatesPage() {
  const list = useCustomerRates();
  const create = useCreateCustomerRate();
  const end = useEndCustomerRate();
  const parties = useParties("", "customer");
  const items = useItems("", "");
  const [partyId, setPartyId] = useState("");
  const [itemId, setItemId] = useState("");
  const [unit, setUnit] = useState("");
  const [rate, setRate] = useState("");
  const [from, setFrom] = useState(todayISO());
  const [to, setTo] = useState("");
  const [error, setError] = useState<{ field: string | null; message: string } | null>(null);

  const customers = (parties.data?.items ?? []).filter((p) => p.is_active);
  const itemList = (items.data?.items ?? []).filter((i) => i.is_active);
  const item = itemList.find((i) => String(i.id) === itemId);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (!partyId || !itemId)
      return setError({ field: null, message: "Pick the customer and the item." });
    if (!/^\d+(\.\d{1,4})?$/.test(rate))
      return setError({ field: "rate", message: "Enter the agreed rate, like 54500." });
    if (to && to < from)
      return setError({
        field: "valid_to",
        message: "The end date cannot be before the start date.",
      });
    setError(null);
    try {
      await create.mutateAsync({
        party_id: Number(partyId),
        item_id: Number(itemId),
        rate,
        unit: unit || item?.units[0]?.unit || item?.base_unit || null,
        valid_from: from,
        valid_to: to || null,
      });
      setRate("");
      setTo("");
    } catch (err) {
      setError(toFormError(err));
    }
  }

  return (
    <div className={styles.stack}>
      <form
        className={styles.entryRow}
        onSubmit={(e) => void onSubmit(e)}
        noValidate
        aria-label="New customer rate"
      >
        <SelectField label="Customer" value={partyId} onChange={(e) => setPartyId(e.target.value)}>
          <option value="">Choose a customer</option>
          {customers.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </SelectField>
        <SelectField
          label="Item"
          value={itemId}
          onChange={(e) => {
            setItemId(e.target.value);
            setUnit("");
          }}
        >
          <option value="">Choose an item</option>
          {itemList.map((i) => (
            <option key={i.id} value={i.id}>
              {i.name}
            </option>
          ))}
        </SelectField>
        <SelectField
          label="Rate per"
          value={unit || item?.units[0]?.unit || item?.base_unit || ""}
          onChange={(e) => setUnit(e.target.value)}
        >
          {item ? (
            unitNames(item).map((u) => <option key={u}>{u}</option>)
          ) : (
            <option value="">—</option>
          )}
        </SelectField>
        <TextField
          label="Agreed rate (₹)"
          inputMode="decimal"
          className={styles.amount}
          value={rate}
          onChange={(e) => setRate(e.target.value)}
          error={error?.field === "rate" ? error.message : null}
        />
        <TextField
          label="From"
          type="date"
          value={from}
          onChange={(e) => setFrom(e.target.value)}
          error={error?.field === "valid_from" ? error.message : null}
        />
        <TextField
          label="Until"
          type="date"
          value={to}
          onChange={(e) => setTo(e.target.value)}
          error={error?.field === "valid_to" ? error.message : null}
          hint="Blank = no end date."
        />
        <Button type="submit" variant="primary" disabled={create.isPending}>
          Add rate
        </Button>
      </form>
      {error && !["rate", "valid_from", "valid_to"].includes(error.field ?? "") ? (
        <p role="alert" className={styles.formError}>
          {error.message}
        </p>
      ) : null}
      <div className={styles.tableWrap}>
        {list.data && list.data.length === 0 ? (
          <p className={styles.empty}>No customer rates yet. Everyone pays the daily rate.</p>
        ) : null}
        {list.data && list.data.length > 0 ? (
          <table className={styles.table}>
            <thead>
              <tr>
                <th scope="col">Customer</th>
                <th scope="col">Item</th>
                <th scope="col" className="num">
                  Rate (₹)
                </th>
                <th scope="col">Per</th>
                <th scope="col">From</th>
                <th scope="col">Until</th>
                <th scope="col">Status</th>
                <th scope="col">
                  <span className="visually-hidden">Actions</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {list.data.map((r) => (
                <tr key={r.id} className={r.is_active ? "" : styles.inactive}>
                  <td>{r.party_name}</td>
                  <td>{r.item_name}</td>
                  <td className="num">{trimDecimal(r.entered_rate)}</td>
                  <td>{r.entered_unit}</td>
                  <td>{r.valid_from}</td>
                  <td>{r.valid_to ?? "No end"}</td>
                  <td className={styles.status}>
                    <span className={r.is_active ? styles.statusActive : styles.statusInactive}>
                      {r.is_active ? "In force" : "Stopped"}
                    </span>
                  </td>
                  <td>
                    {r.is_active ? (
                      <Button
                        variant="quiet"
                        aria-label={`Stop rate for ${r.party_name}, ${r.item_name}`}
                        onClick={() =>
                          void end.mutateAsync({ id: r.id, body: { is_active: false } })
                        }
                      >
                        Stop
                      </Button>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : null}
      </div>
    </div>
  );
}
