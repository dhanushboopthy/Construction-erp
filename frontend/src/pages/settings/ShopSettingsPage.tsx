import { useEffect, useState, type FormEvent, type ReactNode } from "react";

import { toFormError, type FormError } from "@/api/errors";
import { useSaveShopSettings, useShopSettings } from "@/api/setup";
import type { ShopSettings, ShopSettingsUpdate } from "@/api/types";
import { Button } from "@/components/Button";
import { CheckField, SelectField, TextAreaField, TextField } from "@/components/Field";
import { isAmount } from "@/lib/format";
import { GST_STATES } from "@/lib/gstStates";

import styles from "@/components/Ledger.module.css";

const MONTHS = [
  "January",
  "February",
  "March",
  "April",
  "May",
  "June",
  "July",
  "August",
  "September",
  "October",
  "November",
  "December",
];

// Strings in one place so Tamil labels can be added later (docs/DESIGN.md, principle 7).
const T = {
  loading: "Loading shop details…",
  loadFailed: "Shop details could not be loaded.",
  save: "Save shop details",
  saving: "Saving…",
  saved: "Shop details saved.",
  unsaved: "You have unsaved changes.",
  fixErrors: "Some values need fixing. They are marked below.",
};

type Form = {
  [K in keyof ShopSettingsUpdate]-?: string | boolean;
};

const TEXT_KEYS = [
  "legal_name",
  "trade_name",
  "gstin",
  "state_code",
  "address",
  "phone",
  "email",
  "bank_name",
  "bank_account_no",
  "bank_ifsc",
  "invoice_terms",
  "timezone",
] as const;
const INT_KEYS = [
  "financial_year_start_month",
  "return_window_days",
  "default_credit_days",
] as const;
const AMOUNT_KEYS = [
  "weight_variance_pct",
  "default_credit_limit",
  "cash_receipt_limit",
  "eway_threshold_interstate",
  "eway_threshold_intrastate",
  "expense_approval_limit",
  "adjustment_approval_limit",
] as const;
const FLAG_KEYS = [
  "include_gst_in_cost",
  "rates_include_gst",
  "einvoice_enabled",
  "counter_can_enter_purchases",
  "itc_reverse_shortages",
] as const;
const OPTIONAL = new Set([
  "trade_name",
  "gstin",
  "phone",
  "email",
  "bank_name",
  "bank_account_no",
  "bank_ifsc",
  "invoice_terms",
]);

function toForm(s: ShopSettings): Form {
  const form = {} as Record<string, string | boolean>;
  for (const k of TEXT_KEYS) form[k] = s[k] ?? "";
  for (const k of INT_KEYS) form[k] = String(s[k]);
  for (const k of AMOUNT_KEYS) form[k] = s[k];
  for (const k of FLAG_KEYS) form[k] = s[k];
  return form as Form;
}

function validate(form: Form): Record<string, string> {
  const errors: Record<string, string> = {};
  const text = (k: keyof Form) => String(form[k]).trim();
  if (!text("legal_name")) errors.legal_name = "Enter the legal name printed on bills.";
  const gstin = text("gstin").toUpperCase();
  if (gstin && !/^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$/.test(gstin)) {
    errors.gstin = "A GSTIN has 15 characters, like 33ABCDE1234F1Z5.";
  } else if (gstin && gstin.slice(0, 2) !== text("state_code")) {
    errors.gstin = "The first two digits of the GSTIN must match the state.";
  }
  const ifsc = text("bank_ifsc").toUpperCase();
  if (ifsc && !/^[A-Z]{4}0[A-Z0-9]{6}$/.test(ifsc)) {
    errors.bank_ifsc = "An IFSC has 11 characters, like SBIN0001234.";
  }
  const days = (k: keyof Form, max: number) => {
    const v = text(k);
    if (!/^\d+$/.test(v) || Number(v) > max) errors[k] = `Enter whole days from 0 to ${max}.`;
  };
  days("return_window_days", 30);
  days("default_credit_days", 365);
  for (const k of AMOUNT_KEYS) {
    if (!isAmount(text(k))) errors[k] = "Enter an amount like 10000 or 10000.50.";
  }
  if (!errors.weight_variance_pct && Number(text("weight_variance_pct")) > 100) {
    errors.weight_variance_pct = "A percentage cannot be above 100.";
  }
  return errors;
}

