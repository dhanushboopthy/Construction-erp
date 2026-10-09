import { useState } from "react";

import { openFile } from "@/api/client";
import { toFormError } from "@/api/errors";
import { useCloseDay, useClosingPreview, useClosings, useReopenDay, useToday } from "@/api/reports";
import { useLocations } from "@/api/setup";
import { useAuth } from "@/auth/AuthContext";
import { Button } from "@/components/Button";
import { SelectField, TextField } from "@/components/Field";
import styles from "@/components/Ledger.module.css";
import { formatMoney, trimDecimal } from "@/lib/format";

function todayISO(): string {
  const d = new Date();
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
}

/** Count the drawer and close one shop's day. Closing locks that day's documents until the
 * owner reopens it (G17), and saves a PDF date-wise to storage. */
export function ClosingPage() {
  const { user } = useAuth();
  const owner = user?.role === "owner";
  const canClose = user?.role !== "accountant";
  const locations = useLocations();
  const shops = (locations.data ?? []).filter(
    (l) =>
      l.kind === "shop" &&
      (owner || user?.role === "accountant" || user?.locations.some((u) => u.id === l.id)),
  );
  const [shopId, setShopId] = useState("");
  const serverToday = useToday().data?.as_of;
  const [picked, setPicked] = useState<string | null>(null);
  // The shop's own calendar day (India), from the server, not this device's clock.
  const date = picked ?? serverToday ?? todayISO();
  const setDate = setPicked;
  const place = shopId || (shops[0] ? String(shops[0].id) : "");
  const preview = useClosingPreview(place, date);
  const closings = useClosings();
  const close = useCloseDay();
  const reopen = useReopenDay();
  const [counted, setCounted] = useState("");
  const [opening, setOpening] = useState("");
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);

  const p = preview.data;
  const f = p?.figures;
  const firstEver = p && Number(p.opening_cash) === 0 && !p.existing;

  async function onClose() {
    setDone(null);
    if (!/^\d+(\.\d{1,2})?$/.test(counted)) return setError("Enter the cash you counted.");
    if (opening && !/^\d+(\.\d{1,2})?$/.test(opening))
      return setError("Enter the opening cash in rupees.");
    setError(null);
    try {
      const made = await close.mutateAsync({
        location_id: Number(place),
        closing_date: date,
        counted_cash: counted,
        opening_cash: opening || null,
        note: note.trim() || null,
      });
      setDone(
        `Day closed. The drawer is ${Number(made.difference) === 0 ? "exactly right" : `${Number(made.difference) < 0 ? "short" : "over"} by ₹${formatMoney(String(Math.abs(Number(made.difference))))}`}. The PDF is saved.`,
      );
      setCounted("");
      setNote("");
    } catch (err) {
      setError(toFormError(err).message);
    }
  }

  async function onReopen(id: number) {
    const reason = window.prompt("Why is the day being reopened?");
    if (!reason || reason.trim().length < 3) return;
    setError(null);
    try {
      await reopen.mutateAsync({ id, reason: reason.trim() });
    } catch (err) {
      setError(toFormError(err).message);
    }
  }

  return (
    <div className={styles.stack}>
      <div className={styles.filters}>
        <SelectField label="Shop" value={place} onChange={(e) => setShopId(e.target.value)}>
          {shops.map((l) => (
            <option key={l.id} value={l.id}>
              {l.code} {l.name}
            </option>
          ))}
        </SelectField>
        <TextField
          label="Day"
          type="date"
          value={date}
          max={serverToday ?? todayISO()}
          onChange={(e) => setDate(e.target.value)}
        />
      </div>
      {preview.isError ? (
        <p role="alert" className={styles.formError}>
          {toFormError(preview.error).message}
        </p>
      ) : null}
      {f && p ? (
        <div className={styles.split}>
          <div className={styles.tableWrap}>
            <table className={styles.table} aria-label="The day's figures">
              <tbody>
                <tr>
                  <th scope="row">Bills</th>
                  <td className="num">
                    {f.invoices_count}
                    {f.first_invoice ? ` (${f.first_invoice} to ${f.last_invoice})` : ""}
                  </td>
                </tr>
                <tr>
                  <th scope="row">Sales total</th>
                  <td className="num">₹{formatMoney(f.sales_total)}</td>
                </tr>
                <tr>
                  <th scope="row">CGST + SGST / IGST</th>
                  <td className="num">
                    {formatMoney(String(Number(f.cgst) + Number(f.sgst)))} / {formatMoney(f.igst)}
                  </td>
                </tr>
                <tr>
                  <th scope="row">Billed on credit</th>
                  <td className="num">₹{formatMoney(f.credit_given)}</td>
                </tr>
                <tr>
                  <th scope="row">Returns ({f.returns_count})</th>
                  <td className="num">₹{formatMoney(f.returns_total)}</td>
                </tr>
                <tr>
                  <th scope="row">Received: cash / UPI / bank</th>
                  <td className="num">
                    {formatMoney(f.receipts.cash)} / {formatMoney(f.receipts.upi)} /{" "}
                    {formatMoney(f.receipts.bank)}
                  </td>
                </tr>
                <tr>
                  <th scope="row">Cash paid out</th>
                  <td className="num">₹{formatMoney(f.cash_out)}</td>
                </tr>
                {p.profit != null ? (
                  <tr>
                    <th scope="row">Profit (not on the PDF)</th>
                    <td className="num">₹{formatMoney(p.profit)}</td>
                  </tr>
                ) : null}
              </tbody>
            </table>
            {f.top_items.length > 0 ? (
              <p className={styles.sub}>
                Sold:{" "}
                {f.top_items
                  .map((i) => `${i.description} ${trimDecimal(i.quantity)} ${i.base_unit}`)
                  .join(", ")}
              </p>
            ) : null}
          </div>
          <aside className={styles.panel} aria-label="Cash drawer">
            <h2 style={{ margin: 0 }}>Cash drawer</h2>
            <span className={styles.kv}>
              <span>Opening</span>
              <span>₹{formatMoney(p.opening_cash)}</span>
            </span>
            <span className={styles.kv}>
              <strong>Should be</strong>
              <strong>₹{formatMoney(p.expected_cash)}</strong>
            </span>
            {p.locked ? (
              <>
                <p role="status" className={styles.saved}>
                  This day is closed. Counted ₹{formatMoney(p.existing?.counted_cash ?? "0")},
                  difference ₹{formatMoney(p.existing?.difference ?? "0")}.
                </p>
                {p.existing ? (
                  <Button onClick={() => void openFile(`/closings/${p.existing?.id}/pdf`)}>
                    Print closing PDF
                  </Button>
                ) : null}
              </>
            ) : canClose ? (
              <>
                {firstEver ? (
                  <TextField
                    label="Opening cash (first closing only)"
                    inputMode="decimal"
                    value={opening}
                    onChange={(e) => setOpening(e.target.value)}
                  />
                ) : null}
                <TextField
                  label="Cash counted"
                  inputMode="decimal"
                  value={counted}
                  onChange={(e) => setCounted(e.target.value)}
                />
                <TextField
                  label="Note (needed if the drawer is short or over)"
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                />
                <Button variant="primary" onClick={() => void onClose()} disabled={close.isPending}>
                  Close the day
                </Button>
              </>
            ) : (
              <p className={styles.sub}>The accountant can look at a closing but not make one.</p>
            )}
            {error ? (
              <p role="alert" className={styles.formError}>
                {error}
              </p>
            ) : null}
            {done ? (
              <p role="status" className={styles.saved}>
                {done}
              </p>
            ) : null}
          </aside>
        </div>
      ) : null}
      <h2 style={{ margin: 0 }}>Recent closings</h2>
      {closings.isSuccess && closings.data.items.length === 0 ? (
        <p className={styles.empty}>No day has been closed yet.</p>
      ) : null}
      {closings.data && closings.data.items.length > 0 ? (
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th scope="col">Day</th>
                <th scope="col">Shop</th>
                <th scope="col">Status</th>
                <th scope="col" className="num">
                  Sales (₹)
                </th>
                <th scope="col" className="num">
                  Cash difference (₹)
                </th>
                <th scope="col" />
              </tr>
            </thead>
            <tbody>
              {closings.data.items.map((c) => (
                <tr key={c.id}>
                  <td>{c.closing_date}</td>
                  <td>{c.location_code}</td>
                  <td>{c.status === "closed" ? "Closed" : "Reopened"}</td>
                  <td className="num">{formatMoney(c.sales_total)}</td>
                  <td className="num">{formatMoney(c.difference)}</td>
                  <td>
                    {c.has_pdf ? (
                      <Button
                        variant="quiet"
                        onClick={() => void openFile(`/closings/${c.id}/pdf`)}
                      >
                        Print {c.closing_date}
                      </Button>
                    ) : null}
                    {owner && c.status === "closed" ? (
                      <Button variant="quiet" onClick={() => void onReopen(c.id)}>
                        Reopen {c.closing_date}
                      </Button>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </div>
  );
}
