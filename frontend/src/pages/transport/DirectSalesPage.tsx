import { useDropShipReport } from "@/api/transport";
import { useAuth } from "@/auth/AuthContext";
import styles from "@/components/Ledger.module.css";
import { formatMoney, plural, trimDecimal } from "@/lib/format";

/** Sales delivered straight from the supplier: what they earned after the purchase and freight. */
export function DirectSalesPage() {
  const { user } = useAuth();
  const report = useDropShipReport();
  if (user?.role !== "owner")
    return <p className={styles.empty}>Profit on direct sales is for the owner.</p>;
  const rows = report.data?.rows ?? [];
  return (
    <div className={styles.stack}>
      {report.isSuccess && rows.length === 0 ? (
        <p className={styles.empty}>
          No direct sales yet. Choose &quot;Supplier direct&quot; on a bill line to make one.
        </p>
      ) : null}
      {report.data && report.data.unlinked > 0 ? (
        <p role="status" className={styles.callout}>
          {plural(report.data.unlinked, "direct sale")} not linked to a supplier purchase yet; their
          profit is unknown. Open the bill under Sales bills to link it.
        </p>
      ) : null}
      {rows.length > 0 ? (
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th scope="col">Bill</th>
                <th scope="col">Customer</th>
                <th scope="col">Item</th>
                <th scope="col">Supplier purchase</th>
                <th scope="col" className="num">
                  Sale (₹)
                </th>
                <th scope="col" className="num">
                  Goods cost (₹)
                </th>
                <th scope="col" className="num">
                  Freight (₹)
                </th>
                <th scope="col" className="num">
                  Profit (₹)
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.sales_line_id}>
                  <td>{r.invoice_number}</td>
                  <td>{r.customer}</td>
                  <td>
                    {r.item_name} · {trimDecimal(r.base_qty)} {r.base_unit}
                  </td>
                  <td>{r.purchase_number ?? "Not linked"}</td>
                  <td className="num">{formatMoney(r.taxable)}</td>
                  <td className="num">{r.goods_cost ? formatMoney(r.goods_cost) : "—"}</td>
                  <td className="num">{formatMoney(r.freight)}</td>
                  <td className="num">{r.profit ? formatMoney(r.profit) : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
      {report.data ? (
        <p className={styles.results}>
          Profit on linked direct sales: ₹{formatMoney(report.data.profit_total)}
        </p>
      ) : null}
    </div>
  );
}
