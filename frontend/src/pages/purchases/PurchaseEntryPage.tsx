import { useEffect, useMemo, useState, type FormEvent, type KeyboardEvent } from "react";
import { useNavigate } from "react-router";

import { toFormError } from "@/api/errors";
import { useItems } from "@/api/masters";
import { previewPurchase, useCostComponents, useCreatePurchase } from "@/api/purchasing";
import { useLocations } from "@/api/setup";
import { useParties } from "@/api/masters";
import type { PurchaseCreate, PurchasePreview } from "@/api/types";
import { useAuth } from "@/auth/AuthContext";
import { Button } from "@/components/Button";
import { CheckField, SelectField, TextField } from "@/components/Field";
import styles from "@/components/Ledger.module.css";
import { formatMoney, trimDecimal } from "@/lib/format";
import { unitNames } from "@/pages/items/itemLabels";

interface ChargeRow {
  componentId: string;
  amount: string;
  onBill: boolean;
}
interface LineRow {
  itemId: string;
  unit: string;
  quantity: string;
  received: string;
  weightNote: string;
  rate: string;
  gst: string;
  charges: ChargeRow[];
}

const emptyLine = (): LineRow => ({
  itemId: "",
  unit: "",
  quantity: "",
  received: "",
  weightNote: "",
  rate: "",
  gst: "",
  charges: [],
});
const DECIMAL = /^\d+(\.\d+)?$/;

function todayISO(): string {
  const d = new Date();
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
}

