import { useEffect, useRef, useState, type FormEvent } from "react";

import { toFormError, type FormError } from "@/api/errors";
import { useCreateItem, useUpdateItem, type ItemRow } from "@/api/masters";
import type { ItemCategory, ItemCreate, ItemOwner } from "@/api/types";
import { Button } from "@/components/Button";
import { CheckField, SelectField, TextField } from "@/components/Field";
import styles from "@/components/Ledger.module.css";
import { trimDecimal } from "@/lib/format";

import { Converter } from "./Converter";
import { CATEGORIES } from "./itemLabels";

interface UnitRow {
  unit: string;
  factor: string;
  whole: boolean;
}

const T = {
  newTitle: "New item",
  create: "Create item",
  save: "Save changes",
  close: "Close",
  baseFixed: "The base unit cannot change once the item exists.",
};

/** Read-only view for counter staff and the accountant: no margin figures reach them. */
export function ItemDetail({ item, onClose }: { item: ItemRow; onClose: () => void }) {
  return (
    <aside
      className={styles.panel}
      aria-labelledby="item-detail"
      onKeyDown={(e) => e.key === "Escape" && onClose()}
    >
      <div className={styles.panelHead}>
        <h2 id="item-detail">{item.name}</h2>
        <Button variant="quiet" onClick={onClose}>
          {T.close}
        </Button>
      </div>
      <dl className={styles.stack}>
        <div>
          <dt className={styles.sub}>HSN and GST</dt>
          <dd>
            {item.hsn} at {item.gst_rate}%
          </dd>
        </div>
        <div>
          <dt className={styles.sub}>Counted in</dt>
          <dd>{item.base_unit}</dd>
        </div>
        <div>
          <dt className={styles.sub}>Other units</dt>
          <dd>
            {item.units.length
              ? item.units
                  .map((u) => `1 ${u.unit} = ${trimDecimal(u.factor_to_base)} ${item.base_unit}`)
                  .join(", ")
              : "None"}
          </dd>
        </div>
        {item.weight_per_piece_kg ? (
          <div>
            <dt className={styles.sub}>Weight per piece</dt>
            <dd>{item.weight_per_piece_kg} kg</dd>
          </div>
        ) : null}
      </dl>
      <Converter item={item} />
    </aside>
  );
}

