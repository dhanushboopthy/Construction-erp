import { Fragment, useState, type FormEvent } from "react";
import { Link } from "react-router";

import { toFormError } from "@/api/errors";
import { useItems, useParties } from "@/api/masters";
import { useCreateOrder, useOrders, useReceiveGoods } from "@/api/orders";
import { useLocations } from "@/api/setup";
import type { PurchaseOrderRow } from "@/api/types";
import { useAuth } from "@/auth/AuthContext";
import { Button } from "@/components/Button";
import { SelectField, TextField } from "@/components/Field";
import styles from "@/components/Ledger.module.css";
import { formatMoney, trimDecimal } from "@/lib/format";
import { unitNames } from "@/pages/items/itemLabels";

const DECIMAL = /^\d+(\.\d+)?$/;
const STATUS: Record<string, string> = {
  open: "Waiting for goods",
  received: "Received, not fully billed",
  billed: "Billed",
};

interface Row {
  itemId: string;
  unit: string;
  quantity: string;
  rate: string;
}
const EMPTY: Row = { itemId: "", unit: "", quantity: "", rate: "" };

function NewOrder({ onDone }: { onDone: (message: string) => void }) {
  const suppliers = useParties("", "supplier");
  const locations = useLocations();
  const items = useItems("", "");
  const create = useCreateOrder();
  const [supplierId, setSupplierId] = useState("");
  const [placeId, setPlaceId] = useState("");
  const [expected, setExpected] = useState("");
  const [rows, setRows] = useState<Row[]>([EMPTY]);
  const [error, setError] = useState<string | null>(null);
  const itemList = (items.data?.items ?? []).filter((i) => i.is_active);
  const setRow = (i: number, patch: Partial<Row>) =>
    setRows((rs) => rs.map((r, j) => (j === i ? { ...r, ...patch } : r)));

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!supplierId || !placeId) return setError("Pick the supplier and where the goods go.");
    if (rows.some((r) => !r.itemId || !DECIMAL.test(r.quantity) || !DECIMAL.test(r.rate)))
      return setError("Every line needs an item, a quantity and the agreed rate.");
    setError(null);
    try {
      const made = await create.mutateAsync({
        supplier_id: Number(supplierId),
        location_id: Number(placeId),
        expected_date: expected || null,
        lines: rows.map((r) => ({
          item_id: Number(r.itemId),
          unit: r.unit || itemList.find((i) => String(i.id) === r.itemId)?.base_unit || "",
          quantity: r.quantity,
          rate: r.rate,
        })),
      });
      setRows([EMPTY]);
      onDone(`${made.number} placed.`);
    } catch (err) {
      setError(toFormError(err).message);
    }
  }

  return (
    <form
      className={styles.stack}
      aria-label="New order"
      noValidate
      onSubmit={(e) => void submit(e)}
    >
      <div className={styles.filters}>
        <SelectField
          label="Supplier"
          value={supplierId}
          onChange={(e) => setSupplierId(e.target.value)}
        >
          <option value="">Choose a supplier</option>
          {(suppliers.data?.items ?? [])
            .filter((s) => s.is_active)
            .map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
        </SelectField>
        <SelectField
          label="Goods go to"
          value={placeId}
          onChange={(e) => setPlaceId(e.target.value)}
        >
          <option value="">Choose a place</option>
          {(locations.data ?? [])
            .filter((l) => l.is_active)
            .map((l) => (
              <option key={l.id} value={l.id}>
                {l.code} {l.name}
              </option>
            ))}
        </SelectField>
        <TextField
          label="Expected on"
          type="date"
          value={expected}
          onChange={(e) => setExpected(e.target.value)}
        />
      </div>
      {rows.map((r, i) => {
        const item = itemList.find((x) => String(x.id) === r.itemId);
        return (
          <div key={i} className={styles.filters}>
            <SelectField
              label={`Item ${i + 1}`}
              value={r.itemId}
              onChange={(e) => {
                const it = itemList.find((x) => String(x.id) === e.target.value);
                setRow(i, {
                  itemId: e.target.value,
                  unit: it ? (it.units[0]?.unit ?? it.base_unit) : "",
                });
              }}
            >
              <option value="">Choose an item</option>
              {itemList.map((it) => (
                <option key={it.id} value={it.id}>
                  {it.name}
                </option>
              ))}
            </SelectField>
            <SelectField
              label="Unit"
              value={r.unit}
              onChange={(e) => setRow(i, { unit: e.target.value })}
            >
              {item ? (
                unitNames(item).map((u) => <option key={u}>{u}</option>)
              ) : (
                <option value="">—</option>
              )}
            </SelectField>
            <TextField
              label="Quantity"
              inputMode="decimal"
              className={styles.amount}
              value={r.quantity}
              onChange={(e) => setRow(i, { quantity: e.target.value })}
            />
            <TextField
              label={`Agreed rate per ${r.unit || "unit"} (₹)`}
              inputMode="decimal"
              className={styles.amount}
              value={r.rate}
              onChange={(e) => setRow(i, { rate: e.target.value })}
            />
            <Button
              variant="quiet"
              aria-label={`Remove line ${i + 1}`}
              disabled={rows.length === 1}
              onClick={() => setRows((rs) => rs.filter((_, j) => j !== i))}
            >
              Remove
            </Button>
          </div>
        );
      })}
      {error ? (
        <p role="alert" className={styles.formError}>
          {error}
        </p>
      ) : null}
      <div className={styles.actions}>
        <Button onClick={() => setRows((rs) => [...rs, EMPTY])}>Add line</Button>
        <Button type="submit" variant="primary" disabled={create.isPending}>
          Place order
        </Button>
      </div>
    </form>
  );
}

