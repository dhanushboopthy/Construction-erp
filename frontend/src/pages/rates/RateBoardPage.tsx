import { useState } from "react";

import { toFormError } from "@/api/errors";
import { useRateBoard, useSaveRates, type BoardRow } from "@/api/rates";
import type { MarketRatesResult, RateRowOwner } from "@/api/types";
import { Button } from "@/components/Button";
import { TextField } from "@/components/Field";
import styles from "@/components/Ledger.module.css";
import { formatMoney, trimDecimal } from "@/lib/format";

const isOwnerRow = (r: BoardRow): r is RateRowOwner => "avg_cost" in r;

function todayISO(): string {
  const d = new Date();
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
}

const num = (v: string | null | undefined) => (v ? trimDecimal(v) : "");

/** Enter the day's selling rate for every item in one sheet. The owner sees cost, margin and
 * a suggested rate (cost + margin); nothing here ever reaches staff. */
export function RateBoardPage() {
  const [date, setDate] = useState(todayISO());
  const board = useRateBoard(date);
  const save = useSaveRates();
  const [rates, setRates] = useState<Record<number, string>>({});
  const [margins, setMargins] = useState<Record<number, string>>({});
  const [result, setResult] = useState<MarketRatesResult | null>(null);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);

  const rows = board.data ?? [];
  const names = Object.fromEntries(rows.map((r) => [r.item_id, r.item_name]));

  const shownRate = (r: BoardRow) => rates[r.item_id] ?? num(r.rate_quoted);
  const shownMargin = (r: RateRowOwner) => margins[r.item_id] ?? num(r.margin_quoted);

  function fillSuggested() {
    const next: Record<number, string> = { ...rates };
    for (const r of rows)
      if (isOwnerRow(r) && r.suggested_quoted) next[r.item_id] = num(r.suggested_quoted);
    setRates(next);
  }

  async function onSave() {
    setMessage(null);
    setResult(null);
    const bad = rows.find(
      (r) =>
        (rates[r.item_id] && !/^\d+(\.\d{1,4})?$/.test(rates[r.item_id] ?? "")) ||
        (margins[r.item_id] && !/^\d+(\.\d{1,4})?$/.test(margins[r.item_id] ?? "")),
    );
    if (bad)
      return setMessage({
        ok: false,
        text: `${bad.item_name}: enter an amount like 55000 or 56250.50.`,
      });
    const changedRates = rows
      .filter(
        (r) =>
          rates[r.item_id] !== undefined &&
          rates[r.item_id] !== "" &&
          rates[r.item_id] !== num(r.rate_quoted),
      )
      .map((r) => ({ item_id: r.item_id, rate: rates[r.item_id] ?? "", unit: r.quote_unit }));
    const changedMargins = rows
      .filter(isOwnerRow)
      .filter(
        (r) =>
          margins[r.item_id] !== undefined &&
          margins[r.item_id] !== "" &&
          margins[r.item_id] !== num(r.margin_quoted),
      )
      .map((r) => ({ item_id: r.item_id, margin: margins[r.item_id] ?? "", unit: r.quote_unit }));
    if (changedRates.length === 0 && changedMargins.length === 0)
      return setMessage({ ok: false, text: "Nothing has changed yet." });
    try {
      const out = await save.mutateAsync({ date, rates: changedRates, margins: changedMargins });
      setResult(out);
      setRates({});
      setMargins({});
      setMessage({
        ok: true,
        text: `Saved ${changedRates.length} rate${changedRates.length === 1 ? "" : "s"} for ${date}.`,
      });
    } catch (err) {
      setMessage({ ok: false, text: toFormError(err).message });
    }
  }

  return (
    <div className={styles.stack}>
      <div className={styles.filters}>
        <div style={{ minWidth: 200 }}>
          <TextField
            label="Rates for"
            type="date"
            value={date}
            onChange={(e) => {
              setDate(e.target.value);
              setRates({});
              setMargins({});
              setResult(null);
            }}
          />
        </div>
        <Button onClick={fillSuggested}>Fill in suggested rates</Button>
        <Button variant="primary" onClick={() => void onSave()} disabled={save.isPending}>
          Save rates
        </Button>
      </div>
      <p className={styles.sub}>
        Rates are per ton for steel and per bag for cement, before GST. A rate stays in force until
        you enter the next one. Suggested = average cost + your margin.
      </p>
      {message ? (
        <p
          role={message.ok ? "status" : "alert"}
          className={message.ok ? styles.saved : styles.formError}
        >
          {message.text}
        </p>
      ) : null}
      {result && result.warnings.length > 0 ? (
        <div role="alert" className={styles.callout}>
          <strong>Check these before you bill:</strong>
          <ul className={styles.errorList} style={{ color: "inherit" }}>
            {result.warnings.map((w) => (
              <li key={w.item_id}>
                {names[w.item_id] ?? w.item_name}:{" "}
                {w.below_cost ? "selling below cost" : "margin is below your minimum"}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      <div className={styles.tableWrap}>
        {board.isPending ? (
          <p role="status" className={styles.empty}>
            Loading rates…
          </p>
        ) : null}
        {board.isSuccess && rows.length === 0 ? (
          <p className={styles.empty}>No items yet. Add items first, then set their rates here.</p>
        ) : null}
        {rows.length > 0 ? (
          <table className={styles.table}>
            <thead>
              <tr>
                <th scope="col">Item</th>
                <th scope="col">Per</th>
                <th scope="col" className="num">
                  Cost (₹)
                </th>
                <th scope="col" className="num">
                  Margin (₹)
                </th>
                <th scope="col" className="num">
                  Suggested (₹)
                </th>
                <th scope="col" className="num">
                  Before (₹)
                </th>
                <th scope="col" className="num">
                  Rate (₹)
                </th>
                <th scope="col">Check</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={r.item_id}>
                  <th scope="row" style={{ fontWeight: 500, color: "inherit" }}>
                    {r.item_name}
                  </th>
                  <td>{r.quote_unit}</td>
                  <td className="num">
                    {isOwnerRow(r) && r.avg_cost_quoted ? formatMoney(r.avg_cost_quoted) : "—"}
                  </td>
                  <td className="num">
                    {isOwnerRow(r) ? (
                      <input
                        aria-label={`Margin for ${r.item_name}`}
                        inputMode="decimal"
                        value={shownMargin(r)}
                        onChange={(e) => setMargins((m) => ({ ...m, [r.item_id]: e.target.value }))}
                        style={{
                          width: 90,
                          textAlign: "right",
                          padding: "4px 8px",
                          border: "1px solid var(--color-rule-strong)",
                          borderRadius: 4,
                        }}
                      />
                    ) : null}
                  </td>
                  <td className="num">
                    {isOwnerRow(r) && r.suggested_quoted ? formatMoney(r.suggested_quoted) : "—"}
                  </td>
                  <td className="num">
                    {r.previous_quoted ? formatMoney(r.previous_quoted) : "—"}
                  </td>
                  <td className="num">
                    <input
                      aria-label={`Rate for ${r.item_name}`}
                      data-rate-input={i}
                      inputMode="decimal"
                      value={shownRate(r)}
                      onChange={(e) => setRates((m) => ({ ...m, [r.item_id]: e.target.value }))}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") {
                          e.preventDefault();
                          document
                            .querySelector<HTMLInputElement>(`[data-rate-input="${i + 1}"]`)
                            ?.focus();
                        }
                      }}
                      style={{
                        width: 110,
                        textAlign: "right",
                        padding: "4px 8px",
                        border: "1px solid var(--color-rule-strong)",
                        borderRadius: 4,
                      }}
                    />
                  </td>
                  <td>
                    {isOwnerRow(r) && r.below_cost ? (
                      <span className={styles.negative}>Below cost</span>
                    ) : null}
                    {isOwnerRow(r) && !r.below_cost && r.below_min_margin ? (
                      <span style={{ color: "var(--color-warn)" }}>Thin margin</span>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : null}
      </div>
    </div>
  );
}