export function ItemEditor({
  item,
  onClose,
  onDone,
}: {
  item?: ItemOwner;
  onClose: () => void;
  onDone: (item: ItemOwner) => void;
}) {
  const create = useCreateItem();
  const update = useUpdateItem();
  const [name, setName] = useState(item?.name ?? "");
  const [category, setCategory] = useState<ItemCategory>(item?.category ?? "tmt");
  const [brand, setBrand] = useState(item?.brand ?? "");
  const [hsn, setHsn] = useState(item?.hsn ?? "");
  const [gst, setGst] = useState(item?.gst_rate ?? "18");
  const [base, setBase] = useState(item?.base_unit ?? "kg");
  const [baseWhole, setBaseWhole] = useState(item?.base_whole_only ?? false);
  const [size, setSize] = useState(item?.size ?? "");
  const [grade, setGrade] = useState(item?.grade ?? "");
  const [weight, setWeight] = useState(item?.weight_per_piece_kg ?? "");
  const [margin, setMargin] = useState(trimDecimal(item?.min_margin ?? "0"));
  const [leadDays, setLeadDays] = useState(item?.lead_time_days?.toString() ?? "");
  const [safetyDays, setSafetyDays] = useState(item?.safety_days?.toString() ?? "");
  const [active, setActive] = useState(item?.is_active ?? true);
  const [units, setUnits] = useState<UnitRow[]>(
    item?.units.map((u) => ({
      unit: u.unit,
      factor: trimDecimal(u.factor_to_base),
      whole: u.whole_only,
    })) ?? [],
  );
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [serverError, setServerError] = useState<FormError | null>(null);
  const first = useRef<HTMLInputElement>(null);
  useEffect(() => first.current?.focus(), []);

  const titleId = `item-editor-${item?.id ?? "new"}`;
  const pending = create.isPending || update.isPending;

  function validate() {
    const found: Record<string, string> = {};
    if (!name.trim()) found.name = "Enter the item name as it should print on bills.";
    if (!/^\d{4,8}$/.test(hsn)) found.hsn = "HSN is 4 to 8 digits.";
    if (!/^\d+(\.\d{1,2})?$/.test(gst) || Number(gst) > 100)
      found.gst_rate = "Enter a rate like 18.";
    if (!base.trim()) found.base_unit = "Enter what stock is counted in, e.g. kg or bag.";
    if (weight && !/^\d+(\.\d{1,3})?$/.test(weight))
      found.weight_per_piece_kg = "Up to 3 decimals.";
    if (!/^\d+(\.\d{1,4})?$/.test(margin)) found.min_margin = "Enter an amount like 1.25.";
    if (leadDays && (!/^\d{1,3}$/.test(leadDays) || Number(leadDays) > 365))
      found.lead_time_days = "Enter whole days, 0 to 365.";
    if (safetyDays && (!/^\d{1,3}$/.test(safetyDays) || Number(safetyDays) > 365))
      found.safety_days = "Enter whole days, 0 to 365.";
    const names = units.map((u) => u.unit.trim().toLowerCase());
    if (
      units.some(
        (u) => !u.unit.trim() || !/^\d+(\.\d{1,6})?$/.test(u.factor) || Number(u.factor) <= 0,
      )
    ) {
      found.units = "Each unit needs a name and a factor above 0.";
    } else if (new Set(names).size !== names.length) {
      found.units = "A unit is listed twice.";
    } else if (names.includes(base.trim().toLowerCase())) {
      found.units = "The base unit is implicit; do not list it again.";
    }
    return found;
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    const found = validate();
    setErrors(found);
    setServerError(null);
    if (Object.keys(found).length > 0) return;
    const unitBody = units.map((u) => ({
      unit: u.unit.trim(),
      factor_to_base: u.factor,
      whole_only: u.whole,
    }));
    const common = {
      name: name.trim(),
      category,
      brand: brand.trim() || null,
      hsn,
      gst_rate: gst,
      size: size.trim() || null,
      grade: grade.trim() || null,
      weight_per_piece_kg: weight || null,
      min_margin: margin,
      lead_time_days: leadDays ? Number(leadDays) : null,
      safety_days: safetyDays ? Number(safetyDays) : null,
      units: unitBody,
      is_active: active,
    };
    try {
      const saved = item
        ? await update.mutateAsync({ id: item.id, body: common })
        : await create.mutateAsync({
            ...common,
            base_unit: base.trim(),
            base_whole_only: baseWhole,
          } satisfies ItemCreate);
      onDone(saved);
    } catch (err) {
      setServerError(toFormError(err));
    }
  }

  const fieldError = (key: string) =>
    errors[key] ?? (serverError?.field === key ? serverError.message : null);
  const known = [
    "name",
    "hsn",
    "gst_rate",
    "base_unit",
    "weight_per_piece_kg",
    "min_margin",
    "lead_time_days",
    "safety_days",
    "units",
  ];
  const general =
    serverError && !known.includes(serverError.field ?? "") ? serverError.message : null;

  return (
    <aside
      className={styles.panel}
      aria-labelledby={titleId}
      onKeyDown={(e) => e.key === "Escape" && onClose()}
    >
      <div className={styles.panelHead}>
        <h2 id={titleId}>{item ? item.name : T.newTitle}</h2>
        <Button variant="quiet" onClick={onClose}>
          {T.close}
        </Button>
      </div>
      <form onSubmit={(e) => void onSubmit(e)} noValidate>
        <TextField
          ref={first}
          label="Name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          error={fieldError("name")}
        />
        <SelectField
          label="Category"
          value={category}
          onChange={(e) => setCategory(e.target.value as ItemCategory)}
        >
          {CATEGORIES.map((c) => (
            <option key={c.value} value={c.value}>
              {c.label}
            </option>
          ))}
        </SelectField>
        <TextField
          label="Brand"
          hint="Rates and margins are per brand (G8)."
          value={brand}
          onChange={(e) => setBrand(e.target.value)}
        />
        <div className={styles.inline}>
          <TextField
            label="HSN"
            inputMode="numeric"
            maxLength={8}
            className={styles.code}
            value={hsn}
            onChange={(e) => setHsn(e.target.value)}
            error={fieldError("hsn")}
          />
          <TextField
            label="GST %"
            inputMode="decimal"
            className={styles.amount}
            value={gst}
            onChange={(e) => setGst(e.target.value)}
            error={fieldError("gst_rate")}
          />
          <span />
        </div>
        <TextField
          label="Counted in"
          value={base}
          readOnly={Boolean(item)}
          onChange={(e) => setBase(e.target.value)}
          error={fieldError("base_unit")}
          hint={item ? T.baseFixed : "What stock is counted in: kg, bag or piece."}
        />
        {item ? null : (
          <CheckField
            label="Whole numbers only"
            checked={baseWhole}
            onChange={(e) => setBaseWhole(e.target.checked)}
            hint="Tick for bags and pieces that cannot be split."
          />
        )}
        <div className={styles.inline}>
          <TextField label="Size" value={size} onChange={(e) => setSize(e.target.value)} />
          <TextField label="Grade" value={grade} onChange={(e) => setGrade(e.target.value)} />
          <span />
        </div>
        <TextField
          label="Weight per piece (kg)"
          rule="G7"
          inputMode="decimal"
          className={styles.amount}
          value={weight}
          onChange={(e) => setWeight(e.target.value)}
          error={fieldError("weight_per_piece_kg")}
          hint="Theoretical weight; billing by piece converts with it."
        />
        <TextField
          label="Warn below margin (₹ per unit)"
          rule="B5"
          inputMode="decimal"
          className={styles.amount}
          value={margin}
          onChange={(e) => setMargin(e.target.value)}
          error={fieldError("min_margin")}
          hint="Owner only. Never shown to counter staff."
        />
        <TextField
          label="Lead time (days)"
          rule="FM6"
          inputMode="numeric"
          className={styles.amount}
          value={leadDays}
          onChange={(e) => setLeadDays(e.target.value)}
          error={fieldError("lead_time_days")}
          hint="Days from ordering to delivery. Blank uses the supplier's, then the shop's (Settings)."
        />
        <TextField
          label="Safety stock (days of sales)"
          rule="FM6"
          inputMode="numeric"
          className={styles.amount}
          value={safetyDays}
          onChange={(e) => setSafetyDays(e.target.value)}
          error={fieldError("safety_days")}
          hint="Extra stock kept for a bad week. Blank uses the shop's (Settings)."
        />
        <fieldset className={styles.choices} aria-describedby={`${titleId}-units-error`}>
          <legend>Other units</legend>
          {units.map((u, i) => (
            <div key={i} className={styles.inline}>
              <TextField
                label={`Unit ${i + 1}`}
                value={u.unit}
                onChange={(e) =>
                  setUnits((rows) =>
                    rows.map((r, j) => (j === i ? { ...r, unit: e.target.value } : r)),
                  )
                }
              />
              <TextField
                label={`${base || "base"} per unit`}
                inputMode="decimal"
                className={styles.amount}
                value={u.factor}
                onChange={(e) =>
                  setUnits((rows) =>
                    rows.map((r, j) => (j === i ? { ...r, factor: e.target.value } : r)),
                  )
                }
              />
              <Button
                variant="quiet"
                aria-label={`Remove unit ${i + 1}`}
                onClick={() => setUnits((rows) => rows.filter((_, j) => j !== i))}
              >
                Remove
              </Button>
            </div>
          ))}
          <div className={styles.actions}>
            <Button
              onClick={() => setUnits((rows) => [...rows, { unit: "", factor: "", whole: false }])}
            >
              Add unit
            </Button>
          </div>
          {fieldError("units") ? (
            <p id={`${titleId}-units-error`} className={styles.formError}>
              {fieldError("units")}
            </p>
          ) : null}
        </fieldset>
        {item ? (
          <CheckField
            label="Active"
            checked={active}
            onChange={(e) => setActive(e.target.checked)}
            hint="Inactive items stay on old bills but cannot be sold or bought."
          />
        ) : null}
        {general ? (
          <p role="alert" className={styles.formError}>
            {general}
          </p>
        ) : null}
        <div className={styles.actions}>
          <Button type="submit" variant="primary" disabled={pending}>
            {pending ? "Saving…" : item ? T.save : T.create}
          </Button>
        </div>
      </form>
      {item ? <Converter item={item} /> : null}
    </aside>
  );
}