function Receive({
  order,
  onDone,
}: {
  order: PurchaseOrderRow;
  onDone: (message: string) => void;
}) {
  const receive = useReceiveGoods();
  const [quantities, setQuantities] = useState<Record<number, string>>({});
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    const lines = Object.entries(quantities)
      .filter(([, q]) => q.trim() !== "")
      .map(([id, q]) => ({ order_line_id: Number(id), quantity: q.trim() }));
    if (
      lines.length === 0 ||
      lines.some((l) => !DECIMAL.test(l.quantity) || Number(l.quantity) <= 0)
    )
      return setError("Enter what arrived for at least one item.");
    setError(null);
    try {
      const made = await receive.mutateAsync({ orderId: order.id, body: { lines } });
      setQuantities({});
      onDone(`${made.number} recorded. Stock is added when the supplier's bill is entered.`);
    } catch (err) {
      setError(toFormError(err).message);
    }
  }

  return (
    <form
      className={styles.filters}
      aria-label={`Receive goods for ${order.number}`}
      onSubmit={(e) => void submit(e)}
    >
      {order.lines.map((l) => (
        <TextField
          key={l.id}
          label={`Arrived: ${l.item_name} (${l.unit})`}
          inputMode="decimal"
          className={styles.amount}
          value={quantities[l.id] ?? ""}
          onChange={(e) => setQuantities((q) => ({ ...q, [l.id]: e.target.value }))}
        />
      ))}
      <Button type="submit" variant="primary" disabled={receive.isPending}>
        Record goods received
      </Button>
      {error ? (
        <p role="alert" className={styles.formError}>
          {error}
        </p>
      ) : null}
    </form>
  );
}

/** Purchase orders (FM10): placed by the owner at an agreed rate; the goods that arrive are
 * recorded here by the shop. A supplier bill entered against an order is checked against both. */
