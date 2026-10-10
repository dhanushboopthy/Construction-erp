import { useState, type FormEvent } from "react";

import { toFormError } from "@/api/errors";
import { useCreateWriteoff, useReceivables, useWriteoffs } from "@/api/receivables";
import type { ReceivablesOwner } from "@/api/types";
import { useAuth } from "@/auth/AuthContext";
import { Button } from "@/components/Button";
import { SelectField, TextField } from "@/components/Field";
import styles from "@/components/Ledger.module.css";
import { Metric } from "@/components/Metric";
import { useShops } from "@/hooks/useShops";
import { formatMoney, isAmount } from "@/lib/format";

import tiles from "./PnlPage.module.css";

const rupees = (value: string) => `₹${formatMoney(value)}`;

const BUCKETS = [
  ["current", "Not yet due"],
  ["days_1_15", "1 to 15 days late"],
  ["days_16_30", "16 to 30 days late"],
  ["days_31_60", "31 to 60 days late"],
  ["over_60", "Over 60 days late"],
] as const;

/** What customers owe, aged from each bill's due date (FM5), with the doubtful-debt provision
 * and the bad-debt write-off form for the owner. */
export function ReceivablesPage() {
  const { user } = useAuth();
  const owner = user?.role === "owner";
  const report = useReceivables();
  const written = useWriteoffs();
  const create = useCreateWriteoff();
  const { shops } = useShops();
  const [partyId, setPartyId] = useState("");
  const [amount, setAmount] = useState("");
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const r = report.data;
  const provision = r && "provision" in r ? (r as ReceivablesOwner) : null;
  const shop = shops[0];

  async function writeOff(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setDone(null);
    if (!partyId || !shop) return setError("Choose the customer.");
    if (!isAmount(amount) || Number(amount) <= 0) return setError("Enter the amount to write off.");
    if (reason.trim().length < 3) return setError("Give a reason, so the books say why.");
    try {
      const saved = await create.mutateAsync({
        location_id: shop.id,
        party_id: Number(partyId),
        amount,
        reason: reason.trim(),
      });
      setDone(`Written off: ${saved.number}, ${rupees(saved.amount)} from ${saved.party_name}.`);
      setAmount("");
      setReason("");
    } catch (err) {
      setError(toFormError(err).message);
    }
  }

  return (
    <div className={styles.stack}>
      {report.isError ? (
        <p role="alert" className={styles.formError}>
          The receivables could not be loaded.
        </p>
      ) : null}
      {r ? (
        <>
          <dl className={tiles.tiles}>
            <Metric
              code="overdue_receivables"
              label="Overdue receivables"
              value={rupees(r.overdue)}
              tone={Number(r.overdue) > 0 ? "critical" : "good"}
              note={`Customers owe ${rupees(r.total)} in all${Number(r.advances) > 0 ? `; ${rupees(r.advances)} is paid in advance` : ""}.`}
            />
            {provision ? (
              <Metric
                code="provision_doubtful"
                label="Provision for doubtful debts"
                value={rupees(provision.provision)}
                note="To set aside for bills that may never be paid. A report, not booked."
              />
            ) : null}
          </dl>

          <div className={styles.tableWrap}>
            <table className={styles.table} aria-label="Overdue by due date">
              <thead>
                <tr>
                  <th scope="col">How late</th>
                  <th scope="col" className="num">
                    Amount
                  </th>
                  {provision ? (
                    <th scope="col" className="num">
                      Provision
                    </th>
                  ) : null}
                </tr>
              </thead>
              <tbody>
                {BUCKETS.map(([key, label]) => (
                  <tr key={key}>
                    <th scope="row">{label}</th>
                    <td className="num">{rupees(r.buckets[key])}</td>
                    {provision ? <td className="num">{provision.provision_pct[key]}%</td> : null}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className={styles.tableWrap}>
            <table className={styles.table} aria-label="Customers and what they owe">
              <thead>
                <tr>
                  <th scope="col">Customer</th>
                  <th scope="col" className="num">
                    Owes
                  </th>
                  <th scope="col" className="num">
                    Overdue
                  </th>
                  <th scope="col" className="num">
                    Days late
                  </th>
                  <th scope="col" className="num">
                    Credit used
                  </th>
                  <th scope="col" className="num">
                    Days to pay
                  </th>
                  <th scope="col">Last paid</th>
                </tr>
              </thead>
              <tbody>
                {r.rows.map((x) => (
                  <tr key={x.party_id}>
                    <th scope="row">{x.party_name}</th>
                    <td className="num">{rupees(x.balance)}</td>
                    <td className="num">{rupees(x.overdue)}</td>
                    <td className="num">{x.days_late ?? "—"}</td>
                    <td className="num">
                      {x.utilisation_pct == null ? "—" : `${x.utilisation_pct}%`}
                    </td>
                    <td className="num">{x.dso_days ?? "—"}</td>
                    <td>{x.last_payment_date ?? "—"}</td>
                  </tr>
                ))}
                {r.rows.length === 0 ? (
                  <tr>
                    <td colSpan={7} className={styles.empty}>
                      No customer owes anything.
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
          <p className={styles.note}>
            Days late count from the due date, not the bill date. Days to pay is the average owed
            over the credit sales of the last 90 days.
          </p>
        </>
      ) : null}

      {owner && r ? (
        <form
          className={styles.panel}
          onSubmit={(e) => void writeOff(e)}
          aria-label="Write off a bad debt"
        >
          <h2 style={{ margin: 0 }}>Write off a bad debt</h2>
          <p className={styles.note}>
            Use this only when you have given up on the money. It clears the oldest bills first, has
            no GST effect and comes off this month&apos;s profit. It cannot be undone; if the
            customer pays later, record the payment as usual.
          </p>
          <SelectField
            label="Customer"
            value={partyId}
            onChange={(e) => setPartyId(e.target.value)}
          >
            <option value="">Choose…</option>
            {r.rows
              .filter((x) => Number(x.balance) > 0)
              .map((x) => (
                <option key={x.party_id} value={x.party_id}>
                  {x.party_name} owes {rupees(x.balance)}
                </option>
              ))}
          </SelectField>
          <TextField
            label="Amount to write off (₹)"
            inputMode="decimal"
            className={styles.amount}
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
          />
          <TextField label="Reason" value={reason} onChange={(e) => setReason(e.target.value)} />
          {error ? (
            <p role="alert" className={styles.formError}>
              {error}
            </p>
          ) : null}
          {done ? <p role="status">{done}</p> : null}
          <div className={styles.inline}>
            <Button type="submit" disabled={create.isPending}>
              Write off
            </Button>
          </div>
        </form>
      ) : null}

      {written.data && written.data.length > 0 ? (
        <div className={styles.tableWrap}>
          <table className={styles.table} aria-label="Bad debts written off">
            <thead>
              <tr>
                <th scope="col">Number</th>
                <th scope="col">Date</th>
                <th scope="col">Customer</th>
                <th scope="col" className="num">
                  Written off
                </th>
                <th scope="col">Reason</th>
              </tr>
            </thead>
            <tbody>
              {written.data.map((w) => (
                <tr key={w.id}>
                  <th scope="row">{w.number}</th>
                  <td>{w.writeoff_date}</td>
                  <td>{w.party_name}</td>
                  <td className="num">{rupees(w.amount)}</td>
                  <td>{w.reason}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </div>
  );
}
