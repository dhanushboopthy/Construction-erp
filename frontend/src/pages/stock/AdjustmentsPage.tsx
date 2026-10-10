import { useState, type FormEvent } from "react";

import { useAdjustments, useCreateAdjustment } from "@/api/adjustments";
import { ApiError } from "@/api/client";
import { toFormError } from "@/api/errors";
import { useItems } from "@/api/masters";
import { useLocations } from "@/api/setup";
import type {
  AdjustmentBookOwner,
  AdjustmentOwner,
  AdjustmentReason,
  StockDirection,
} from "@/api/types";
import { useAuth } from "@/auth/AuthContext";
import { ApprovalPrompt } from "@/components/ApprovalPrompt";
import { Button } from "@/components/Button";
import { SelectField, TextField } from "@/components/Field";
import styles from "@/components/Ledger.module.css";
import { formatMoney, trimDecimal } from "@/lib/format";
import { unitNames } from "@/pages/items/itemLabels";

const REASON: Record<AdjustmentReason, { label: string; hint: string }> = {
  breakage: { label: "Breakage", hint: "Torn cement bags, cracked pipes." },
  damage: { label: "Rust or damage", hint: "Rusted steel, cement that has set, water damage." },
  theft: { label: "Theft", hint: "Stock stolen from the shop or the godown." },
  free_sample: { label: "Free sample", hint: "Given away to a customer or a mason." },
  weighbridge_loss: {
    label: "Weighbridge loss",
    hint: "The weighbridge showed less than the supplier billed.",
  },
  weighbridge_gain: {
    label: "Weighbridge gain",
    hint: "The weighbridge showed more than the supplier billed.",
  },
  count_correction: {
    label: "Count correction",
    hint: "The shelf differs from the books. Say for each item whether it is more or less.",
  },
};
const ORDER: AdjustmentReason[] = [
  "breakage",
  "damage",
  "theft",
  "free_sample",
  "weighbridge_loss",
  "weighbridge_gain",
  "count_correction",
];
const ONLY: Partial<Record<AdjustmentReason, StockDirection>> = { weighbridge_gain: "in" };

interface Row {
  itemId: string;
  quantity: string;
  unit: string;
  direction: StockDirection | "";
}
const EMPTY: Row = { itemId: "", quantity: "", unit: "", direction: "" };

function rupees(value: string) {
  const n = Number(value);
  return `${n < 0 ? "−" : ""}₹${formatMoney(String(Math.abs(n)))}`;
}

/** Stock that leaves or arrives without a bill (FM2): every adjustment has a reason, so losses
 * show by cause. Above the owner's limit, counter staff need the owner's PIN. */
