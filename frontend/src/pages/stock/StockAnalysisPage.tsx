import { useFifoAge, useInventoryAnalytics } from "@/api/inventory";
import styles from "@/components/Ledger.module.css";
import { Metric } from "@/components/Metric";
import { formatMoney, trimDecimal } from "@/lib/format";
import tiles from "@/pages/reports/PnlPage.module.css";

const rupees = (value: string) => `₹${formatMoney(value)}`;
const BUCKET_LABEL: Record<string, string> = {
  "0-30": "0 to 30 days",
  "31-90": "31 to 90 days",
  "91-180": "91 to 180 days",
  "180+": "Over 180 days",
};
const CLASS_NOTE = "A is the few items that make most of the sales; C the many that make little.";

/** Stock analysis for the owner (FM6): what to reorder, which items are fast, slow or not
 * moving, how old the stock is, and how old the cement is. */
export function StockAnalysisPage() {
  const report = useInventoryAnalytics();
  const cement = useFifoAge();
  const r = report.data;
  const reorder = (r?.rows ?? []).filter((x) => x.reorder_now);

  return (
    <div className={styles.stack}>
      {report.isError ? (
        <p role="alert" className={styles.formError}>
          The stock analysis could not be loaded.
        </p>
      ) : null}
      {r?.data_note ? <p className={styles.callout}>{r.data_note}</p> : null}
      {r ? (
        <>
          <dl className={tiles.tiles}>
            <Metric
              code="dead_stock_value"
              label="Stock not moving"
              value={rupees(r.dead_stock_value)}
            />
            <Metric
              code="reorder_point"
              label="Items to reorder"
              value={String(reorder.length)}
              note={
                r.enough_data
                  ? `Lead time ${r.default_lead_days} days and safety ${r.default_safety_days} days unless an item or supplier says otherwise.`
                  : "Not enough data yet."
              }
            />
          </dl>

          <h2 style={{ margin: 0 }}>Reorder now</h2>
          <div className={styles.tableWrap}>
            <table className={styles.table} aria-label="Items to reorder">
              <thead>
                <tr>
                  <th scope="col">Item</th>
                  <th scope="col" className="num">
                    On hand
                  </th>
                  <th scope="col" className="num">
                    Reorder at
                  </th>
                  <th scope="col" className="num">
                    Short by
                  </th>
                  <th scope="col" className="num">
                    Days of stock
                  </th>
                  <th scope="col" className="num">
                    Lead time
                  </th>
                </tr>
              </thead>
              <tbody>
                {reorder.map((x) => (
                  <tr key={x.item_id}>
                    <th scope="row">{x.item_name}</th>
                    <td className="num">
                      {trimDecimal(x.on_hand)} {x.base_unit}
                    </td>
                    <td className="num">{trimDecimal(x.reorder_point ?? "0")}</td>
                    <td className="num">{trimDecimal(x.short_by ?? "0")}</td>
                    <td className="num">{x.cover_days ?? "—"}</td>
                    <td className="num">{x.lead_days} days</td>
                  </tr>
                ))}
                {reorder.length === 0 ? (
                  <tr>
                    <td colSpan={6} className={styles.empty}>
                      {r.enough_data
                        ? "Nothing needs ordering this week."
                        : "Not enough data yet (needs 30 days of bills)."}
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>

          <h2 style={{ margin: 0 }}>How old the stock is</h2>
          <div className={styles.tableWrap}>
            <table className={styles.table} aria-label="Stock by age">
              <thead>
                <tr>
                  <th scope="col">Since the last sale or purchase</th>
                  <th scope="col" className="num">
                    Items
                  </th>
                  <th scope="col" className="num">
                    Stock at cost
                  </th>
                </tr>
              </thead>
              <tbody>
                {r.aging.map((a) => (
                  <tr key={a.bucket}>
                    <th scope="row">{BUCKET_LABEL[a.bucket] ?? a.bucket}</th>
                    <td className="num">{a.items}</td>
                    <td className="num">{rupees(a.value)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <h2 style={{ margin: 0 }}>Every item</h2>
          <div className={styles.tableWrap}>
            <table className={styles.table} aria-label="Stock analysis">
              <thead>
                <tr>
                  <th scope="col">Item</th>
                  <th scope="col" className="num">
                    On hand
                  </th>
                  <th scope="col" className="num">
                    At cost
                  </th>
                  <th scope="col" title={CLASS_NOTE}>
                    Sales class
                  </th>
                  <th scope="col" title="Fast, slow or non-moving, by days sold in the last 90">
                    Speed
                  </th>
                  <th scope="col">Last moved</th>
                  <th scope="col" className="num">
                    Days of stock
                  </th>
                </tr>
              </thead>
              <tbody>
                {r.rows.map((x) => (
                  <tr key={x.item_id}>
                    <th scope="row">{x.item_name}</th>
                    <td className="num">
                      {trimDecimal(x.on_hand)} {x.base_unit}
                    </td>
                    <td className="num">{rupees(x.value)}</td>
                    <td>{x.abc ?? "—"}</td>
                    <td>
                      {x.fsn === "F"
                        ? "Fast"
                        : x.fsn === "S"
                          ? "Slow"
                          : x.fsn === "N"
                            ? "Not moving"
                            : "—"}
                    </td>
                    <td>{x.last_movement ? `${x.last_movement} (${x.age_days} days)` : "—"}</td>
                    <td className="num">{x.cover_days ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className={styles.note}>
            Stock adjustments, count corrections, transfers and write-downs are not movement: only a
            purchase, a sale or a return is. {CLASS_NOTE}
          </p>
        </>
      ) : null}

      {cement.data && cement.data.items.length > 0 ? (
        <>
          <h2 style={{ margin: 0 }}>Cement by age (an estimate)</h2>
          <p className={styles.note}>{cement.data.note}</p>
          <div className={styles.tableWrap}>
            <table className={styles.table} aria-label="Cement by age">
              <thead>
                <tr>
                  <th scope="col">Item</th>
                  <th scope="col" className="num">
                    On hand
                  </th>
                  <th scope="col" className="num">
                    0 to 30 days
                  </th>
                  <th scope="col" className="num">
                    31 to 60
                  </th>
                  <th scope="col" className="num">
                    61 to 90
                  </th>
                  <th scope="col" className="num">
                    Over 90
                  </th>
                  <th scope="col" className="num">
                    Oldest
                  </th>
                </tr>
              </thead>
              <tbody>
                {cement.data.items.map((c) => (
                  <tr key={c.item_id}>
                    <th scope="row">{c.item_name}</th>
                    <td className="num">
                      {trimDecimal(c.on_hand)} {c.base_unit}
                    </td>
                    <td className="num">{trimDecimal(c.buckets["0-30"] ?? "0")}</td>
                    <td className="num">{trimDecimal(c.buckets["31-60"] ?? "0")}</td>
                    <td className="num">{trimDecimal(c.buckets["61-90"] ?? "0")}</td>
                    <td className="num">
                      {trimDecimal(c.buckets["90+"] ?? "0")}
                      {Number(c.over_90_value) > 0 ? ` (${rupees(c.over_90_value)})` : ""}
                    </td>
                    <td className="num">{c.oldest_age_days} days</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      ) : null}
    </div>
  );
}
