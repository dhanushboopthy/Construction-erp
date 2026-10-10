import { useState, type FormEvent } from "react";

import { toFormError } from "@/api/errors";
import { useItems } from "@/api/masters";
import { useFillRate, useLogLostSale, useLostSales } from "@/api/orders";
import { useToday } from "@/api/reports";
import { useAuth } from "@/auth/AuthContext";
import { Button } from "@/components/Button";
import { SelectField, TextField } from "@/components/Field";
import styles from "@/components/Ledger.module.css";
import { Metric } from "@/components/Metric";
import { useShops } from "@/hooks/useShops";
import { formatMoney, trimDecimal } from "@/lib/format";
import { unitNames } from "@/pages/items/itemLabels";

import tiles from "@/pages/reports/PnlPage.module.css";

/** "Asked for, out of stock" (FM10): one entry each time a customer asks for something the shop
 * cannot supply. Staff see quantities; the owner also sees what the lost sales were worth. */
export function LostSalesPage() {
  const { user } = useAuth();
  const owner = user?.role === "owner";
  const { shops, single } = useShops();
  const items = useItems("", "");
  const itemList = (items.data?.items ?? []).filter((i) => i.is_active);
  const log = useLostSales();
  const asOf = useToday().data?.as_of ?? "";
  const fill = useFillRate(asOf.slice(0, 7));
  const save = useLogLostSale();
  const [placeId, setPlaceId] = useState("");
  const [itemId, setItemId] = useState("");
  const [unit, setUnit] = useState("");
  const [quantity, setQuantity] = useState("");
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const place = placeId || (shops[0] ? String(shops[0].id) : "");
  const item = itemList.find((i) => String(i.id) === itemId);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setDone(null);
    if (!place) return setError("Pick the shop.");
    if (!itemId) return setError("Pick the item the customer asked for.");
    if (!/^\d+(\.\d{1,3})?$/.test(quantity) || Number(quantity) <= 0)
      return setError("Enter how much they asked for.");
    setError(null);
    try {
      await save.mutateAsync({
        location_id: Number(place),
        item_id: Number(itemId),
        quantity,
        unit: unit || null,
        note: note.trim() || null,
      });
      setDone(
        `Logged: ${quantity} ${unit || item?.base_unit || ""} of ${item?.name ?? "the item"}.`,
      );
      setQuantity("");
      setNote("");
    } catch (err) {
      setError(toFormError(err).message);
    }
  }

  const r = fill.data;
  return (
    <div className={styles.stack}>
      <form
        className={styles.filters}
        aria-label="Log a lost sale"
        noValidate
        onSubmit={(e) => void submit(e)}
      >
        {single ? null : (
          <SelectField label="Shop" value={place} onChange={(e) => setPlaceId(e.target.value)}>
            {shops.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </SelectField>
        )}
        <SelectField
          label="Asked for"
          value={itemId}
          onChange={(e) => {
            const it = itemList.find((x) => String(x.id) === e.target.value);
            setItemId(e.target.value);
            setUnit(it ? it.base_unit : "");
          }}
          autoFocus
        >
          <option value="">Choose an item</option>
          {itemList.map((it) => (
            <option key={it.id} value={it.id}>
              {it.name}
            </option>
          ))}
        </SelectField>
        <TextField
          label="How much"
          inputMode="decimal"
          className={styles.amount}
          value={quantity}
          onChange={(e) => setQuantity(e.target.value)}
        />
        <SelectField label="Unit" value={unit} onChange={(e) => setUnit(e.target.value)}>
          {item ? (
            unitNames(item).map((u) => <option key={u}>{u}</option>)
          ) : (
            <option value="">—</option>
          )}
        </SelectField>
        <TextField
          label="Note (optional)"
          value={note}
          maxLength={200}
          onChange={(e) => setNote(e.target.value)}
        />
        <Button type="submit" variant="primary" disabled={save.isPending}>
          Log it
        </Button>
      </form>
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

      {r ? (
        <>
          <dl className={tiles.tiles}>
            <Metric
              code="fill_rate"
              label="Lines filled"
              value={r.line_fill_rate_pct == null ? "—" : `${r.line_fill_rate_pct} %`}
              note={`${r.lines_supplied} bill lines supplied, ${r.lines_lost} asks logged this month.`}
            />
            {owner && r.lost_value != null ? (
              <Metric
                code="fill_rate_lost_value"
                label="Sales lost, at market rate"
                value={`₹${formatMoney(r.lost_value)}`}
              />
            ) : null}
          </dl>
          <div className={styles.tableWrap}>
            <table className={styles.table} aria-label="Fill rate by item">
              <thead>
                <tr>
                  <th scope="col">Item</th>
                  <th scope="col" className="num">
                    Supplied
                  </th>
                  <th scope="col" className="num">
                    Asked, not in stock
                  </th>
                  <th scope="col" className="num">
                    Fill rate
                  </th>
                  {owner ? (
                    <th scope="col" className="num">
                      Lost (₹)
                    </th>
                  ) : null}
                </tr>
              </thead>
              <tbody>
                {r.rows.map((row) => (
                  <tr key={row.item_id}>
                    <td>{row.item_name}</td>
                    <td className="num">
                      {trimDecimal(row.supplied_qty)} {row.base_unit}
                    </td>
                    <td className="num">
                      {trimDecimal(row.lost_qty)} {row.base_unit}
                    </td>
                    <td className="num">
                      {row.fill_rate_pct == null ? "—" : `${row.fill_rate_pct} %`}
                    </td>
                    {owner ? (
                      <td className="num">{row.lost_value ? formatMoney(row.lost_value) : ""}</td>
                    ) : null}
                  </tr>
                ))}
              </tbody>
            </table>
            {r.rows.length === 0 ? (
              <p className={styles.empty}>No bills or entries this month.</p>
            ) : null}
          </div>
        </>
      ) : null}

      <h2 style={{ margin: 0 }}>Last 7 days</h2>
      <div className={styles.tableWrap}>
        <table className={styles.table} aria-label="Lost sales log">
          <thead>
            <tr>
              <th scope="col">Date</th>
              <th scope="col">Item</th>
              <th scope="col" className="num">
                Quantity
              </th>
              <th scope="col">Note</th>
              <th scope="col">By</th>
              {owner ? (
                <th scope="col" className="num">
                  Value (₹)
                </th>
              ) : null}
            </tr>
          </thead>
          <tbody>
            {(log.data ?? []).map((e) => (
              <tr key={e.id}>
                <td>
                  {e.entry_date} <span className={styles.sub}>{e.location_code}</span>
                </td>
                <td>{e.item_name}</td>
                <td className="num">
                  {trimDecimal(e.quantity)} {e.unit}
                </td>
                <td>{e.note ?? ""}</td>
                <td>{e.entered_by ?? ""}</td>
                {owner ? (
                  <td className="num">{"value" in e && e.value ? formatMoney(e.value) : "—"}</td>
                ) : null}
              </tr>
            ))}
          </tbody>
        </table>
        {log.isSuccess && (log.data ?? []).length === 0 ? (
          <p className={styles.empty}>
            Nothing logged yet. Log each time a customer asks for stock you do not have.
          </p>
        ) : null}
      </div>
    </div>
  );
}
