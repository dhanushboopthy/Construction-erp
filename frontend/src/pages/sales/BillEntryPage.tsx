import { useEffect, useMemo, useState, type FormEvent, type KeyboardEvent } from "react";
import { useNavigate } from "react-router";

import { toFormError } from "@/api/errors";
import { useItems, useParties } from "@/api/masters";
import { previewInvoice, useCreateInvoice } from "@/api/sales";
import { useLocations } from "@/api/setup";
import type { FulfilmentSource, InvoiceCreate, InvoicePreview } from "@/api/types";
import { useAuth } from "@/auth/AuthContext";
import { Button } from "@/components/Button";
import { SelectField, TextField } from "@/components/Field";
import styles from "@/components/Ledger.module.css";
import { formatMoney, trimDecimal } from "@/lib/format";
import { unitNames } from "@/pages/items/itemLabels";

interface LineRow {
  itemId: string;
  unit: string;
  quantity: string;
  source: FulfilmentSource;
  sourceLocationId: string;
  discount: string;
  reason: string;
}

const emptyLine = (): LineRow => ({
  itemId: "",
  unit: "",
  quantity: "",
  source: "shop",
  sourceLocationId: "",
  discount: "",
  reason: "",
});
const DECIMAL = /^\d+(\.\d+)?$/;

function todayISO(): string {
  const d = new Date();
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
}

/** The counter billing screen: pick the customer and site, key item and quantity, and read the
 * rate, tax and total the server works out. Staff never type a price (B3, B4). */
