import { useState } from "react";

import { useRateOverrides } from "@/api/finance";
import { useToday } from "@/api/reports";
import { SelectField, TextField } from "@/components/Field";
import styles from "@/components/Ledger.module.css";
import { Metric } from "@/components/Metric";
import { useShops } from "@/hooks/useShops";
import { formatMoney, trimDecimal } from "@/lib/format";

import tiles from "./PnlPage.module.css";

function rupees(value: string | null | undefined) {
  if (value == null) return "—";
  const n = Number(value);
  return `${n < 0 ? "−" : ""}₹${formatMoney(String(Math.abs(n)))}`;
}

/** Prices set by hand (FM3, owner only): who typed a price instead of using the rate board,
 * why, and what it cost against the rate the system would have charged. */
export function OverridesPage() {
  const asOf = useToday().data?.as_of ?? "";
  const [picked, setPicked] = useState<string | null>(null);
  const period = picked ?? asOf.slice(0, 7);
  const { shops, single } = useShops();
  const [shopId, setShopId] = useState("");
  const report = useRateOverrides(period, single ? "" : shopId);
  const r = report.data;

  return (
    <div className={styles.stack}>
      <div className={styles.filters}>
        <TextField
          label="Month"
          type="month"
          value={period}
          max={asOf.slice(0, 7) || undefined}
          onChange={(e) => setPicked(e.target.value)}
        />
        {single ? null : (
          <SelectField label="Shop" value={shopId} onChange={(e) => setShopId(e.target.value)}>
            <option value="">Whole business</option>
            {shops.map((s) => (
              <option key={s.id} value={s.id}>
                {s.code} {s.name}
              </option>
            ))}
          </SelectField>
        )}
      </div>

      {report.isError ? (
        <p role="alert" className={styles.formError}>
          The price overrides could not be loaded.
        </p>
      ) : null}

      {r ? (
        <>
          <dl className={tiles.tiles}>
            <Metric
              code="discount_leakage"
              label="Discount leakage"
              value={rupees(r.leakage)}
              tone={Number(r.leakage) > 0 ? "critical" : undefined}
              note={`Price cuts ${rupees(r.cut)} + bill discounts ${rupees(r.discounts)}, excluding GST.`}
            />
            <Metric
              code="price_realisation_pct"
              label="Price realisation"
              value={r.realisation_pct == null ? "—" : `${r.realisation_pct}%`}
              note={
                r.realisation_pct == null
                  ? "Not enough data yet: no hand-priced bills this month."
                  : undefined
              }
            />
          </dl>
          {r.unpriced > 0 ? (
            <p className={styles.callout}>
              {r.unpriced} hand-priced line{r.unpriced === 1 ? "" : "s"} had no rate on the board to
              compare with, so their effect is not counted.
            </p>
          ) : null}
          {Number(r.raised) > 0 ? (
            <p className={styles.note}>
              Prices charged above the board rate add back {rupees(r.raised)}; net effect{" "}
              {rupees(r.net)}.
            </p>
          ) : null}

          <h2 style={{ margin: 0 }}>By person</h2>
          <div className={styles.tableWrap}>
            <table className={styles.table} aria-label="Price overrides by person">
              <thead>
                <tr>
                  <th scope="col">Person</th>
                  <th scope="col" className="num">
                    Hand-priced lines
                  </th>
                  <th scope="col" className="num">
                    Price cuts
                  </th>
                  <th scope="col" className="num">
                    Bill discounts
                  </th>
                </tr>
              </thead>
              <tbody>
                {r.by_user.map((u) => (
                  <tr key={u.user_id ?? "none"}>
                    <th scope="row">{u.user_name ?? "Unknown"}</th>
                    <td className="num">{u.lines}</td>
                    <td className="num">{rupees(u.cut)}</td>
                    <td className="num">{rupees(u.discounts)}</td>
                  </tr>
                ))}
                {r.by_user.length === 0 ? (
                  <tr>
                    <td colSpan={4} className={styles.empty}>
                      No hand-set prices or discounts this month.
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>

          {r.rows.length > 0 ? (
            <>
              <h2 style={{ margin: 0 }}>Every hand-priced line</h2>
              <div className={styles.tableWrap}>
                <table className={styles.table} aria-label="Hand-priced lines">
                  <thead>
                    <tr>
                      <th scope="col">Bill</th>
                      <th scope="col">Date</th>
                      <th scope="col">Item</th>
                      <th scope="col">By</th>
                      <th scope="col" className="num">
                        Quantity
                      </th>
                      <th scope="col" className="num">
                        Board rate
                      </th>
                      <th scope="col" className="num">
                        Billed rate
                      </th>
                      <th scope="col" className="num">
                        Given away
                      </th>
                      <th scope="col">Reason</th>
                    </tr>
                  </thead>
                  <tbody>
                    {r.rows.map((x) => (
                      <tr key={`${x.invoice_id}-${x.item_name}-${x.billed_rate}-${x.base_qty}`}>
                        <th scope="row">{x.invoice_number}</th>
                        <td>{x.invoice_date}</td>
                        <td>{x.item_name}</td>
                        <td>{x.user_name ?? "—"}</td>
                        <td className="num">
                          {trimDecimal(x.base_qty)} {x.base_unit}
                        </td>
                        <td className="num">
                          {x.list_rate ? `₹${trimDecimal(x.list_rate)}` : "—"}
                        </td>
                        <td className="num">₹{trimDecimal(x.billed_rate)}</td>
                        <td className="num">{rupees(x.effect)}</td>
                        <td>{x.reason}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          ) : null}
        </>
      ) : null}
    </div>
  );
}
