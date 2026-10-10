import { useState, type FormEvent } from "react";

import { ApiError } from "@/api/client";
import { toFormError } from "@/api/errors";
import {
  useCashBook,
  useCreateCashEntry,
  useExpenseCategories,
  useReverseCashEntry,
} from "@/api/finance";
import { useToday } from "@/api/reports";
import type { CashEntry, CashEntryKind, PaymentMode } from "@/api/types";
import { useAuth } from "@/auth/AuthContext";
import { ApprovalPrompt } from "@/components/ApprovalPrompt";
import { Button } from "@/components/Button";
import { SelectField, TextField } from "@/components/Field";
import styles from "@/components/Ledger.module.css";
import { useShops } from "@/hooks/useShops";
import { formatMoney } from "@/lib/format";

const KIND: Record<CashEntryKind, string> = {
  expense: "Expense",
  bank_deposit: "Cash taken to the bank",
  bank_withdrawal: "Cash brought from the bank",
  owner_drawing: "Owner took cash",
  owner_capital: "Owner put in cash",
};
const STAFF_KINDS: CashEntryKind[] = ["expense", "bank_deposit"];
const OWNER_KINDS: CashEntryKind[] = [
  "expense",
  "bank_deposit",
  "bank_withdrawal",
  "owner_drawing",
  "owner_capital",
];
const MODE: Record<PaymentMode, string> = { cash: "Cash", upi: "UPI", bank: "Bank transfer" };
const CASH_ONLY: CashEntryKind[] = ["bank_deposit", "bank_withdrawal"];

function signed(value: string) {
  const n = Number(value);
  if (n === 0) return "—";
  return `${n > 0 ? "+" : "−"}₹${formatMoney(String(Math.abs(n)))}`;
}

/** The shop's cash book (FM1): expenses, cash taken to or brought from the bank, and the
 * owner's own money. The daily closing counts every cash voucher, so the drawer balances. */