export function PurchaseEntryPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const owner = user?.role === "owner";
  const items = useItems("", "");
  const suppliers = useParties("", "supplier");
  const locations = useLocations();
  const components = useCostComponents();
  const create = useCreatePurchase();

  const [supplierId, setSupplierId] = useState("");
  const [locationId, setLocationId] = useState(
    user?.locations[0] ? String(user.locations[0].id) : "",
  );
  const [billNo, setBillNo] = useState("");
  const [billDate, setBillDate] = useState(todayISO());
  const [dueDate, setDueDate] = useState("");
  const [mode, setMode] = useState<"stock" | "direct">("stock");
  const [note, setNote] = useState("");
  const [lines, setLines] = useState<LineRow[]>([emptyLine()]);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [serverError, setServerError] = useState<string | null>(null);
  const [focusLine, setFocusLine] = useState<number | null>(null);
  const [preview, setPreview] = useState<PurchasePreview | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);

  const itemList = useMemo(
    () => (items.data?.items ?? []).filter((i) => i.is_active),
    [items.data],
  );
  const itemById = (id: string) => itemList.find((i) => String(i.id) === id);
  const supplierList = (suppliers.data?.items ?? []).filter((s) => s.is_active);
  const placeList = locations.data ?? [];

  function payload(): PurchaseCreate | null {
    if (!supplierId || !locationId || !billNo.trim() || !billDate) return null;
    const out: PurchaseCreate["lines"] = [];
    for (const line of lines) {
      if (
        !line.itemId ||
        !line.unit ||
        !DECIMAL.test(line.quantity) ||
        Number(line.quantity) <= 0 ||
        !DECIMAL.test(line.rate)
      )
        return null;
      if (line.received && (!DECIMAL.test(line.received) || Number(line.received) <= 0))
        return null;
      if (line.gst && !DECIMAL.test(line.gst)) return null;
      if (line.charges.some((c) => !c.componentId || !DECIMAL.test(c.amount))) return null;
      out.push({
        item_id: Number(line.itemId),
        unit: line.unit,
        quantity: line.quantity,
        received_quantity: line.received || null,
        weight_note: line.received && line.weightNote.trim() ? line.weightNote.trim() : null,
        rate: line.rate,
        gst_rate: line.gst || null,
        charges: line.charges.map((c) => ({
          component_id: Number(c.componentId),
          amount: c.amount,
          on_supplier_bill: c.onBill,
        })),
      });
    }
    return {
      supplier_id: Number(supplierId),
      location_id: Number(locationId),
      bill_no: billNo.trim(),
      bill_date: billDate,
      due_date: dueDate || null,
      mode,
      note: note.trim() || null,
      lines: out,
    };
  }

  // The owner sees landed cost while keying. The server does the maths (ADR 0002).
  const body = payload();
  const bodyKey = JSON.stringify(body);
  useEffect(() => {
    if (!owner || !body) {
      setPreview(null);
      setPreviewError(null);
      return;
    }
    const handle = setTimeout(() => {
      previewPurchase(body)
        .then((p) => {
          setPreview(p);
          setPreviewError(null);
        })
        .catch((err: unknown) => {
          setPreview(null);
          setPreviewError(toFormError(err).message);
        });
    }, 450);
    return () => clearTimeout(handle);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bodyKey, owner]);

  useEffect(() => {
    if (focusLine === null) return;
    document.querySelector<HTMLElement>(`[data-line-item="${focusLine}"]`)?.focus();
    setFocusLine(null);
  }, [focusLine]);

  const setLine = (index: number, patch: Partial<LineRow>) =>
    setLines((rows) => rows.map((r, i) => (i === index ? { ...r, ...patch } : r)));

  function addLine() {
    setLines((rows) => [...rows, emptyLine()]);
    setFocusLine(lines.length);
  }

  function pickItem(index: number, id: string) {
    const item = itemById(id);
    setLine(index, {
      itemId: id,
      unit: item ? (item.units[0]?.unit ?? item.base_unit) : "",
      gst: "",
    });
  }

  function validate(): Record<string, string> {
    const found: Record<string, string> = {};
    if (!supplierId) found.supplier = "Pick the supplier.";
    if (!locationId) found.location = "Pick where the goods arrive.";
    if (!billNo.trim()) found.billNo = "Enter the supplier's bill number.";
    if (!billDate) found.billDate = "Enter the bill date.";
    if (dueDate && dueDate < billDate)
      found.dueDate = "The due date cannot be before the bill date.";
    lines.forEach((l, i) => {
      if (!l.itemId) found[`${i}.item`] = "Pick an item.";
      if (!DECIMAL.test(l.quantity) || Number(l.quantity) <= 0)
        found[`${i}.quantity`] = "Enter the billed quantity.";
      if (l.received && (!DECIMAL.test(l.received) || Number(l.received) <= 0))
        found[`${i}.received`] = "Enter a quantity above 0.";
      if (!DECIMAL.test(l.rate)) found[`${i}.rate`] = "Enter the rate on the bill.";
      l.charges.forEach((c, j) => {
        if (!c.componentId) found[`${i}.c${j}.type`] = "Pick a charge type.";
        if (!DECIMAL.test(c.amount)) found[`${i}.c${j}.amount`] = "Enter an amount.";
      });
    });
    return found;
  }

  async function onSubmit(event?: FormEvent) {
    event?.preventDefault();
    const found = validate();
    setErrors(found);
    setServerError(null);
    if (Object.keys(found).length > 0 || !body) return;
    try {
      const saved = await create.mutateAsync(body);
      void navigate("/purchases", { state: { saved: saved.number } });
    } catch (err) {
      setServerError(toFormError(err).message);
    }
  }

  function onKeyDown(event: KeyboardEvent<HTMLFormElement>) {
    if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
      event.preventDefault();
      void onSubmit();
      return;
    }
    // Enter in a line's rate box adds the next line, so a whole bill is keyed without the mouse.
    if (event.key === "Enter" && (event.target as HTMLElement).dataset.lineRate !== undefined) {
      event.preventDefault();
      addLine();
    }
  }

  const supplierName = supplierList.find((s) => String(s.id) === supplierId)?.name;

  return (
    <section aria-labelledby="entry-title" className={styles.page}>
      <div className={styles.toolbar}>
        <h1 id="entry-title" className={styles.title}>
          New purchase
        </h1>
        <p className={styles.keys}>Enter in Rate adds a line · Ctrl+Enter saves · Tab moves</p>
      </div>
      <form
        onSubmit={(e) => void onSubmit(e)}
        onKeyDown={onKeyDown}
        noValidate
        className={styles.entryLayout}
      >
        <div className={styles.stack}>
          <div className={styles.headerGrid}>
            <SelectField
              label="Supplier"
              value={supplierId}
              onChange={(e) => setSupplierId(e.target.value)}
              error={errors.supplier}
              autoFocus
            >
              <option value="">
                {supplierList.length ? "Choose a supplier" : "No suppliers yet"}
              </option>
              {supplierList.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </SelectField>
            <SelectField
              label="Goods arrive at"
              value={locationId}
              onChange={(e) => setLocationId(e.target.value)}
              error={errors.location}
            >
              <option value="">Choose a place</option>
              {placeList
                .filter((l) => owner || user?.locations.some((x) => x.id === l.id))
                .map((l) => (
                  <option key={l.id} value={l.id}>
                    {l.code} {l.name}
                  </option>
                ))}
            </SelectField>
            <TextField
              label="Supplier's bill no."
              value={billNo}
              onChange={(e) => setBillNo(e.target.value)}
              error={errors.billNo}
            />
            <TextField
              label="Bill date"
              type="date"
              value={billDate}
              onChange={(e) => setBillDate(e.target.value)}
              error={errors.billDate}
            />
            <TextField
              label="Pay by"
              type="date"
              value={dueDate}
              onChange={(e) => setDueDate(e.target.value)}
              error={errors.dueDate}
              hint="Leave blank if paid in advance."
            />
            <SelectField
              label="Goes to"
              value={mode}
              onChange={(e) => setMode(e.target.value as "stock" | "direct")}
              hint={
                mode === "direct"
                  ? "Sent straight to a customer's site: no stock is added."
                  : undefined
              }
            >
              <option value="stock">Our stock</option>
              <option value="direct">Customer's site (direct)</option>
            </SelectField>
          </div>

          {lines.map((line, i) => {
            const item = itemById(line.itemId);
            return (
              <fieldset key={i} className={styles.lineBlock} style={{ margin: 0 }}>
                <legend className="visually-hidden">{`Line ${i + 1}`}</legend>
                <div className={styles.lineGrid}>
                  <SelectField
                    label={`Item ${i + 1}`}
                    data-line-item={i}
                    value={line.itemId}
                    onChange={(e) => pickItem(i, e.target.value)}
                    error={errors[`${i}.item`]}
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
                    value={line.unit}
                    onChange={(e) => setLine(i, { unit: e.target.value })}
                  >
                    {item ? (
                      unitNames(item).map((u) => <option key={u}>{u}</option>)
                    ) : (
                      <option value="">—</option>
                    )}
                  </SelectField>
                  <TextField
                    label="Billed qty"
                    inputMode="decimal"
                    className={styles.amount}
                    value={line.quantity}
                    onChange={(e) => setLine(i, { quantity: e.target.value })}
                    error={errors[`${i}.quantity`]}
                  />
                  <TextField
                    label="Received qty"
                    inputMode="decimal"
                    className={styles.amount}
                    value={line.received}
                    onChange={(e) => setLine(i, { received: e.target.value })}
                    error={errors[`${i}.received`]}
                  />
                  {line.received && line.received !== line.quantity ? (
                    <TextField
                      label="Why the weight differs"
                      value={line.weightNote}
                      onChange={(e) => setLine(i, { weightNote: e.target.value })}
                    />
                  ) : null}
                  <TextField
                    label={`Rate per ${line.unit || "unit"} (₹)`}
                    inputMode="decimal"
                    className={styles.amount}
                    data-line-rate=""
                    value={line.rate}
                    onChange={(e) => setLine(i, { rate: e.target.value })}
                    error={errors[`${i}.rate`]}
                  />
                  <Button
                    variant="quiet"
                    aria-label={`Remove line ${i + 1}`}
                    disabled={lines.length === 1}
                    onClick={() => setLines((rows) => rows.filter((_, j) => j !== i))}
                  >
                    Remove
                  </Button>
                </div>
                {item ? (
                  <p className={styles.sub}>
                    GST {trimDecimal(item.gst_rate)}% · leave Received blank when the weighbridge
                    matches the bill
                  </p>
                ) : null}
                {line.charges.map((c, j) => (
                  <div key={j} className={styles.chargeRow}>
                    <SelectField
                      label={`Charge ${j + 1}`}
                      value={c.componentId}
                      error={errors[`${i}.c${j}.type`]}
                      onChange={(e) => {
                        const comp = components.data?.find((x) => String(x.id) === e.target.value);
                        setLine(i, {
                          charges: line.charges.map((x, k) =>
                            k === j
                              ? {
                                  ...x,
                                  componentId: e.target.value,
                                  amount:
                                    x.amount || (comp ? trimDecimal(comp.default_amount) : ""),
                                }
                              : x,
                          ),
                        });
                      }}
                    >
                      <option value="">Choose a charge</option>
                      {(components.data ?? []).map((comp) => (
                        <option key={comp.id} value={comp.id}>
                          {comp.name} ({comp.basis.replace(/_/g, " ")})
                        </option>
                      ))}
                    </SelectField>
                    <TextField
                      label="Amount (₹)"
                      inputMode="decimal"
                      className={styles.amount}
                      value={c.amount}
                      error={errors[`${i}.c${j}.amount`]}
                      onChange={(e) =>
                        setLine(i, {
                          charges: line.charges.map((x, k) =>
                            k === j ? { ...x, amount: e.target.value } : x,
                          ),
                        })
                      }
                    />
                    <CheckField
                      label="On supplier's bill"
                      checked={c.onBill}
                      onChange={(e) =>
                        setLine(i, {
                          charges: line.charges.map((x, k) =>
                            k === j ? { ...x, onBill: e.target.checked } : x,
                          ),
                        })
                      }
                    />
                    <Button
                      variant="quiet"
                      aria-label={`Remove charge ${j + 1} of line ${i + 1}`}
                      onClick={() =>
                        setLine(i, { charges: line.charges.filter((_, k) => k !== j) })
                      }
                    >
                      Remove
                    </Button>
                  </div>
                ))}
                <div className={styles.actions}>
                  <Button
                    onClick={() =>
                      setLine(i, {
                        charges: [...line.charges, { componentId: "", amount: "", onBill: false }],
                      })
                    }
                  >
                    Add charge to line {i + 1}
                  </Button>
                </div>
              </fieldset>
            );
          })}
          <div className={styles.actions}>
            <Button onClick={addLine}>Add line</Button>
          </div>
          <TextField label="Note" value={note} onChange={(e) => setNote(e.target.value)} />
          {serverError ? (
            <p role="alert" className={styles.formError}>
              {serverError}
            </p>
          ) : null}
          {Object.keys(errors).length > 0 ? (
            <p role="alert" className={styles.formError}>
              Some boxes need fixing. They are marked above.
            </p>
          ) : null}
          <div className={styles.actions}>
            <Button type="submit" variant="primary" disabled={create.isPending}>
              {create.isPending ? "Saving…" : "Save purchase"}
            </Button>
            <Button onClick={() => void navigate("/purchases")}>Cancel</Button>
          </div>
        </div>

        {owner ? (
          <aside className={styles.preview} aria-labelledby="preview-title" aria-live="polite">
            <h3 id="preview-title">Landed cost</h3>
            {previewError ? <p className={styles.formError}>{previewError}</p> : null}
            {!preview && !previewError ? (
              <p className={styles.sub}>
                Fill in the supplier, bill and lines to see the cost per unit.
              </p>
            ) : null}
            {preview ? (
              <>
                {preview.lines.map((l, i) => (
                  <div key={i} className={styles.stack}>
                    <strong>{l.item_name}</strong>
                    <span className={styles.kv}>
                      <span>Cost per {l.base_unit}</span>
                      <strong>₹{trimDecimal(l.unit_cost)}</strong>
                    </span>
                    <span className={styles.kv}>
                      <span>Landed total</span>
                      <span>{formatMoney(l.total_cost)}</span>
                    </span>
                    {l.weight_flagged ? (
                      <span className={styles.kv} role="status">
                        <span>Weight differs by {l.weight_variance_pct}%, a note is needed</span>
                        <span>Shortage ₹{formatMoney(l.shortage_value)}</span>
                      </span>
                    ) : null}
                  </div>
                ))}
                <div className={styles.stack}>
                  <span className={styles.kv}>
                    <span>Goods</span>
                    <span>{formatMoney(preview.goods_value)}</span>
                  </span>
                  <span className={styles.kv}>
                    <span>GST {preview.gst_in_cost ? "(in cost)" : "(not in cost)"}</span>
                    <span>{formatMoney(preview.gst_amount)}</span>
                  </span>
                  <span className={styles.kv}>
                    <span>Charges</span>
                    <span>{formatMoney(preview.charges_total)}</span>
                  </span>
                  <span className={`${styles.kv} ${styles.kvStrong}`}>
                    <span>{supplierName ? `We owe ${supplierName}` : "We owe the supplier"}</span>
                    <span>₹{formatMoney(preview.supplier_payable)}</span>
                  </span>
                </div>
              </>
            ) : null}
          </aside>
        ) : null}
      </form>
    </section>
  );
}