function toPayload(form: Form): ShopSettingsUpdate {
  const out = {} as Record<string, string | number | boolean | null>;
  for (const k of TEXT_KEYS) {
    let v = String(form[k]).trim();
    if (k === "gstin" || k === "bank_ifsc") v = v.toUpperCase();
    out[k] = v === "" && OPTIONAL.has(k) ? null : v;
  }
  for (const k of INT_KEYS) out[k] = Number(form[k]);
  for (const k of AMOUNT_KEYS) out[k] = String(form[k]).trim(); // decimals travel as strings
  for (const k of FLAG_KEYS) out[k] = Boolean(form[k]);
  return out as unknown as ShopSettingsUpdate;
}

function Group({ title, note, children }: { title: string; note: string; children: ReactNode }) {
  const id = `group-${title.toLowerCase().replace(/\W+/g, "-")}`;
  return (
    <section className={styles.group} aria-labelledby={id}>
      <div className={styles.groupHead}>
        <h2 id={id}>{title}</h2>
        <p>{note}</p>
      </div>
      <div className={styles.grid}>{children}</div>
    </section>
  );
}

export function ShopSettingsPage() {
  const query = useShopSettings();
  if (query.isPending) return <p role="status">{T.loading}</p>;
  if (query.isError) return <p className={styles.formError}>{T.loadFailed}</p>;
  return <ShopSettingsForm settings={query.data} />;
}