export function CashBookPage() {
  const { user } = useAuth();
  const owner = user?.role === "owner";
  const canWrite = owner || user?.role === "counter";
  const { shops, single } = useShops();
  const serverToday = useToday().data?.as_of ?? "";
  const [shopId, setShopId] = useState("");
  const [day, setDay] = useState<string | null>(null);
  const on = day ?? serverToday;
  const place = shopId || (shops[0] ? String(shops[0].id) : "");
  const book = useCashBook(place, on, on);
  const heads = useExpenseCategories();
  const create = useCreateCashEntry();
  const reverse = useReverseCashEntry();

  const [kind, setKind] = useState<CashEntryKind>("expense");
  const [headId, setHeadId] = useState("");
  const [amount, setAmount] = useState("");
  const [mode, setMode] = useState<PaymentMode>("cash");
  const [paidTo, setPaidTo] = useState("");
  const [reference, setReference] = useState("");
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [needsOwner, setNeedsOwner] = useState<string | null>(null);
  const [saved, setSaved] = useState<string | null>(null);

  const cashOnly = CASH_ONLY.includes(kind);

  async function save(approvalIds: number[] = []) {
    setSaved(null);
    if (!place) return setError("Pick the shop.");
    if (kind === "expense" && !headId) return setError("Choose the expense head.");
    if (!/^\d+(\.\d{1,2})?$/.test(amount) || Number(amount) <= 0)
      return setError("Enter the amount, like 450 or 450.50.");
    setError(null);
    try {
      const made = await create.mutateAsync({
        location_id: Number(place),
        entry_date: on || null,
        kind,
        mode: cashOnly ? "cash" : mode,
        amount,
        category_id: kind === "expense" ? Number(headId) : null,
        paid_to: paidTo.trim() || null,
        reference: reference.trim() || null,
        note: note.trim() || null,
        approval_ids: approvalIds,
      });
      setNeedsOwner(null);
      setSaved(`${made.number} saved: ${KIND[made.kind]} ₹${formatMoney(made.amount)}.`);
      setAmount("");
      setPaidTo("");
      setReference("");
      setNote("");
    } catch (err) {
      if (err instanceof ApiError && err.requiresOwnerApproval) return setNeedsOwner(err.message);
      setError(toFormError(err).message);
    }
  }

  async function onReverse(entry: CashEntry) {
    const reason = window.prompt(`Why reverse ${entry.number}?`);
    if (!reason || reason.trim().length < 3) return;
    setError(null);
    try {
      await reverse.mutateAsync({ id: entry.id, reason: reason.trim() });
    } catch (err) {
      setError(toFormError(err).message);
    }
  }

  const b = book.data;
  const kinds = owner ? OWNER_KINDS : STAFF_KINDS;

  return (
    <section aria-labelledby="cash-title" className={styles.page}>
      <h1 id="cash-title" className={styles.title}>
        Cash book
      </h1>
      <div className={styles.filters}>
        {single ? null : (
          <SelectField label="Shop" value={place} onChange={(e) => setShopId(e.target.value)}>
            {shops.map((s) => (
              <option key={s.id} value={s.id}>
                {s.code} {s.name}
              </option>
            ))}
          </SelectField>
        )}
        <TextField
          label="Day"
          type="date"
          value={on}
          max={serverToday || undefined}
          onChange={(e) => setDay(e.target.value)}
        />
      </div>

      {canWrite ? (
        <form
          className={styles.stack}
          aria-label="New voucher"
          noValidate
          onSubmit={(e: FormEvent) => {
            e.preventDefault();
            void save();
          }}
        >
          <div className={styles.headerGrid}>
            <SelectField
              label="What happened"
              value={kind}
              onChange={(e) => setKind(e.target.value as CashEntryKind)}
            >
              {kinds.map((k) => (
                <option key={k} value={k}>
                  {KIND[k]}
                </option>
              ))}
            </SelectField>
            {kind === "expense" ? (
              <SelectField
                label="Expense head"
                value={headId}
                onChange={(e) => setHeadId(e.target.value)}
              >
                <option value="">Choose a head</option>
                {(heads.data ?? []).map((h) => (
                  <option key={h.id} value={h.id}>
                    {h.name}
                  </option>
                ))}
              </SelectField>
            ) : null}
            <TextField
              label="Amount (₹)"
              inputMode="decimal"
              className={styles.amount}
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
            />
            {cashOnly ? null : (
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
            )}
            <TextField
              label={kind === "expense" ? "Paid to" : "Taken by"}
              value={paidTo}
              onChange={(e) => setPaidTo(e.target.value)}
            />
            {mode !== "cash" && !cashOnly ? (
              <TextField
                label="UPI or bank reference"
                value={reference}
                onChange={(e) => setReference(e.target.value)}
              />
            ) : null}
            <TextField label="Note" value={note} onChange={(e) => setNote(e.target.value)} />
          </div>
          {needsOwner ? (
            <ApprovalPrompt
              actions={["expense"]}
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
            <Button type="submit" variant="primary" disabled={create.isPending}>
              Save voucher
            </Button>
          </div>
        </form>
      ) : null}

      {b ? (
        <div className={styles.totalBand}>
          <span>
            Into the drawer <strong className="num">₹{formatMoney(b.drawer_in)}</strong>
          </span>
          <span>
            Out of the drawer <strong className="num">₹{formatMoney(b.drawer_out)}</strong>
          </span>
          <span>
            Expenses <strong className="num">₹{formatMoney(b.expenses)}</strong>
          </span>
        </div>
      ) : null}

      <div className={styles.tableWrap}>
        <table className={styles.table} aria-label="Vouchers">
          <thead>
            <tr>
              <th scope="col">Voucher</th>
              <th scope="col">What</th>
              <th scope="col">Paid to / by</th>
              <th scope="col">Mode</th>
              <th scope="col" className="num">
                Amount
              </th>
              <th scope="col" className="num">
                Drawer
              </th>
              {owner ? <th scope="col">Action</th> : null}
            </tr>
          </thead>
          <tbody>
            {(b?.entries ?? []).map((e) => (
              <tr key={e.id} className={e.reversed_by_number ? styles.inactive : undefined}>
                <td className={styles.code}>{e.number}</td>
                <td>
                  {e.category_name ?? KIND[e.kind]}
                  {e.reverses_number ? (
                    <span className={styles.sub}> · reverses {e.reverses_number}</span>
                  ) : null}
                  {e.reversed_by_number ? (
                    <span className={styles.sub}> · reversed by {e.reversed_by_number}</span>
                  ) : null}
                </td>
                <td>
                  {e.paid_to ?? "—"}
                  {e.created_by_name ? (
                    <span className={styles.sub}> · entered by {e.created_by_name}</span>
                  ) : null}
                </td>
                <td>{MODE[e.mode]}</td>
                <td className="num">₹{formatMoney(e.amount)}</td>
                <td className="num">{signed(e.drawer_effect)}</td>
                {owner ? (
                  <td>
                    {!e.reverses_id && !e.reversed_by_number ? (
                      <Button variant="quiet" onClick={() => void onReverse(e)}>
                        Reverse
                      </Button>
                    ) : null}
                  </td>
                ) : null}
              </tr>
            ))}
          </tbody>
        </table>
        {b && b.entries.length === 0 ? (
          <p className={styles.empty}>
            No vouchers on this day. Record loading labour, tea, power bills or the cash you take to
            the bank, so the daily closing balances.
          </p>
        ) : null}
      </div>
    </section>
  );
}
