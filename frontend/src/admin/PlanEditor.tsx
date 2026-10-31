import { useState, type FormEvent } from "react";

import { toFormError, type FormError } from "@/api/errors";
import { Button } from "@/components/Button";
import { CheckField, SelectField, TextAreaField, TextField } from "@/components/Field";
import styles from "@/components/Ledger.module.css";

import { useCreatePlan, useUpdatePlan } from "./api";
import { PlanCard } from "./PlanCard";
import planStyles from "./Plans.module.css";
import type { DurationUnit, Plan, PlanFeature } from "./types";

const UNITS: DurationUnit[] = ["day", "month", "year"];
const MAX_PRICES = 6; // backend app/domain/plans.py MAX_PRICES
const PRICE_TEXT = /^\d{1,10}(\.\d{1,2})?$/;

interface PriceRow {
  value: string;
  unit: DurationUnit;
  price: string;
  active: boolean;
}

/** "999.9" -> "999.90" for the preview only; the server stores what was sent. */
function twoDecimals(text: string): string {
  if (!PRICE_TEXT.test(text)) return "0.00";
  const [whole = "0", fraction = ""] = text.split(".");
  return `${whole}.${fraction.padEnd(2, "0")}`;
}

/** Add or edit a plan, with the card as it will be shown updating beside the form. */
export function PlanEditor({
  plan,
  features,
  onDone,
  onCancel,
}: {
  plan?: Plan;
  features: PlanFeature[];
  onDone: () => void;
  onCancel: () => void;
}) {
  const create = useCreatePlan();
  const update = useUpdatePlan(plan?.id ?? 0);
  const [code, setCode] = useState(plan?.code ?? "");
  const [name, setName] = useState(plan?.name ?? "");
  const [shortText, setShortText] = useState(plan?.short_description ?? "");
  const [longText, setLongText] = useState(plan?.long_description ?? "");
  const [maxUsers, setMaxUsers] = useState(plan?.max_users.toString() ?? "10");
  const [maxLocations, setMaxLocations] = useState(plan?.max_locations.toString() ?? "3");
  const [chosen, setChosen] = useState<string[]>(plan?.features ?? []);
  const [popular, setPopular] = useState(plan?.is_popular ?? false);
  const [sortOrder, setSortOrder] = useState(plan?.sort_order.toString() ?? "0");
  const [rows, setRows] = useState<PriceRow[]>(
    plan?.prices.map((p) => ({
      value: p.duration_value.toString(),
      unit: p.duration_unit,
      price: p.price,
      active: p.is_active,
    })) ?? [{ value: "1", unit: "month", price: "", active: true }],
  );
  const [reason, setReason] = useState("");
  const [error, setError] = useState<FormError | null>(null);
  const fieldError = (key: string) => (error?.field === key ? error.message : null);
  const names = Object.fromEntries(features.map((f) => [f.code, f.name]));
  const pending = create.isPending || update.isPending;

  const setRow = (index: number, change: Partial<PriceRow>) =>
    setRows((all) => all.map((r, i) => (i === index ? { ...r, ...change } : r)));
  const toggle = (featureCode: string) =>
    setChosen((all) =>
      all.includes(featureCode) ? all.filter((c) => c !== featureCode) : [...all, featureCode],
    );

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    const prices = [];
    for (const row of rows) {
      const price = row.price.trim();
      if (!/^\d+$/.test(row.value) || Number(row.value) < 1 || !PRICE_TEXT.test(price)) {
        setError({
          field: "prices",
          message: "Each price needs a whole duration and an amount like 999.90.",
        });
        return;
      }
      prices.push({
        duration_value: Number(row.value),
        duration_unit: row.unit,
        price,
        is_active: row.active,
      });
    }
    const body = {
      name: name.trim(),
      short_description: shortText.trim(),
      long_description: longText.trim(),
      max_users: Number(maxUsers),
      max_locations: Number(maxLocations),
      features: chosen,
      is_popular: popular,
      sort_order: Number(sortOrder) || 0,
      prices,
      reason: reason.trim() || null,
    };
    try {
      if (plan) await update.mutateAsync(body);
      else await create.mutateAsync({ ...body, code: code.trim() });
      onDone();
    } catch (err) {
      setError(toFormError(err));
    }
  }

  return (
    <div className={planStyles.editor}>
      <form className={styles.panel} onSubmit={(e) => void onSubmit(e)} noValidate>
        <h2 className={styles.panelHead}>{plan ? `Edit ${plan.name}` : "Add a plan"}</h2>
        {plan ? null : (
          <TextField
            label="Code"
            value={code}
            onChange={(e) => setCode(e.target.value.toUpperCase())}
            hint="Capital letters, digits and underscores, such as GOLD_2027. It cannot change later."
            error={fieldError("code")}
            autoComplete="off"
            required
          />
        )}
        <TextField
          label="Name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          error={fieldError("name")}
          required
        />
        <TextField
          label="Short description"
          value={shortText}
          onChange={(e) => setShortText(e.target.value)}
          maxLength={200}
        />
        <TextAreaField
          label="Long description"
          value={longText}
          onChange={(e) => setLongText(e.target.value)}
        />
        <div className={styles.grid}>
          <TextField
            label="Users"
            inputMode="numeric"
            value={maxUsers}
            onChange={(e) => setMaxUsers(e.target.value.replace(/\D/g, ""))}
            hint="Active users a company may have."
            error={fieldError("max_users")}
          />
          <TextField
            label="Shops and godowns"
            inputMode="numeric"
            value={maxLocations}
            onChange={(e) => setMaxLocations(e.target.value.replace(/\D/g, ""))}
            error={fieldError("max_locations")}
          />
          <TextField
            label="Order"
            inputMode="numeric"
            value={sortOrder}
            onChange={(e) => setSortOrder(e.target.value.replace(/\D/g, ""))}
            hint="Smaller numbers come first."
          />
        </div>

        <fieldset className={styles.group}>
          <legend>Prices (1 to {MAX_PRICES})</legend>
          {rows.map((row, i) => (
            <div key={i} className={planStyles.priceRow}>
              <TextField
                label={`Length ${i + 1}`}
                inputMode="numeric"
                value={row.value}
                onChange={(e) => setRow(i, { value: e.target.value.replace(/\D/g, "") })}
              />
              <SelectField
                label={`Unit ${i + 1}`}
                value={row.unit}
                onChange={(e) => setRow(i, { unit: e.target.value as DurationUnit })}
              >
                {UNITS.map((u) => (
                  <option key={u} value={u}>
                    {u}s
                  </option>
                ))}
              </SelectField>
              <TextField
                label={`Price ${i + 1} (rupees)`}
                inputMode="decimal"
                value={row.price}
                onChange={(e) => setRow(i, { price: e.target.value.replace(/[^\d.]/g, "") })}
                placeholder="999.90"
              />
              <Button
                disabled={rows.length === 1}
                onClick={() => setRows((all) => all.filter((_, j) => j !== i))}
                aria-label={`Remove price ${i + 1}`}
              >
                Remove
              </Button>
            </div>
          ))}
          {fieldError("prices") ? (
            <p role="alert" className={styles.formError}>
              {fieldError("prices")}
            </p>
          ) : null}
          <div className={styles.actions}>
            <Button
              disabled={rows.length >= MAX_PRICES}
              onClick={() =>
                setRows((all) => [...all, { value: "1", unit: "month", price: "", active: true }])
              }
            >
              Add a price
            </Button>
          </div>
        </fieldset>

        <fieldset className={styles.group}>
          <legend>Features listed on the card</legend>
          <p className={styles.note}>
            This only lists what the plan includes. It does not switch anything on or off yet.
          </p>
          <div className={planStyles.featureGrid}>
            {features.map((f) => (
              <CheckField
                key={f.code}
                label={f.name}
                hint={f.description}
                checked={chosen.includes(f.code)}
                onChange={() => toggle(f.code)}
              />
            ))}
          </div>
        </fieldset>

        <CheckField
          label="Popular"
          hint="Highlights this plan. Only one plan can be popular: choosing it here clears the other."
          checked={popular}
          onChange={(e) => setPopular(e.target.checked)}
        />
        <TextField
          label="Reason (optional)"
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          hint="Kept in the audit log."
        />
        {error && !error.field ? (
          <p role="alert" className={styles.formError}>
            {error.message}
          </p>
        ) : null}
        <div className={styles.actions}>
          <Button type="submit" variant="primary" disabled={pending}>
            {pending ? "Saving…" : plan ? "Save plan" : "Add plan"}
          </Button>
          <Button onClick={onCancel}>Cancel</Button>
        </div>
      </form>

      <div className={planStyles.preview}>
        <p className={planStyles.previewLabel}>Preview</p>
        <PlanCard
          featureNames={names}
          plan={{
            code: plan?.code ?? (code || "CODE"),
            name,
            short_description: shortText,
            max_users: Number(maxUsers) || 0,
            max_locations: Number(maxLocations) || 0,
            features: chosen,
            is_popular: popular,
            is_active: plan?.is_active ?? true,
            prices: rows.map((r) => ({
              duration_value: Number(r.value) || 1,
              duration_unit: r.unit,
              price: twoDecimals(r.price.trim()),
            })),
          }}
        />
      </div>
    </div>
  );
}
