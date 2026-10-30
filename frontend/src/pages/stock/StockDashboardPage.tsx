import { Link } from "react-router";

import { useStockDashboard } from "@/api/inventory";
import type { StockDashboard, StockDashboardOwner } from "@/api/types";
import styles from "@/components/Ledger.module.css";
import { Metric } from "@/components/Metric";
import { formatMoney, trimDecimal } from "@/lib/format";
import { categoryLabel } from "@/pages/items/itemLabels";
import tiles from "@/pages/reports/PnlPage.module.css";

const withValues = (d: StockDashboard | StockDashboardOwner): d is StockDashboardOwner =>
  "stock_value" in d;

/** Stock on one screen (R5): what is in stock and where, what has run out and what to order.
 * Values at cost are the owner's only (B4); everyone else sees counts and quantities. */
export function StockDashboardPage() {
  const query = useStockDashboard();
  const d = query.data;
  if (query.isPending) {
    return (
      <p role="status" className={styles.empty}>
        Loading…
      </p>
    );
  }
  if (!d) return null;
  const owner = withValues(d);

  return (
    <div className={styles.stack}>
      <dl className={tiles.tiles}>
        {owner ? (
          <Metric code="stock_value" label="Stock value" value={`₹${formatMoney(d.stock_value)}`} />
        ) : null}
        <Metric code="items_in_stock" label="Items in stock" value={d.items_in_stock} />
        <Metric
          code="out_of_stock"
          label="Out of stock"
          value={d.out_of_stock.length}
          tone={d.out_of_stock.length > 0 ? "critical" : "good"}
        />
        <Metric
          code="reorder_now"
          label="To order now"
          value={d.enough_history ? d.reorder.length : "—"}
          tone={d.reorder.length > 0 ? "critical" : undefined}
          note={d.enough_history ? undefined : "Needs a few weeks of sales first."}
        />
        {owner ? (
          <Metric
            code="dead_stock_value"
            label="Dead stock"
            value={`₹${formatMoney(d.dead_stock_value)}`}
            tone={Number(d.dead_stock_value) > 0 ? "critical" : "good"}
            note="Nothing bought or sold for 180 days."
          />
        ) : null}
      </dl>

      <div className={styles.split}>
        <div className={styles.tableWrap}>
          <table className={styles.table} aria-label="By place">
            <thead>
              <tr>
                <th scope="col">Place</th>
                <th scope="col" className="num">
                  Items in stock
                </th>
                {owner ? (
                  <th scope="col" className="num">
                    Value (₹)
                  </th>
                ) : null}
              </tr>
            </thead>
            <tbody>
              {d.places.map((p) => (
                <tr key={p.location_id}>
                  <td>
                    {p.code} {p.name}
                  </td>
                  <td className="num">{p.items}</td>
                  {owner && "value" in p ? <td className="num">{formatMoney(p.value)}</td> : null}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className={styles.tableWrap}>
          <table className={styles.table} aria-label="By category">
            <thead>
              <tr>
                <th scope="col">Category</th>
                <th scope="col" className="num">
                  Items in stock
                </th>
                {owner ? (
                  <th scope="col" className="num">
                    Value (₹)
                  </th>
                ) : null}
              </tr>
            </thead>
            <tbody>
              {d.categories.map((c) => (
                <tr key={c.category}>
                  <td>{categoryLabel(c.category)}</td>
                  <td className="num">{c.items}</td>
                  {owner && "value" in c ? <td className="num">{formatMoney(c.value)}</td> : null}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className={styles.tableWrap}>
        <table className={styles.table} aria-label="To order now">
          <thead>
            <tr>
              <th scope="col">To order now</th>
              <th scope="col" className="num">
                On hand
              </th>
              <th scope="col" className="num">
                Reorder at
              </th>
            </tr>
          </thead>
          <tbody>
            {d.reorder.map((r) => (
              <tr key={r.item_id}>
                <td>{r.name}</td>
                <td className="num">
                  {trimDecimal(r.on_hand)} {r.base_unit}
                </td>
                <td className="num">
                  {trimDecimal(r.reorder_point)} {r.base_unit}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {d.reorder.length === 0 ? (
          <p className={styles.empty}>
            {d.enough_history
              ? "Nothing is below its reorder point."
              : "Reorder points need a few weeks of sales history."}
          </p>
        ) : null}
      </div>

      <div className={styles.tableWrap}>
        <table className={styles.table} aria-label="Out of stock">
          <thead>
            <tr>
              <th scope="col">Out of stock</th>
            </tr>
          </thead>
          <tbody>
            {d.out_of_stock.map((x) => (
              <tr key={x.item_id}>
                <td>{x.name}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {d.out_of_stock.length === 0 ? <p className={styles.empty}>Every item has stock.</p> : null}
      </div>
      <p className={styles.sub}>
        Quantities per item are on <Link to="/stock">Stock levels</Link>.
      </p>
    </div>
  );
}