export function BillEntryPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const owner = user?.role === "owner";
  const items = useItems("", "");
  const parties = useParties("", "customer");
  const locations = useLocations();
  const create = useCreateInvoice();

  const [partyId, setPartyId] = useState("");
  const [siteId, setSiteId] = useState("");
  const [locationId, setLocationId] = useState(
    user?.locations[0] ? String(user.locations[0].id) : "",
  );
  const [date, setDate] = useState(todayISO());
  const [vehicle, setVehicle] = useState("");
  const [remark, setRemark] = useState("");
  const [lines, setLines] = useState<LineRow[]>([emptyLine()]);
  const [preview, setPreview] = useState<InvoicePreview | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [serverError, setServerError] = useState<{ message: string; approval: boolean } | null>(
    null,
  );
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [focusLine, setFocusLine] = useState<number | null>(null);
  const [key, setKey] = useState(() => crypto.randomUUID());

  const itemList = useMemo(
    () => (items.data?.items ?? []).filter((i) => i.is_active),
    [items.data],
  );
  const customers = (parties.data?.items ?? []).filter((p) => p.is_active);
  const places = useMemo(() => locations.data ?? [], [locations.data]);
  const party = customers.find((p) => String(p.id) === partyId);
  const sites = (party?.sites ?? []).filter((s) => s.is_active);
  const itemOf = (id: string) => itemList.find((i) => String(i.id) === id);

  // Default to the walk-in customer once the list is there.
  useEffect(() => {
    if (!partyId && customers.length > 0) {
      const walkIn = customers.find((c) => c.name === "Walk-in customer");
      if (walkIn) setPartyId(String(walkIn.id));
    }
  }, [customers, partyId]);

  // The owner works at every shop, so start on the first one.
  useEffect(() => {
    if (!locationId) {
      const first = places.find((l) => l.kind === "shop");
      if (first) setLocationId(String(first.id));
    }
  }, [places, locationId]);

  function payload(): InvoiceCreate | null {
    if (!partyId || !locationId) return null;
    const out: InvoiceCreate["lines"] = [];
    for (const l of lines) {
      if (!l.itemId || !DECIMAL.test(l.quantity) || Number(l.quantity) <= 0) return null;
      if (l.discount && !DECIMAL.test(l.discount)) return null;
      out.push({
        item_id: Number(l.itemId),
        quantity: l.quantity,
        unit: l.unit || null,
        source: l.source,
        source_location_id:
          l.source === "godown" && l.sourceLocationId ? Number(l.sourceLocationId) : null,
        discount: owner && l.discount ? l.discount : null,
        discount_reason: owner && l.discount ? l.reason || null : null,
      });
    }
    return {
      location_id: Number(locationId),
      party_id: Number(partyId),
      site_id: siteId ? Number(siteId) : null,
      invoice_date: owner ? date : null,
      vehicle_no: vehicle.trim() || null,
      remark: remark.trim() || null,
      lines: out,
    };
  }

  const body = payload();
  const bodyKey = JSON.stringify(body);
  useEffect(() => {
    if (!body) {
      setPreview(null);
      setPreviewError(null);
      return;
    }
    const handle = setTimeout(() => {
      previewInvoice(body)
        .then((p) => {
          setPreview(p);
          setPreviewError(null);
        })
        .catch((err: unknown) => {
          setPreview(null);
          setPreviewError(toFormError(err).message);
        });
    }, 350);
    return () => clearTimeout(handle);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bodyKey]);

  useEffect(() => {
    if (focusLine === null) return;
    document.querySelector<HTMLElement>(`[data-line-item="${focusLine}"]`)?.focus();
    setFocusLine(null);
  }, [focusLine]);

  const setLine = (i: number, patch: Partial<LineRow>) =>
    setLines((rows) => rows.map((r, j) => (j === i ? { ...r, ...patch } : r)));
  function addLine() {
    setLines((rows) => [...rows, emptyLine()]);
    setFocusLine(lines.length);
  }

  async function onSubmit(event?: FormEvent) {
    event?.preventDefault();
    const found: Record<string, string> = {};
    if (!partyId) found.party = "Pick the customer.";
    if (!locationId) found.location = "Pick the shop you are billing from.";
    lines.forEach((l, i) => {
      if (!l.itemId) found[`${i}.item`] = "Pick an item.";
      if (!DECIMAL.test(l.quantity) || Number(l.quantity) <= 0)
        found[`${i}.qty`] = "Enter the quantity.";
    });
    setErrors(found);
    setServerError(null);
    if (Object.keys(found).length > 0 || !body) return;
    try {
      const saved = await create.mutateAsync({ body, key });
      setKey(crypto.randomUUID());
      void navigate(`/sales?open=${saved.id}`);
    } catch (err) {
      const e = toFormError(err);
      const approval = (err as { requiresOwnerApproval?: boolean }).requiresOwnerApproval === true;
      setServerError({ message: e.message, approval });
    }
  }

  function onKeyDown(event: KeyboardEvent<HTMLFormElement>) {
    if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
      event.preventDefault();
      void onSubmit();
    } else if (
      event.key === "Enter" &&
      (event.target as HTMLElement).dataset.lineQty !== undefined
    ) {
      event.preventDefault();
      addLine();
    }
  }

  const intra = preview?.supply_kind === "intra_state";

  return (
    <section aria-labelledby="bill-title" className={styles.page}>
      <div className={styles.toolbar}>
        <h1 id="bill-title" className={styles.title}>
          New bill
        </h1>
        <p className={styles.keys}>Enter in Quantity adds a line · Ctrl+Enter saves · Tab moves</p>
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
              label="Customer"
              value={partyId}
              error={errors.party}
              onChange={(e) => {
                setPartyId(e.target.value);
                setSiteId("");
              }}
              autoFocus
            >
              <option value="">Choose a customer</option>
              {customers.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </SelectField>
            <SelectField
              label="Deliver to"
              value={siteId}
              onChange={(e) => setSiteId(e.target.value)}
              hint={siteId ? undefined : "Blank = collected from the shop"}
            >
              <option value="">Collect from shop</option>
              {sites.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </SelectField>
            <SelectField
              label="Bill from"
              value={locationId}
              error={errors.location}
              onChange={(e) => setLocationId(e.target.value)}
            >
              <option value="">Choose a shop</option>
              {places
                .filter(
                  (l) => l.kind === "shop" && (owner || user?.locations.some((x) => x.id === l.id)),
                )
                .map((l) => (
                  <option key={l.id} value={l.id}>
                    {l.code} {l.name}
                  </option>
                ))}
            </SelectField>
            {owner ? (
              <TextField
                label="Bill date"
                type="date"
                value={date}
                max={todayISO()}
                onChange={(e) => setDate(e.target.value)}
              />
            ) : null}
            <TextField
              label="Vehicle no."
              value={vehicle}
              onChange={(e) => setVehicle(e.target.value.toUpperCase())}
            />
          </div>

          {lines.map((l, i) => {
            const item = itemOf(l.itemId);
            const row = preview?.lines[i];
            return (
              <fieldset key={i} className={styles.lineBlock} style={{ margin: 0 }}>
                <legend className="visually-hidden">{`Line ${i + 1}`}</legend>
                <div className={styles.lineGrid}>
                  <SelectField
                    label={`Item ${i + 1}`}
                    data-line-item={i}
                    value={l.itemId}
                    error={errors[`${i}.item`]}
                    onChange={(e) => setLine(i, { itemId: e.target.value, unit: "" })}
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
                    value={l.unit || item?.base_unit || ""}
                    onChange={(e) => setLine(i, { unit: e.target.value })}
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
                    data-line-qty=""
                    value={l.quantity}
                    error={errors[`${i}.qty`]}
                    onChange={(e) => setLine(i, { quantity: e.target.value })}
                  />
                  <SelectField
                    label="Taken from"
                    value={l.source}
                    onChange={(e) => setLine(i, { source: e.target.value as FulfilmentSource })}
                  >
                    <option value="shop">Shop</option>
                    <option value="godown">Other place</option>
                    <option value="direct">Supplier direct</option>
                  </SelectField>
                  {l.source === "godown" ? (
                    <SelectField
                      label="Which place"
                      value={l.sourceLocationId}
                      onChange={(e) => setLine(i, { sourceLocationId: e.target.value })}
                    >
                      <option value="">Choose</option>
                      {places
                        .filter((p) => String(p.id) !== locationId)
                        .map((p) => (
                          <option key={p.id} value={p.id}>
                            {p.code} {p.name}
                          </option>
                        ))}
                    </SelectField>
                  ) : (
                    <span />
                  )}
                  <Button
                    variant="quiet"
                    aria-label={`Remove line ${i + 1}`}
                    disabled={lines.length === 1}
                    onClick={() => setLines((rows) => rows.filter((_, j) => j !== i))}
                  >
                    Remove
                  </Button>
                </div>
                {owner ? (
                  <div className={styles.inline}>
                    <TextField
                      label="Discount (₹)"
                      inputMode="decimal"
                      className={styles.amount}
                      value={l.discount}
                      onChange={(e) => setLine(i, { discount: e.target.value })}
                    />
                    <TextField
                      label="Reason for discount"
                      value={l.reason}
                      onChange={(e) => setLine(i, { reason: e.target.value })}
                    />
                    <span />
                  </div>
                ) : null}
                {row ? (
                  <p className={styles.sub} aria-live="polite">
                    {row.rate
                      ? `₹${trimDecimal(row.rate)} per ${row.base_unit}${row.rate_source === "customer" ? " (this customer's rate)" : ""} · ${trimDecimal(row.base_qty)} ${row.base_unit} · taxable ₹${formatMoney(row.taxable)} · GST ${trimDecimal(row.gst_rate)}% · line ₹${formatMoney(row.line_total)}`
                      : "No rate yet"}
                    {row.stock_after !== null
                      ? ` · ${trimDecimal(row.stock_after)} ${row.base_unit} left`
                      : ""}
                  </p>
                ) : null}
                {row?.problems.map((p) => (
                  <p key={p} role="alert" className={styles.problem}>
                    {p}
                  </p>
                ))}
              </fieldset>
            );
          })}
          <div className={styles.actions}>
            <Button onClick={addLine}>Add line</Button>
          </div>
          <TextField label="Remark" value={remark} onChange={(e) => setRemark(e.target.value)} />
          {serverError ? (
            <p role="alert" className={styles.formError}>
              {serverError.message}
              {serverError.approval ? " Ask the owner to make this bill." : ""}
            </p>
          ) : null}
          <div className={styles.actions}>
            <Button
              type="submit"
              variant="primary"
              disabled={create.isPending || preview?.can_save === false}
            >
              {create.isPending ? "Saving…" : "Save bill"}
            </Button>
            <Button onClick={() => void navigate("/sales")}>Cancel</Button>
          </div>
        </div>

        <aside className={styles.preview} aria-labelledby="totals-title" aria-live="polite">
          <h3 id="totals-title">Bill</h3>
          {previewError ? <p className={styles.formError}>{previewError}</p> : null}
          {!preview && !previewError ? (
            <p className={styles.sub}>
              Pick the customer and an item with a quantity to see the bill.
            </p>
          ) : null}
          {preview ? (
            <>
              <p className={styles.sub}>
                {preview.supply_type === "B2B"
                  ? "Registered customer"
                  : "Unregistered customer (B2C)"}{" "}
                · place of supply {preview.place_of_supply} · {intra ? "CGST + SGST" : "IGST"}
              </p>
              <span className={styles.kv}>
                <span>Taxable value</span>
                <span>{formatMoney(preview.taxable_value)}</span>
              </span>
              {intra ? (
                <>
                  <span className={styles.kv}>
                    <span>CGST</span>
                    <span>{formatMoney(preview.cgst)}</span>
                  </span>
                  <span className={styles.kv}>
                    <span>SGST</span>
                    <span>{formatMoney(preview.sgst)}</span>
                  </span>
                </>
              ) : (
                <span className={styles.kv}>
                  <span>IGST</span>
                  <span>{formatMoney(preview.igst)}</span>
                </span>
              )}
              <span className={styles.kv}>
                <span>Round off</span>
                <span>{formatMoney(preview.round_off)}</span>
              </span>
              <div className={styles.billTotal}>
                <span>Bill total</span>
                <strong>₹{formatMoney(preview.grand_total)}</strong>
              </div>
              {Number(preview.pending_balance) > 0 ? (
                <p className={styles.callout}>
                  This customer already owes ₹{formatMoney(preview.pending_balance)}.
                </p>
              ) : null}
            </>
          ) : null}
        </aside>
      </form>
    </section>
  );
}
