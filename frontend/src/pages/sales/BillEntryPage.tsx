import { useEffect, useMemo, useState, type FormEvent, type KeyboardEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router";

import { toFormError } from "@/api/errors";
import { useItems, useParties } from "@/api/masters";
import { previewQuote, QUOTE_LABEL, useCreateQuote, useQuote } from "@/api/quotes";
import { previewInvoice, useCreateInvoice } from "@/api/sales";
import { useLocations } from "@/api/setup";
import { useOpenDirectLines } from "@/api/transport";
import type {
  FulfilmentSource,
  InvoiceCreate,
  InvoicePreview,
  PaymentMode,
  QuoteCreate,
  QuoteKind,
} from "@/api/types";
import { useAuth } from "@/auth/AuthContext";
import { ApprovalPrompt } from "@/components/ApprovalPrompt";
import { Button } from "@/components/Button";
import { SelectField, TextField } from "@/components/Field";
import styles from "@/components/Ledger.module.css";
import { formatMoney, trimDecimal } from "@/lib/format";
import { ItemEditor } from "@/pages/items/ItemEditor";
import { unitNames } from "@/pages/items/itemLabels";
import { PartyEditor } from "@/pages/parties/PartyEditor";

/** What the side column shows: the bill's totals, or a quick form to add a missing customer or
 * item without leaving the bill. */
type Side = { kind: "totals" } | { kind: "customer" } | { kind: "item" };

/** What is being made: a tax invoice, or a quotation or proforma that is not one (ADR 0005). */
type Doc = "invoice" | QuoteKind;

interface PayRow {
  mode: PaymentMode;
  amount: string;
  reference: string;
}

interface LineRow {
  itemId: string;
  unit: string;
  quantity: string;
  source: FulfilmentSource;
  sourceLocationId: string;
  purchaseLineId: string;
  slipWeight: string;
  weightNote: string;
  discount: string;
  reason: string;
  price: string; // a price typed for this bill, per the line's unit (owner or approved)
  priceReason: string;
}

const emptyLine = (): LineRow => ({
  itemId: "",
  unit: "",
  quantity: "",
  source: "shop",
  sourceLocationId: "",
  purchaseLineId: "",
  slipWeight: "",
  weightNote: "",
  discount: "",
  reason: "",
  price: "",
  priceReason: "",
});
const DECIMAL = /^\d+(\.\d+)?$/;

/** Which supplier purchase supplies a direct line. Optional: it can be linked later by the owner. */
function DirectPurchasePick({
  itemId,
  value,
  onChange,
}: {
  itemId: number | null;
  value: string;
  onChange: (value: string) => void;
}) {
  const open = useOpenDirectLines(itemId);
  return (
    <SelectField label="Supplier purchase" value={value} onChange={(e) => onChange(e.target.value)}>
      <option value="">Link later</option>
      {(open.data ?? []).map((p) => (
        <option key={p.purchase_line_id} value={p.purchase_line_id}>
          {p.purchase_number} · {p.supplier_name} · {trimDecimal(p.free_qty)} {p.base_unit} free
        </option>
      ))}
    </SelectField>
  );
}

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
  const createQuote = useCreateQuote();
  const [params] = useSearchParams();
  // A bill made from a saved quotation or proforma (`?quote=`), or a new quotation (`?doc=`).
  const fromQuoteId = params.get("quote") ? Number(params.get("quote")) : null;
  const fromQuote = useQuote(fromQuoteId);
  const [doc, setDoc] = useState<Doc>(() => {
    const asked = params.get("doc");
    return asked === "quotation" || asked === "proforma" ? asked : "invoice";
  });
  const isQuote = doc !== "invoice";
  const [validUntil, setValidUntil] = useState("");

  const [partyId, setPartyId] = useState("");
  const [siteId, setSiteId] = useState("");
  const [locationId, setLocationId] = useState(
    user?.locations[0] ? String(user.locations[0].id) : "",
  );
  const [date, setDate] = useState(todayISO());
  const [vehicle, setVehicle] = useState("");
  const [remark, setRemark] = useState("");
  const [lines, setLines] = useState<LineRow[]>([emptyLine()]);
  const [pays, setPays] = useState<PayRow[]>([]);
  const [approvalIds, setApprovalIds] = useState<number[]>([]);
  const [preview, setPreview] = useState<InvoicePreview | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [serverError, setServerError] = useState<{ message: string; approval: boolean } | null>(
    null,
  );
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [focusLine, setFocusLine] = useState<number | null>(null);
  const [key, setKey] = useState(() => crypto.randomUUID());
  const [side, setSide] = useState<Side>({ kind: "totals" });

  const itemList = useMemo(
    () => (items.data?.items ?? []).filter((i) => i.is_active),
    [items.data],
  );
  const customers = (parties.data?.items ?? []).filter((p) => p.is_active);
  const places = useMemo(() => locations.data ?? [], [locations.data]);
  const party = customers.find((p) => String(p.id) === partyId);
  const sites = (party?.sites ?? []).filter((s) => s.is_active);
  const itemOf = (id: string) => itemList.find((i) => String(i.id) === id);
  // The shops this user may bill from. With only one there is nothing to choose.
  const shops = places.filter(
    (l) => l.kind === "shop" && (owner || user?.locations.some((x) => x.id === l.id)),
  );
  const onlyShop = shops.length === 1 ? shops[0] : undefined;

  // Billing a quotation: start from its customer, shop and lines. Prices are worked out again at
  // today's rates, the same as any bill.
  const quote = fromQuote.data;
  useEffect(() => {
    if (!quote) return;
    setPartyId(String(quote.party_id));
    setSiteId(quote.site_id ? String(quote.site_id) : "");
    setLocationId(String(quote.location_id));
    setLines(
      quote.lines.map((x) => ({
        ...emptyLine(),
        itemId: String(x.item_id),
        unit: x.unit,
        quantity: trimDecimal(x.quantity),
        discount: Number(x.discount) > 0 ? trimDecimal(x.discount) : "",
        reason: x.discount_reason ?? "",
      })),
    );
  }, [quote]);

  // Default to the walk-in customer once the list is there.
  useEffect(() => {
    if (!partyId && !fromQuoteId && customers.length > 0) {
      const walkIn = customers.find((c) => c.name === "Walk-in customer");
      if (walkIn) setPartyId(String(walkIn.id));
    }
  }, [customers, partyId, fromQuoteId]);

  // A user with one shop always bills from it; the owner works at every shop, so start on the first.
  useEffect(() => {
    if (onlyShop && locationId !== String(onlyShop.id)) {
      setLocationId(String(onlyShop.id));
    } else if (!locationId) {
      const first = places.find((l) => l.kind === "shop");
      if (first) setLocationId(String(first.id));
    }
  }, [places, locationId, onlyShop]);

  function payload(): InvoiceCreate | null {
    if (!partyId || !locationId) return null;
    const out: InvoiceCreate["lines"] = [];
    for (const l of lines) {
      if (!l.itemId || !DECIMAL.test(l.quantity) || Number(l.quantity) <= 0) return null;
      if (l.discount && !DECIMAL.test(l.discount)) return null;
      if (l.price && !DECIMAL.test(l.price)) return null;
      if (l.slipWeight && (!DECIMAL.test(l.slipWeight) || Number(l.slipWeight) <= 0)) return null;
      if (pays.some((p) => p.amount && !DECIMAL.test(p.amount))) return null;
      out.push({
        item_id: Number(l.itemId),
        quantity: l.quantity,
        unit: l.unit || null,
        source: l.source,
        source_location_id:
          l.source === "godown" && l.sourceLocationId ? Number(l.sourceLocationId) : null,
        purchase_line_id:
          l.source === "direct" && l.purchaseLineId ? Number(l.purchaseLineId) : null,
        slip_weight: l.slipWeight || null,
        weight_note: l.slipWeight && l.weightNote.trim() ? l.weightNote.trim() : null,
        discount: l.discount || null,
        discount_reason: l.discount ? l.reason || null : null,
        rate_override: l.price || null,
        rate_override_reason: l.price ? l.priceReason.trim() || null : null,
      });
    }
    return {
      location_id: Number(locationId),
      party_id: Number(partyId),
      site_id: siteId ? Number(siteId) : null,
      invoice_date: date === todayISO() ? null : date,
      // A vehicle is only asked for when we deliver; it can also be added later on the e-way bill.
      vehicle_no: (siteId && vehicle.trim()) || null,
      remark: remark.trim() || null,
      lines: out,
      payments: pays
        .filter((p) => p.amount)
        .map((p) => ({ mode: p.mode, amount: p.amount, reference: p.reference.trim() || null })),
      approval_ids: approvalIds,
      quote_id: fromQuoteId,
    };
  }

  /** A quotation or proforma carries the same customer and lines, and nothing about payment,
   * delivery vehicle or where the stock comes from. */
  function asQuote(bill: InvoiceCreate, kind: QuoteKind): QuoteCreate {
    return {
      kind,
      location_id: bill.location_id,
      party_id: bill.party_id,
      site_id: bill.site_id,
      valid_until: validUntil || null,
      remark: bill.remark,
      lines: bill.lines.map((l) => ({
        ...l,
        source: "shop",
        source_location_id: null,
        purchase_line_id: null,
        slip_weight: null,
        weight_note: null,
      })),
      approval_ids: bill.approval_ids,
    };
  }

  const body = payload();
  const bodyKey = JSON.stringify([doc, body]);
  useEffect(() => {
    if (!body) {
      setPreview(null);
      setPreviewError(null);
      return;
    }
    const handle = setTimeout(() => {
      (doc === "invoice" ? previewInvoice(body) : previewQuote(asQuote(body, doc)))
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
      if (doc !== "invoice") {
        const saved = await createQuote.mutateAsync(asQuote(body, doc));
        void navigate(`/sales/quotes?open=${saved.id}`);
        return;
      }
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
          {doc === "invoice" ? "New bill" : `New ${QUOTE_LABEL[doc].toLowerCase()}`}
        </h1>
        <Link to="/stock/lost-sales">Asked for, out of stock? Log it</Link>
        {onlyShop ? (
          <p className={styles.sub}>
            Billing from {onlyShop.code} {onlyShop.name}
          </p>
        ) : null}
        <p className={styles.keys}>Enter in Quantity adds a line · Ctrl+Enter saves · Tab moves</p>
      </div>
      {quote ? (
        <p role="status" className={styles.callout}>
          Billing {QUOTE_LABEL[quote.kind].toLowerCase()} {quote.number}. Prices are worked out at
          today&apos;s rates.
        </p>
      ) : null}
      {isQuote ? (
        <p className={styles.sub}>
          Not a tax invoice: it moves no stock and the customer owes nothing until it is billed.
        </p>
      ) : null}
      <div className={styles.entryLayout}>
        <form
          onSubmit={(e) => void onSubmit(e)}
          onKeyDown={onKeyDown}
          noValidate
          className={styles.stack}
        >
          <div className={styles.headerGrid}>
            {fromQuoteId ? null : (
              <SelectField
                label="Document"
                value={doc}
                onChange={(e) => setDoc(e.target.value as Doc)}
              >
                <option value="invoice">Tax invoice</option>
                <option value="quotation">Quotation (estimate)</option>
                <option value="proforma">Proforma invoice</option>
              </SelectField>
            )}
            <div className={styles.stack}>
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
              <Button variant="ghost" onClick={() => setSide({ kind: "customer" })}>
                New customer
              </Button>
            </div>
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
            {onlyShop ? null : (
              <SelectField
                label="Bill from"
                value={locationId}
                error={errors.location}
                onChange={(e) => setLocationId(e.target.value)}
              >
                <option value="">Choose a shop</option>
                {shops.map((l) => (
                  <option key={l.id} value={l.id}>
                    {l.code} {l.name}
                  </option>
                ))}
              </SelectField>
            )}
            {isQuote ? (
              <TextField
                label="Valid until (optional)"
                type="date"
                value={validUntil}
                min={todayISO()}
                onChange={(e) => setValidUntil(e.target.value)}
              />
            ) : null}
            {owner && !isQuote ? (
              <TextField
                label="Bill date"
                type="date"
                value={date}
                max={todayISO()}
                onChange={(e) => setDate(e.target.value)}
              />
            ) : null}
            {siteId && !isQuote ? (
              <TextField
                label="Vehicle no. (optional)"
                value={vehicle}
                onChange={(e) => setVehicle(e.target.value.toUpperCase())}
              />
            ) : null}
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
                  {isQuote ? (
                    <span />
                  ) : (
                    <SelectField
                      label="Taken from"
                      value={l.source}
                      onChange={(e) => setLine(i, { source: e.target.value as FulfilmentSource })}
                    >
                      <option value="shop">Shop</option>
                      <option value="godown">Other place</option>
                      <option value="direct">Supplier direct</option>
                    </SelectField>
                  )}
                  {isQuote ? (
                    <span />
                  ) : l.source === "godown" ? (
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
                  ) : l.source === "direct" ? (
                    <DirectPurchasePick
                      itemId={l.itemId ? Number(l.itemId) : null}
                      value={l.purchaseLineId}
                      onChange={(v) => setLine(i, { purchaseLineId: v })}
                    />
                  ) : (
                    <span />
                  )}
                  <Button
                    variant="ghost"
                    aria-label={`Remove line ${i + 1}`}
                    disabled={lines.length === 1}
                    onClick={() => setLines((rows) => rows.filter((_, j) => j !== i))}
                  >
                    Remove
                  </Button>
                </div>
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
                  <TextField
                    label="Different price (₹ per unit)"
                    inputMode="decimal"
                    className={styles.amount}
                    value={l.price}
                    onChange={(e) => setLine(i, { price: e.target.value })}
                  />
                  {l.price ? (
                    <TextField
                      label="Reason for different price"
                      value={l.priceReason}
                      onChange={(e) => setLine(i, { priceReason: e.target.value })}
                    />
                  ) : null}
                  {isQuote ? null : (
                    <TextField
                      label="Slip weight (optional)"
                      inputMode="decimal"
                      className={styles.amount}
                      value={l.slipWeight}
                      onChange={(e) => setLine(i, { slipWeight: e.target.value })}
                    />
                  )}
                  {row?.weight_flagged && !isQuote ? (
                    <TextField
                      label="Why the weight differs"
                      value={l.weightNote}
                      onChange={(e) => setLine(i, { weightNote: e.target.value })}
                    />
                  ) : null}
                </div>
                {row ? (
                  <p className={styles.sub} aria-live="polite">
                    {row.rate
                      ? `₹${trimDecimal(row.rate)} per ${row.base_unit}${row.rate_source === "customer" ? " (this customer's rate)" : row.rate_source === "override" ? " (price set by hand)" : ""} · ${trimDecimal(row.base_qty)} ${row.base_unit} · taxable ₹${formatMoney(row.taxable)} · GST ${trimDecimal(row.gst_rate)}% · line ₹${formatMoney(row.line_total)}`
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
            {owner ? (
              <Button variant="ghost" onClick={() => setSide({ kind: "item" })}>
                New item
              </Button>
            ) : null}
          </div>
          <fieldset className={styles.lineBlock} style={{ margin: 0 }} hidden={isQuote}>
            <legend className="visually-hidden">Money taken now</legend>
            <strong>Money taken now</strong>
            {pays.map((p, i) => (
              <div key={i} className={styles.chargeRow}>
                <SelectField
                  label={`Paid by ${i + 1}`}
                  value={p.mode}
                  onChange={(e) =>
                    setPays((r) =>
                      r.map((x, j) =>
                        j === i ? { ...x, mode: e.target.value as PaymentMode } : x,
                      ),
                    )
                  }
                >
                  <option value="cash">Cash</option>
                  <option value="upi">UPI</option>
                  <option value="bank">Bank transfer</option>
                </SelectField>
                <TextField
                  label={`Amount ${i + 1} (₹)`}
                  inputMode="decimal"
                  className={styles.amount}
                  value={p.amount}
                  onChange={(e) =>
                    setPays((r) =>
                      r.map((x, j) => (j === i ? { ...x, amount: e.target.value } : x)),
                    )
                  }
                />
                <TextField
                  label="Reference"
                  value={p.reference}
                  onChange={(e) =>
                    setPays((r) =>
                      r.map((x, j) => (j === i ? { ...x, reference: e.target.value } : x)),
                    )
                  }
                />
                <Button
                  variant="ghost"
                  aria-label={`Remove payment ${i + 1}`}
                  onClick={() => setPays((r) => r.filter((_, j) => j !== i))}
                >
                  Remove
                </Button>
              </div>
            ))}
            <div className={styles.actions}>
              <Button
                onClick={() => setPays((r) => [...r, { mode: "cash", amount: "", reference: "" }])}
              >
                Add payment
              </Button>
              {preview && pays.length > 0 && !pays[0]?.amount ? (
                <Button
                  onClick={() =>
                    setPays((r) =>
                      r.map((x, j) => (j === 0 ? { ...x, amount: preview.grand_total } : x)),
                    )
                  }
                >
                  Paid in full
                </Button>
              ) : null}
            </div>
            <p className={styles.sub}>
              Anything not paid now stays on the customer's account, if they are approved for
              credit.
            </p>
          </fieldset>
          <TextField label="Remark" value={remark} onChange={(e) => setRemark(e.target.value)} />
          {serverError ? (
            <p role="alert" className={styles.formError}>
              {serverError.message}
              {serverError.approval ? " Ask the owner to make this bill." : ""}
            </p>
          ) : null}
          {preview?.needs_owner && !owner ? (
            <ApprovalPrompt
              actions={preview.approvals_needed}
              partyId={partyId ? Number(partyId) : null}
              messages={[...preview.invoice_problems, ...preview.lines.flatMap((l) => l.problems)]}
              onApproved={(ids) => setApprovalIds((old) => [...old, ...ids])}
            />
          ) : null}
          <div className={styles.actions}>
            <Button
              type="submit"
              variant="primary"
              disabled={create.isPending || createQuote.isPending || preview?.can_save === false}
            >
              {create.isPending || createQuote.isPending
                ? "Saving…"
                : doc === "invoice"
                  ? "Save bill"
                  : `Save ${QUOTE_LABEL[doc].toLowerCase()}`}
            </Button>
            <Button onClick={() => void navigate("/sales")}>Cancel</Button>
          </div>
        </form>

        {side.kind === "customer" ? (
          <PartyEditor
            key="new-customer"
            onClose={() => setSide({ kind: "totals" })}
            onDone={(p) => {
              setPartyId(String(p.id));
              setSiteId("");
              setSide({ kind: "totals" });
            }}
          />
        ) : side.kind === "item" ? (
          <ItemEditor
            key="new-item"
            onClose={() => setSide({ kind: "totals" })}
            onDone={(it) => {
              const empty = lines.findIndex((l) => !l.itemId);
              if (empty >= 0) {
                setLine(empty, { itemId: String(it.id), unit: "" });
              } else {
                setLines((rows) => [...rows, { ...emptyLine(), itemId: String(it.id) }]);
              }
              setSide({ kind: "totals" });
            }}
          />
        ) : null}

        <aside
          className={styles.preview}
          aria-labelledby="totals-title"
          aria-live="polite"
          hidden={side.kind !== "totals"}
        >
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
              {Number(preview.paid_now) > 0 ? (
                <>
                  <span className={styles.kv}>
                    <span>Paid now</span>
                    <span>{formatMoney(preview.paid_now)}</span>
                  </span>
                  <span className={`${styles.kv} ${styles.kvStrong}`}>
                    <span>Balance on account</span>
                    <span>{formatMoney(preview.balance_due)}</span>
                  </span>
                </>
              ) : null}
              {preview.invoice_problems.map((m) => (
                <p key={m} role="alert" className={styles.problem}>
                  {m}
                </p>
              ))}
              {Number(preview.pending_balance) > 0 ? (
                <p className={styles.callout}>
                  This customer already owes ₹{formatMoney(preview.pending_balance)}.
                </p>
              ) : null}
            </>
          ) : null}
        </aside>
      </div>
    </section>
  );
}
