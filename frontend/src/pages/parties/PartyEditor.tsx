import { useEffect, useRef, useState, type FormEvent } from "react";

import { toFormError, type FormError } from "@/api/errors";
import { useCreateParty, useUpdateParty } from "@/api/masters";
import type { CustomerSegment, Party, PartyType } from "@/api/types";
import { useAuth } from "@/auth/AuthContext";
import { Button } from "@/components/Button";
import { CheckField, SelectField, TextAreaField, TextField } from "@/components/Field";
import styles from "@/components/Ledger.module.css";
import { formatMoney } from "@/lib/format";
import { GST_STATES } from "@/lib/gstStates";

import { TYPE_LABEL } from "./partyLabels";
import { SitesSection } from "./SitesSection";
import { SupplierPayment } from "./SupplierPayment";
import { StatementSection } from "./StatementSection";

const SEGMENTS: { value: CustomerSegment; label: string }[] = [
  { value: "retail", label: "Retail" },
  { value: "contractor", label: "Contractor" },
  { value: "bulk", label: "Bulk" },
];

export function PartyEditor({
  party,
  onClose,
  onDone,
}: {
  party?: Party;
  onClose: () => void;
  onDone: (party: Party) => void;
}) {
  const { user } = useAuth();
  const isOwner = user?.role === "owner";
  const canEdit = user?.role === "owner" || user?.role === "counter";
  const create = useCreateParty();
  const update = useUpdateParty();
  const [name, setName] = useState(party?.name ?? "");
  const [type, setType] = useState<PartyType>(party?.type ?? "customer");
  const [segment, setSegment] = useState<CustomerSegment | "">(party?.segment ?? "");
  const [gstin, setGstin] = useState(party?.gstin ?? "");
  const [state, setState] = useState(party?.state_code ?? "33");
  const [address, setAddress] = useState(party?.address ?? "");
  const [phone, setPhone] = useState(party?.phone ?? "");
  const [creditAllowed, setCreditAllowed] = useState(party?.credit_allowed ?? false);
  const [creditLimit, setCreditLimit] = useState(party?.credit_limit ?? "");
  const [creditDays, setCreditDays] = useState(party?.credit_days?.toString() ?? "");
  const [active, setActive] = useState(party?.is_active ?? true);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [serverError, setServerError] = useState<FormError | null>(null);
  const first = useRef<HTMLInputElement>(null);
  useEffect(() => first.current?.focus(), []);

  const titleId = `party-editor-${party?.id ?? "new"}`;
  const pending = create.isPending || update.isPending;
  const isCustomer = type !== "supplier";

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    const found: Record<string, string> = {};
    if (!name.trim()) found.name = "Enter the name as it should print on bills.";
    const g = gstin.trim().toUpperCase();
    if (g && !/^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$/.test(g)) {
      found.gstin = "A GSTIN has 15 characters, like 33ABCDE1234F1Z5.";
    } else if (g && g.slice(0, 2) !== state) {
      found.gstin = "The first two digits of the GSTIN must match the state.";
    }
    if (isOwner && creditLimit && !/^\d+(\.\d{1,2})?$/.test(creditLimit))
      found.credit_limit = "Enter an amount like 10000.";
    if (isOwner && creditDays && !/^\d{1,3}$/.test(creditDays))
      found.credit_days = "Enter whole days, 0 to 365.";
    setErrors(found);
    setServerError(null);
    if (Object.keys(found).length > 0) return;

    const base = {
      name: name.trim(),
      type,
      segment: isCustomer && segment ? segment : null,
      gstin: g || null,
      state_code: state,
      address: address.trim(),
      phone: phone.trim() || null,
    };
    const credit = {
      credit_allowed: isOwner && isCustomer ? creditAllowed : false,
      credit_limit: isOwner && isCustomer && creditLimit ? creditLimit : null,
      credit_days: isOwner && isCustomer && creditDays ? Number(creditDays) : null,
    };
    // Counter staff may not touch credit terms, so an update from them leaves them out.
    const creditChange = isOwner ? credit : {};
    try {
      const saved = party
        ? await update.mutateAsync({
            id: party.id,
            body: { ...base, ...creditChange, is_active: active },
          })
        : await create.mutateAsync({ ...base, ...credit });
      onDone(saved);
    } catch (err) {
      setServerError(toFormError(err));
    }
  }

  const fieldError = (key: string) =>
    errors[key] ?? (serverError?.field === key ? serverError.message : null);
  const known = ["name", "gstin", "credit_limit", "credit_days"];
  const general =
    serverError && !known.includes(serverError.field ?? "") ? serverError.message : null;

  return (
    <aside
      className={styles.panel}
      aria-labelledby={titleId}
      onKeyDown={(e) => e.key === "Escape" && onClose()}
    >
      <div className={styles.panelHead}>
        <h2 id={titleId}>{party ? party.name : "New party"}</h2>
        <Button variant="quiet" onClick={onClose}>
          Close
        </Button>
      </div>
      <form onSubmit={(e) => void onSubmit(e)} noValidate>
        <fieldset
          disabled={!canEdit}
          className={styles.stack}
          style={{ border: 0, padding: 0, margin: 0 }}
        >
          <TextField
            ref={first}
            label="Name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            error={fieldError("name")}
          />
          <SelectField
            label="Type"
            value={type}
            onChange={(e) => setType(e.target.value as PartyType)}
          >
            {(Object.keys(TYPE_LABEL) as PartyType[]).map((t) => (
              <option key={t} value={t}>
                {TYPE_LABEL[t]}
              </option>
            ))}
          </SelectField>
          {isCustomer ? (
            <SelectField
              label="Customer segment"
              value={segment}
              onChange={(e) => setSegment(e.target.value as CustomerSegment | "")}
              hint="Used in the monthly sales chart."
            >
              <option value="">Not set</option>
              {SEGMENTS.map((s) => (
                <option key={s.value} value={s.value}>
                  {s.label}
                </option>
              ))}
            </SelectField>
          ) : null}
          <TextField
            label="GSTIN"
            maxLength={15}
            className={styles.code}
            value={gstin}
            onChange={(e) => setGstin(e.target.value)}
            error={fieldError("gstin")}
            hint="Leave blank for a customer without GST; bills are then B2C."
          />
          <SelectField label="State" value={state} onChange={(e) => setState(e.target.value)}>
            {GST_STATES.map((s) => (
              <option key={s.code} value={s.code}>
                {s.code} {s.name}
              </option>
            ))}
          </SelectField>
          <TextAreaField
            label="Address"
            value={address}
            onChange={(e) => setAddress(e.target.value)}
          />
          <TextField
            label="Phone"
            type="tel"
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
          />
        </fieldset>

        {isCustomer && party ? (
          isOwner ? (
            <section className={styles.subsection}>
              <h3>Credit</h3>
              <CheckField
                label="Allow credit"
                rule="B8"
                checked={creditAllowed}
                onChange={(e) => setCreditAllowed(e.target.checked)}
                hint="Only approved customers buy on credit."
              />
              <TextField
                label="Credit limit (₹)"
                inputMode="decimal"
                className={styles.amount}
                value={creditLimit}
                onChange={(e) => setCreditLimit(e.target.value)}
                error={fieldError("credit_limit")}
                hint="Blank uses the shop default from Settings."
              />
              <TextField
                label="Credit days"
                inputMode="numeric"
                className={styles.amount}
                value={creditDays}
                onChange={(e) => setCreditDays(e.target.value)}
                error={fieldError("credit_days")}
                hint="Blank uses the shop default."
              />
            </section>
          ) : (
            <p className={styles.sub}>
              {party.credit_allowed
                ? `Credit allowed up to ₹${party.credit_limit ? formatMoney(party.credit_limit) : "the shop default"}.`
                : "Cash and UPI only. Ask the owner to approve credit."}
            </p>
          )
        ) : null}
        {party && canEdit ? (
          <CheckField
            label="Active"
            checked={active}
            onChange={(e) => setActive(e.target.checked)}
            hint="Inactive parties stay on old bills but cannot be picked."
          />
        ) : null}
        {general ? (
          <p role="alert" className={styles.formError}>
            {general}
          </p>
        ) : null}
        {canEdit ? (
          <div className={styles.actions}>
            <Button type="submit" variant="primary" disabled={pending}>
              {pending ? "Saving…" : party ? "Save changes" : "Create party"}
            </Button>
          </div>
        ) : null}
      </form>
      {party && party.type !== "supplier" ? <SitesSection party={party} /> : null}
      {party ? <SupplierPayment party={party} /> : null}
      {party ? <StatementSection party={party} /> : null}
    </aside>
  );
}