function ShopSettingsForm({ settings }: { settings: ShopSettings }) {
  const save = useSaveShopSettings();
  const [form, setForm] = useState<Form>(() => toForm(settings));
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [serverError, setServerError] = useState<FormError | null>(null);
  const [dirty, setDirty] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    setForm(toForm(settings));
  }, [settings]);

  const set = (key: keyof Form) => (value: string | boolean) => {
    setForm((f) => ({ ...f, [key]: value }));
    setDirty(true);
    setSaved(false);
  };
  const text = (key: keyof Form) => ({
    name: key,
    value: String(form[key]),
    onChange: (e: { target: { value: string } }) => set(key)(e.target.value),
    error: errors[key] ?? (serverError?.field === key ? serverError.message : null),
  });
  const flag = (key: keyof Form) => ({
    name: key,
    checked: Boolean(form[key]),
    onChange: (e: { target: { checked: boolean } }) => set(key)(e.target.checked),
  });

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    const found = validate(form);
    setErrors(found);
    setServerError(null);
    if (Object.keys(found).length > 0) {
      document.getElementsByName(Object.keys(found)[0] ?? "")[0]?.focus();
      return;
    }
    try {
      await save.mutateAsync(toPayload(form));
      setDirty(false);
      setSaved(true);
    } catch (err) {
      setServerError(toFormError(err));
    }
  }

  const hasErrors = Object.keys(errors).length > 0;

  return (
    <form className={styles.sheet} onSubmit={(e) => void onSubmit(e)} noValidate>
      <Group title="On every bill" note="Printed at the top of invoices and statements.">
        <TextField
          label="Legal name"
          required
          {...text("legal_name")}
          autoComplete="organization"
        />
        <TextField
          label="Trade name"
          hint="Leave blank if same as legal name."
          {...text("trade_name")}
        />
        <TextField
          label="GSTIN"
          hint="Leave blank only if the shop is not registered yet."
          maxLength={15}
          className={styles.code}
          {...text("gstin")}
        />
        <SelectField label="State" {...text("state_code")}>
          {GST_STATES.map((s) => (
            <option key={s.code} value={s.code}>
              {s.code} {s.name}
            </option>
          ))}
        </SelectField>
        <TextField label="Phone" type="tel" {...text("phone")} />
        <TextField label="Email" type="email" {...text("email")} />
        <div className={styles.wide}>
          <TextAreaField label="Address" {...text("address")} />
        </div>
      </Group>

      <Group
        title="Bank and bill footer"
        note="Customers pay into this account; terms print under the total."
      >
        <TextField label="Bank name" {...text("bank_name")} />
        <TextField
          label="Account number"
          inputMode="numeric"
          className={styles.code}
          {...text("bank_account_no")}
        />
        <TextField label="IFSC" maxLength={11} className={styles.code} {...text("bank_ifsc")} />
        <div className={styles.wide}>
          <TextAreaField label="Terms on the bill" {...text("invoice_terms")} />
        </div>
      </Group>

      <Group
        title="Credit and returns"
        note="Defaults for new customers. Each customer can have their own limit and days."
      >
        <TextField
          label="Credit limit (₹)"
          rule="B8"
          inputMode="decimal"
          className={styles.amount}
          {...text("default_credit_limit")}
        />
        <TextField
          label="Credit days"
          rule="B8"
          inputMode="numeric"
          className={styles.amount}
          hint="Due date = bill date + these days."
          {...text("default_credit_days")}
        />
        <TextField
          label="Return window (days)"
          rule="B11"
          inputMode="numeric"
          className={styles.amount}
          hint="Later returns need the owner."
          {...text("return_window_days")}
        />
      </Group>

      <Group
        title="Purchases and costing"
        note="Who enters purchases, and how cost and daily rates treat GST."
      >
        <TextField
          label="Weight variance allowed (%)"
          rule="G20"
          inputMode="decimal"
          className={styles.amount}
          hint="Above this, a purchase or sale is flagged and needs a note."
          {...text("weight_variance_pct")}
        />
        <div className={styles.wide}>
          <CheckField
            label="Add purchase GST to cost"
            rule="G1"
            hint="Only if the shop cannot claim input tax credit. Ask the accountant."
            {...flag("include_gst_in_cost")}
          />
        </div>
        <div className={styles.wide}>
          <CheckField
            label="Daily rates include GST"
            rule="G2"
            hint="Turn on if you quote rates with tax included; the bill backs the tax out."
            {...flag("rates_include_gst")}
          />
        </div>
        <div className={styles.wide}>
          <CheckField
            label="Counter staff may enter purchases"
            rule="G28"
            hint="They key in the supplier's bill for their own shop but never see costs. Turn off to keep purchase entry with the owner."
            {...flag("counter_can_enter_purchases")}
          />
        </div>
      </Group>

      <Group
        title="Owner approval"
        note="Above these amounts, counter staff need your PIN. You never do."
      >
        <TextField
          label="Cash-book voucher above (₹)"
          rule="FM1"
          inputMode="decimal"
          className={styles.amount}
          hint="Expenses only; bank deposits are checked against the bank statement."
          {...text("expense_approval_limit")}
        />
        <TextField
          label="Stock adjustment above (₹)"
          rule="FM2"
          inputMode="decimal"
          className={styles.amount}
          hint="Breakage, theft, weighbridge or count corrections, at average cost."
          {...text("adjustment_approval_limit")}
        />
        <div className={styles.wide}>
          <CheckField
            label="Reverse ITC on unexplained shortages"
            rule="FM2"
            hint="Count and weighbridge shortages join the ITC to reverse list. Losses, theft, damage and free samples are always listed. Ask the accountant."
            {...flag("itc_reverse_shortages")}
          />
        </div>
      </Group>

      <Group
        title="Compliance limits"
        note="Set by law and by state. Confirm the current values with the accountant."
      >
        <TextField
          label="Cash from one person in a day (₹)"
          rule="G14"
          inputMode="decimal"
          className={styles.amount}
          hint="Cash at or above this is blocked; take UPI or bank."
          {...text("cash_receipt_limit")}
        />
        <TextField
          label="E-way bill above, other state (₹)"
          rule="G13"
          inputMode="decimal"
          className={styles.amount}
          {...text("eway_threshold_interstate")}
        />
        <TextField
          label="E-way bill above, same state (₹)"
          rule="G13"
          inputMode="decimal"
          className={styles.amount}
          {...text("eway_threshold_intrastate")}
        />
        <SelectField
          label="Financial year starts in"
          rule="B16"
          hint="Document numbers restart each financial year."
          {...text("financial_year_start_month")}
        >
          {MONTHS.map((m, i) => (
            <option key={m} value={String(i + 1)}>
              {m}
            </option>
          ))}
        </SelectField>
        <div className={styles.wide}>
          <CheckField
            label="E-invoicing (IRN) is required"
            rule="G12"
            hint="Turn on only when the accountant confirms turnover has crossed the limit."
            {...flag("einvoice_enabled")}
          />
        </div>
      </Group>

      <div className={styles.saveBar}>
        <Button type="submit" variant="primary" disabled={save.isPending}>
          {save.isPending ? T.saving : T.save}
        </Button>
        <p
          role="status"
          className={
            hasErrors || serverError ? styles.formError : saved ? styles.saved : styles.note
          }
        >
          {hasErrors
            ? T.fixErrors
            : serverError
              ? serverError.message
              : saved
                ? T.saved
                : dirty
                  ? T.unsaved
                  : ""}
        </p>
      </div>
    </form>
  );
}
