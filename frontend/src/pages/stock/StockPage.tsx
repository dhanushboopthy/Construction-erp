import { useState } from "react";

import { useStock, type StockRow } from "@/api/ledger";
import { useLocations } from "@/api/setup";
import type { StockItemOwner } from "@/api/types";
import { useAuth } from "@/auth/AuthContext";
import { SelectField, TextField } from "@/components/Field";
import styles from "@/components/Ledger.module.css";
import { formatMoney, plural, trimDecimal } from "@/lib/format";

const isOwnerRow = (row: StockRow): row is StockItemOwner => "avg_cost" in row;

/** Stock per item and place, rebuilt from the stock ledger. Cost and value are the owner's. */
export function StockPage() {
  const { user } = useAuth();
  const [q, setQ] = useState("");
  const [locationId, setLocationId] = useState("");
  const locations = useLocations();
  const stock = useStock(q, locationId);
  const rows = stock.data ?? [];
  const shown = (locations.data ?? []).filter((l) => !locationId || String(l.id) === locationId);
  const owner = user?.role === "owner";
  const totalValue = rows.reduce(
    (sum, r) => (isOwnerRow(r) ? sum + Math.round(Number(r.value) * 100) : sum),
    0,
  );

  return (
    <section aria-labelledby="stock-title" className={styles.page}>
      <div className={styles.toolbar}>
        <h1 id="stock-title" className={styles.title}>
          Stock
        </h1>
      </div>
      <div className={styles.filters}>
        <div className={styles.search}>
          <TextField
            label="Search"
            type="search"
            placeholder="Item, brand or size"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
        </div>
        <SelectField
          label="Place"
          value={locationId}
          onChange={(e) => setLocationId(e.target.value)}
        >
          <option value="">All places</option>
          {(locations.data ?? []).map((l) => (
            <option key={l.id} value={l.id}>
              {l.code} {l.name}
            </option>
          ))}
        </SelectField>
      </div>
      <div className={styles.tableWrap}>
        {stock.isPending ? (
          <p role="status" className={styles.empty}>
            Loading stock…
          </p>
        ) : null}
        {stock.isError ? <p className={styles.formError}>Stock could not be loaded.</p> : null}
        {stock.isSuccess && rows.length === 0 ? (
          <p className={styles.empty}>
            {q || locationId
              ? "Nothing matches. Clear the search to see all stock."
              : owner
                ? "No stock yet. Enter opening stock under Settings, then purchases will add to it."
                : "No stock yet. Ask the owner to enter opening stock."}
          </p>
        ) : null}
        {rows.length > 0 ? (
          <table className={styles.table}>
            <thead>
              <tr>
                <th scope="col">Item</th>
                <th scope="col">Unit</th>
                {shown.map((l) => (
                  <th key={l.id} scope="col" className="num">
                    {l.code}
                  </th>
                ))}
                <th scope="col" className="num">
                  Total
                </th>
                {owner ? (
                  <>
                    <th scope="col" className="num">
                      Avg cost (₹)
                    </th>
                    <th scope="col" className="num">
                      Value (₹)
                    </th>
                  </>
                ) : null}
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.item_id}>
                  <th scope="row" style={{ fontWeight: 500, color: "inherit" }}>
                    {r.name}
                  </th>
                  <td>{r.base_unit}</td>
                  {shown.map((l) => (
                    <td key={l.id} className="num">
                      {trimDecimal(
                        r.locations.find((x) => x.location_id === l.id)?.quantity ?? "0",
                      )}
                    </td>
                  ))}
                  <td className="num">
                    <strong>{trimDecimal(r.quantity)}</strong>
                  </td>
                  {owner && isOwnerRow(r) ? (
                    <>
                      <td className="num">{trimDecimal(r.avg_cost)}</td>
                      <td className="num">{formatMoney(r.value)}</td>
                    </>
                  ) : null}
                </tr>
              ))}
            </tbody>
          </table>
        ) : null}
        {stock.isSuccess ? <p className={styles.results}>{plural(rows.length, "item")}</p> : null}
      </div>
      {owner && rows.length > 0 ? (
        <div className={styles.totalBand}>
          <span>Stock value at average cost</span>
          <strong>₹{formatMoney((totalValue / 100).toFixed(2))}</strong>
        </div>
      ) : null}
    </section>
  );
}
