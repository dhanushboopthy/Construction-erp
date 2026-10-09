import { useState, type FormEvent } from "react";

import { toFormError } from "@/api/errors";
import { useParties } from "@/api/masters";
import { useOpenBills, usePayments, useRecordPayment } from "@/api/payments";
import { useLocations } from "@/api/setup";
import type { PaymentMode, PaymentOut } from "@/api/types";
import { useAuth } from "@/auth/AuthContext";
import { Button } from "@/components/Button";
import { SelectField, TextField } from "@/components/Field";
import styles from "@/components/Ledger.module.css";
import { formatMoney, plural } from "@/lib/format";

function todayISO(): string {
  const d = new Date();
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
}

const MODE: Record<PaymentMode, string> = { cash: "Cash", upi: "UPI", bank: "Bank transfer" };

/** Money received from customers. Tick the bills it is for, or leave them blank and the
 * oldest bill is paid first; anything extra is kept as the customer's advance. */
export function PaymentsPage() {
  const { user } = useAuth();
  const canRecord = user?.role === "owner" || user?.role === "counter";
  const parties = useParties("", "customer");
  const locations = useLocations();
  const list = usePayments();
  const record = useRecordPayment();
  const [partyId, setPartyId] = useState("");
  const [siteId, setSiteId] = useState("");
  const [locationId, setLocationId] = useState(
    user?.locations[0] ? String(user.locations[0].id) : "",
  );
  const [amount, setAmount] = useState("");
  const [mode, setMode] = useState<PaymentMode>("upi");
  const [reference, setReference] = useState("");
  const [date, setDate] = useState(todayISO());
  const [picked, setPicked] = useState<Record<string, string>>({});
  const [key, setKey] = useState(() => crypto.randomUUID());
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<PaymentOut | null>(null);

  const bills = useOpenBills(partyId ? Number(partyId) : null, "receivable");
  const customers = (parties.data?.items ?? []).filter(
    (p) => p.is_active && p.name !== "Walk-in customer",
  );
  const party = customers.find((p) => String(p.id) === partyId);
  const places = (locations.data ?? []).filter(
    (l) => user?.role === "owner" || user?.locations.some((x) => x.id === l.id),
  );

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setDone(null);
    if (!partyId) return setError("Pick the customer.");
    if (!locationId) return setError("Pick the shop that took the money.");
    if (!/^\d+(\.\d{1,2})?$/.test(amount) || Number(amount) <= 0)
      return setError("Enter the amount received, like 5000 or 5000.50.");
    const allocations = Object.entries(picked)
      .filter(([, v]) => v !== "")
      .map(([bill_no, v]) => ({ bill_no, amount: v }));
    if (allocations.some((a) => !/^\d+(\.\d{1,2})?$/.test(a.amount) || Number(a.amount) <= 0))
      return setError("Each ticked bill needs an amount above 0.");
    setError(null);
    try {
      const made = await record.mutateAsync({
        key,
        body: {
          direction: "received",
          party_id: Number(partyId),
          site_id: siteId ? Number(siteId) : null,
          location_id: Number(locationId),
          amount,
          mode,
          reference: reference.trim() || null,
          payment_date: date,
          allocations,
        },
      });
      setDone(made);
      setAmount("");
      setReference("");
      setPicked({});
      setKey(crypto.randomUUID());
    } catch (err) {
      setError(toFormError(err).message);
    }
  }

  const rows = list.data ?? [];
  return (
    <section aria-labelledby="payments-title" className={styles.page}>
      <h1 id="payments-title" className={styles.title}>
        Payments
      </h1>
      {canRecord ? (
        <form
          className={styles.stack}
          onSubmit={(e) => void onSubmit(e)}
          noValidate
          aria-label="Record money received"
        >
          <div className={styles.headerGrid}>
            <SelectField
              label="Customer"
              value={partyId}
              onChange={(e) => {
                setPartyId(e.target.value);
                setSiteId("");
                setPicked({});
                setDone(null);
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
              label="For site"
              value={siteId}
              onChange={(e) => setSiteId(e.target.value)}
              hint="Blank = the customer as a whole."
            >
              <option value="">Whole customer</option>
              {(party?.sites ?? []).map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </SelectField>
            <TextField
              label="Amount received (₹)"
              inputMode="decimal"
              className={styles.amount}
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
            />
            <SelectField
              label="Paid by"
              value={mode}
              onChange={(e) => setMode(e.target.value as PaymentMode)}
            >
              {(Object.keys(MODE) as PaymentMode[]).map((m) => (
                <option key={m} value={m}>
                  {MODE[m]}
                </option>
              ))}
            </SelectField>
            <TextField
              label="Reference"
              value={reference}
              onChange={(e) => setReference(e.target.value)}
              hint="UTR or UPI reference."
            />
            <TextField
              label="Date"
              type="date"
              value={date}
              max={todayISO()}
              onChange={(e) => setDate(e.target.value)}
            />
            <SelectField
              label="Taken at"
              value={locationId}
              onChange={(e) => setLocationId(e.target.value)}
            >
              <option value="">Choose a place</option>
              {places.map((l) => (
                <option key={l.id} value={l.id}>
                  {l.code} {l.name}
                </option>
              ))}
            </SelectField>
          </div>
          {bills.data && bills.data.bills.length > 0 ? (
            <fieldset className={styles.lineBlock} style={{ margin: 0 }}>
              <legend className="visually-hidden">Bills</legend>
              <strong>Which bills is this for?</strong>
              <p className={styles.sub}>
                Tick a bill to pay it first. Leave all blank to pay the oldest bill first.
              </p>
              {bills.data.bills.map((b) => (
                <div key={b.bill_no} className={styles.chargeRow}>
                  <label className={styles.choice}>
                    <input
                      type="checkbox"
                      checked={picked[b.bill_no] !== undefined}
                      onChange={(e) =>
                        setPicked((p) =>
                          e.target.checked
                            ? { ...p, [b.bill_no]: b.remaining }
                            : Object.fromEntries(
                                Object.entries(p).filter(([k]) => k !== b.bill_no),
                              ),
                        )
                      }
                    />
                    <span>
                      {b.bill_no} · {b.bill_date}
                    </span>
                  </label>
                  <span className="num">₹{formatMoney(b.remaining)} open</span>
                  {picked[b.bill_no] !== undefined ? (
                    <TextField
                      label={`Pay on ${b.bill_no} (₹)`}
                      inputMode="decimal"
                      className={styles.amount}
                      value={picked[b.bill_no] ?? ""}
                      onChange={(e) => setPicked((p) => ({ ...p, [b.bill_no]: e.target.value }))}
                    />
                  ) : (
                    <span />
                  )}
                </div>
              ))}
              {Number(bills.data.advance) > 0 ? (
                <p className={styles.sub}>
                  This customer already has an advance of ₹{formatMoney(bills.data.advance)}.
                </p>
              ) : null}
            </fieldset>
          ) : partyId && bills.data ? (
            <p className={styles.sub}>
              No unpaid bills. Money received now will be kept as an advance.
            </p>
          ) : null}
          {error ? (
            <p role="alert" className={styles.formError}>
              {error}
            </p>
          ) : null}
          {done ? (
            <div role="status" className={styles.callout}>
              <strong>Receipt {done.number} recorded.</strong>{" "}
              {(done.applied ?? [])
                .map((a) => `₹${formatMoney(a.amount)} to ${a.bill_no}`)
                .join(", ")}
              {Number(done.advance) > 0
                ? `${(done.applied ?? []).length ? ", " : ""}₹${formatMoney(done.advance)} kept as an advance`
                : ""}
              .
            </div>
          ) : null}
          <div className={styles.actions}>
            <Button type="submit" variant="primary" disabled={record.isPending}>
              Record receipt
            </Button>
          </div>
        </form>
      ) : null}
      <div className={styles.tableWrap}>
        {list.isPending ? (
          <p role="status" className={styles.empty}>
            Loading receipts…
          </p>
        ) : null}
        {list.isSuccess && rows.length === 0 ? (
          <p className={styles.empty}>No receipts yet.</p>
        ) : null}
        {rows.length > 0 ? (
          <table className={styles.table}>
            <thead>
              <tr>
                <th scope="col">Receipt</th>
                <th scope="col">Date</th>
                <th scope="col">Party</th>
                <th scope="col">Direction</th>
                <th scope="col">Paid by</th>
                <th scope="col" className="num">
                  Amount (₹)
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.map((p) => (
                <tr key={p.id}>
                  <td>{p.number}</td>
                  <td>{p.payment_date}</td>
                  <td>{p.party_name}</td>
                  <td>{p.direction === "received" ? "Received" : "Paid out"}</td>
                  <td>{MODE[p.mode]}</td>
                  <td className="num">{formatMoney(p.amount)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : null}
        {list.isSuccess ? <p className={styles.results}>{plural(rows.length, "receipt")}</p> : null}
      </div>
    </section>
  );
}