export function OrdersPage() {
  const { user } = useAuth();
  const owner = user?.role === "owner";
  const canReceive = owner || user?.role === "counter";
  const [openOnly, setOpenOnly] = useState(true);
  const orders = useOrders(openOnly);
  const [openId, setOpenId] = useState<number | null>(null);
  const [note, setNote] = useState<string | null>(null);

  return (
    <section aria-labelledby="orders-title" className={styles.page}>
      <div className={styles.toolbar}>
        <h1 id="orders-title" className={styles.title}>
          Purchase orders
        </h1>
        <Link to="/purchases">Back to purchases</Link>
      </div>
      {note ? (
        <p role="status" className={styles.saved}>
          {note}
        </p>
      ) : null}
      {owner ? <NewOrder onDone={setNote} /> : null}
      <label className={styles.choice}>
        <input type="checkbox" checked={openOnly} onChange={(e) => setOpenOnly(e.target.checked)} />
        Show only orders not fully billed
      </label>
      <div className={styles.tableWrap}>
        <table className={styles.table} aria-label="Purchase orders">
          <thead>
            <tr>
              <th scope="col">Order</th>
              <th scope="col">Date</th>
              <th scope="col">Supplier</th>
              <th scope="col">At</th>
              <th scope="col">Status</th>
              {owner ? (
                <th scope="col" className="num">
                  Value (₹)
                </th>
              ) : null}
            </tr>
          </thead>
          <tbody>
            {(orders.data ?? []).map((o) => (
              <Fragment key={o.id}>
                <tr className={openId === o.id ? styles.selected : ""}>
                  <td>
                    <button
                      type="button"
                      className={styles.rowButton}
                      aria-expanded={openId === o.id}
                      onClick={() => setOpenId(openId === o.id ? null : o.id)}
                    >
                      {o.number}
                    </button>
                  </td>
                  <td>{o.order_date}</td>
                  <td>{o.supplier_name}</td>
                  <td>{o.location_code}</td>
                  <td>{STATUS[o.status] ?? o.status}</td>
                  {owner ? (
                    <td className="num">{"value" in o ? formatMoney(o.value) : ""}</td>
                  ) : null}
                </tr>
                {openId === o.id ? (
                  <tr>
                    <td colSpan={owner ? 6 : 5}>
                      <div className={styles.stack}>
                        <table className={styles.table} aria-label={`Lines of ${o.number}`}>
                          <thead>
                            <tr>
                              <th scope="col">Item</th>
                              <th scope="col" className="num">
                                Ordered
                              </th>
                              <th scope="col" className="num">
                                Received
                              </th>
                              <th scope="col" className="num">
                                Billed
                              </th>
                              {owner ? (
                                <th scope="col" className="num">
                                  Rate (₹)
                                </th>
                              ) : null}
                            </tr>
                          </thead>
                          <tbody>
                            {o.lines.map((l) => (
                              <tr key={l.id}>
                                <td>{l.item_name}</td>
                                <td className="num">
                                  {trimDecimal(l.base_qty)} {l.base_unit}
                                </td>
                                <td className="num">
                                  {trimDecimal(l.received_qty)} {l.base_unit}
                                </td>
                                <td className="num">
                                  {trimDecimal(l.billed_qty)} {l.base_unit}
                                </td>
                                {owner ? (
                                  <td className="num">
                                    {"rate" in l ? `${formatMoney(l.rate)} per ${l.unit}` : ""}
                                  </td>
                                ) : null}
                              </tr>
                            ))}
                          </tbody>
                        </table>
                        {o.receipts.length > 0 ? (
                          <p className={styles.sub}>
                            Receipts:{" "}
                            {o.receipts.map((r) => `${r.number} (${r.receipt_date})`).join(", ")}
                            {o.bills.length > 0
                              ? ` · Bills: ${o.bills.map((b) => b.bill_no).join(", ")}`
                              : ""}
                          </p>
                        ) : null}
                        {canReceive && o.status === "open" ? (
                          <Receive order={o} onDone={setNote} />
                        ) : null}
                      </div>
                    </td>
                  </tr>
                ) : null}
              </Fragment>
            ))}
          </tbody>
        </table>
        {orders.isSuccess && (orders.data ?? []).length === 0 ? (
          <p className={styles.empty}>No orders yet.</p>
        ) : null}
      </div>
    </section>
  );
}