export function AdjustmentsPage() {
  const { user } = useAuth();
  const owner = user?.role === "owner";
  const canWrite = owner || user?.role === "counter";
  const locations = useLocations();
  const places = (locations.data ?? []).filter(
    (l) => l.is_active && (owner || user?.locations.some((x) => x.id === l.id)),
  );
  const [placeId, setPlaceId] = useState("");
  const place = placeId || (places[0] ? String(places[0].id) : "");
  const book = useAdjustments("", "", "");
  const create = useCreateAdjustment();
  const items = useItems("", "");
  const itemList = (items.data?.items ?? []).filter((i) => i.is_active);

  const [reason, setReason] = useState<AdjustmentReason>("breakage");
  const [rows, setRows] = useState<Row[]>([EMPTY]);
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [needsOwner, setNeedsOwner] = useState<string | null>(null);
  const [saved, setSaved] = useState<string | null>(null);

  const askDirection = reason === "count_correction";
  const setRow = (i: number, patch: Partial<Row>) =>
    setRows((rs) => rs.map((r, j) => (j === i ? { ...r, ...patch } : r)));

  async function save(approvalIds: number[] = []) {
    setSaved(null);
    if (!place) return setError("Pick the shop or godown.");
    if (
      rows.some(
        (r) => !r.itemId || !/^\d+(\.\d{1,3})?$/.test(r.quantity) || Number(r.quantity) <= 0,
      )
    )
      return setError("Every line needs an item and a quantity above 0.");
    if (askDirection && rows.some((r) => !r.direction))
      return setError("Say for each item whether the count found more or less.");
    setError(null);
    try {
      const made = await create.mutateAsync({
        location_id: Number(place),
        reason,
        note: note.trim() || null,
        approval_ids: approvalIds,
        lines: rows.map((r) => ({
          item_id: Number(r.itemId),
          quantity: r.quantity,
          unit: r.unit || null,
          direction: askDirection ? (r.direction as StockDirection) : (ONLY[reason] ?? "out"),
        })),
      });
      setNeedsOwner(null);
      setSaved(`${made.number} saved: ${REASON[made.reason].label}.`);
      setRows([EMPTY]);
      setNote("");
    } catch (err) {
      if (err instanceof ApiError && err.requiresOwnerApproval) return setNeedsOwner(err.message);
      setError(toFormError(err).message);
    }
  }

  const b = book.data;
  const costed = b && "net_loss" in b ? (b as AdjustmentBookOwner) : null;

  return (
    <div className={styles.stack}>
      {canWrite ? (
        <form
          className={styles.stack}
          aria-label="New adjustment"
          noValidate
          onSubmit={(e: FormEvent) => {
            e.preventDefault();
            void save();
          }}
        >
          <div className={styles.headerGrid}>
            {places.length > 1 ? (
              <SelectField label="Where" value={place} onChange={(e) => setPlaceId(e.target.value)}>
                {places.map((l) => (
                  <option key={l.id} value={l.id}>
                    {l.code} {l.name}
                  </option>
                ))}
              </SelectField>
            ) : null}
            <SelectField
              label="Reason"
              value={reason}
              onChange={(e) => setReason(e.target.value as AdjustmentReason)}
            >
              {ORDER.map((r) => (
                <option key={r} value={r}>
                  {REASON[r].label}
                </option>
              ))}
            </SelectField>
            <TextField label="Note" value={note} onChange={(e) => setNote(e.target.value)} />
          </div>
          <p className={styles.note}>{REASON[reason].hint}</p>
          {rows.map((r, i) => {
            const item = itemList.find((x) => String(x.id) === r.itemId);
            return (
              <div key={i} className={styles.entryRow}>
                <SelectField
                  label={`Item ${i + 1}`}
                  value={r.itemId}
                  onChange={(e) => setRow(i, { itemId: e.target.value, unit: "" })}
                >
                  <option value="">Choose an item</option>
                  {itemList.map((it) => (
                    <option key={it.id} value={it.id}>
                      {it.name}
                    </option>
                  ))}
                </SelectField>
                {askDirection ? (
                  <SelectField
                    label="Found"
                    value={r.direction}
                    onChange={(e) => setRow(i, { direction: e.target.value as StockDirection })}
                  >
                    <option value="">Choose</option>
                    <option value="out">Less than the books</option>
                    <option value="in">More than the books</option>
                  </SelectField>
                ) : null}
                <TextField
                  label="Quantity"
                  inputMode="decimal"
                  className={styles.amount}
                  value={r.quantity}
                  onChange={(e) => setRow(i, { quantity: e.target.value })}
                />
                <SelectField
                  label="Unit"
                  value={r.unit || item?.base_unit || ""}
                  onChange={(e) => setRow(i, { unit: e.target.value })}
                >
                  {item ? (
                    unitNames(item).map((u) => <option key={u}>{u}</option>)
                  ) : (
                    <option value="">—</option>
                  )}
                </SelectField>
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
          {needsOwner ? (
            <ApprovalPrompt
              actions={["stock_adjustment"]}
              partyId={null}
              messages={[needsOwner]}
              onApproved={(ids) => void save(ids)}
            />
          ) : null}
          {error ? (
            <p role="alert" className={styles.formError}>
              {error}
            </p>
          ) : null}
          {saved ? (
            <p role="status" className={styles.saved}>
              {saved}
            </p>
          ) : null}
          <div className={styles.actions}>
            <Button onClick={() => setRows((rs) => [...rs, EMPTY])}>Add line</Button>
            <Button type="submit" variant="primary" disabled={create.isPending}>
              Post adjustment
            </Button>
          </div>
        </form>
      ) : null}

      {costed ? (
        <div className={styles.totalBand} aria-label="This month">
          <span>
            Stock lost this month <strong className="num">{rupees(costed.net_loss)}</strong>
          </span>
          {costed.by_reason.map((r) => (
            <span key={r.reason}>
              {r.reason_label} <strong className="num">{rupees(r.value)}</strong>
            </span>
          ))}
          <span>
            ITC to reverse <strong className="num">{rupees(costed.itc_to_reverse)}</strong>
          </span>
        </div>
      ) : null}

      <div className={styles.tableWrap}>
        <table className={styles.table} aria-label="Adjustments this month">
          <thead>
            <tr>
              <th scope="col">Number</th>
              <th scope="col">Date</th>
              <th scope="col">Reason</th>
              <th scope="col">Items</th>
              <th scope="col">Entered by</th>
              {costed ? (
                <th scope="col" className="num">
                  Value lost
                </th>
              ) : null}
            </tr>
          </thead>
          <tbody>
            {(b?.entries ?? []).map((a) => (
              <tr key={a.id}>
                <td className={styles.code}>{a.number}</td>
                <td>{a.adjustment_date}</td>
                <td>
                  {a.reason_label}
                  {a.approved ? <span className={styles.sub}> · owner approved</span> : null}
                  {a.note ? <span className={styles.sub}> · {a.note}</span> : null}
                </td>
                <td>
                  {a.lines
                    .map(
                      (l) =>
                        `${l.direction === "in" ? "+" : "−"}${trimDecimal(l.quantity)} ${l.base_unit} ${l.item_name}`,
                    )
                    .join(", ")}
                </td>
                <td>{a.created_by_name ?? "—"}</td>
                {costed ? <td className="num">{rupees((a as AdjustmentOwner).value)}</td> : null}
              </tr>
            ))}
          </tbody>
        </table>
        {b && b.entries.length === 0 ? (
          <p className={styles.empty}>
            No adjustments this month. Record breakage, rust, theft or a weighbridge difference
            here, so the stock and the profit stay true.
          </p>
        ) : null}
      </div>
    </div>
  );
}
