import { useState } from "react";

import { useProfitability, useToday } from "@/api/reports";
import type { Cut } from "@/api/types";
import { SelectField, TextField } from "@/components/Field";
import styles from "@/components/Ledger.module.css";
import { Metric } from "@/components/Metric";
import { useShops } from "@/hooks/useShops";
import { formatMoney, trimDecimal } from "@/lib/format";

import tiles from "./PnlPage.module.css";

const CUTS: { value: Cut; label: string }[] = [
  { value: "brand", label: "Brand" },
  { value: "shop", label: "Shop" },
  { value: "user", label: "Who made the bill" },
  { value: "item", label: "Item" },
  { value: "customer", label: "Customer" },
];

const rupees = (value: string) => `₹${formatMoney(value)}`;
const maybe = (value: string | null | undefined) => (value == null ? "—" : rupees(value));

/** Profit per ton by brand, shop, user, item or customer (FM8, owner only). The rows add up to
 * the profit and loss gross profit once the stock lost is taken off. */
export function ProfitCutsPage() {
  const asOf = useToday().data?.as_of ?? "";
  const { shops, single } = useShops();
  const [picked, setPicked] = useState<string | null>(null);
  const [by, setBy] = useState<Cut>("brand");
  const [shop, setShop] = useState("");
  const period = picked ?? asOf.slice(0, 7);
  const report = useProfitability(period, by, shop);
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
        <SelectField label="Group by" value={by} onChange={(e) => setBy(e.target.value as Cut)}>
          {CUTS.map((c) => (
            <option key={c.value} value={c.value}>
              {c.label}
            </option>
          ))}
        </SelectField>
        {single ? null : (
          <SelectField label="Shop" value={shop} onChange={(e) => setShop(e.target.value)}>
            <option value="">All shops</option>
            {shops.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </SelectField>
        )}
      </div>
      {report.isError ? (
        <p role="alert" className={styles.formError}>
          The report could not be loaded.
        </p>
      ) : null}
      {r?.data_note ? <p className={styles.callout}>{r.data_note}</p> : null}
      {r && r.rows.length > 0 ? (
        <>
          <dl className={tiles.tiles}>
            <Metric
              code="profit_per_ton"
              label="Profit per ton"
              value={maybe(r.profit_per_ton)}
              note={`On ${trimDecimal(r.tons)} t sold by weight.`}
            />
            <Metric
              code="contribution_per_ton"
              label="Contribution per ton"
              value={maybe(r.contribution_per_ton)}
            />
          </dl>
          <div className={styles.tableWrap}>
            <table className={styles.table} aria-label="Profit by cut">
              <thead>
                <tr>
                  <th scope="col">{CUTS.find((c) => c.value === by)?.label}</th>
                  <th scope="col" className="num">
                    Net sales
                  </th>
                  <th scope="col" className="num">
                    Cost
                  </th>
                  <th scope="col" className="num">
                    Freight
                  </th>
                  <th scope="col" className="num">
                    Profit
                  </th>
                  <th scope="col" className="num">
                    Margin %
                  </th>
                  <th scope="col" className="num">
                    Share %
                  </th>
                  <th scope="col" className="num">
                    Tons
                  </th>
                  <th scope="col" className="num">
                    Profit a ton
                  </th>
                  <th scope="col" className="num">
                    Other units
                  </th>
                  <th scope="col" className="num">
                    Profit a unit
                  </th>
                </tr>
              </thead>
              <tbody>
                {r.rows.map((row) => (
                  <tr key={row.key}>
                    <th scope="row">{row.key}</th>
                    <td className="num">{formatMoney(row.net_sales)}</td>
                    <td className="num">{formatMoney(row.cogs)}</td>
                    <td className="num">{formatMoney(row.freight)}</td>
                    <td className="num">{formatMoney(row.gross_profit)}</td>
                    <td className="num">{row.margin_pct ?? "—"}</td>
                    <td className="num">{row.share_pct ?? "—"}</td>
                    <td className="num">{Number(row.tons) ? trimDecimal(row.tons) : ""}</td>
                    <td className="num">
                      {row.profit_per_ton ? formatMoney(row.profit_per_ton) : ""}
                    </td>
                    <td className="num">
                      {Number(row.units) ? `${trimDecimal(row.units)} ${row.unit_label ?? ""}` : ""}
                    </td>
                    <td className="num">
                      {row.profit_per_unit ? formatMoney(row.profit_per_unit) : ""}
                    </td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr>
                  <th scope="row">Rows added up</th>
                  <td className="num">{formatMoney(r.net_sales)}</td>
                  <td className="num">{formatMoney(r.cogs)}</td>
                  <td className="num">{formatMoney(r.freight)}</td>
                  <td className="num">{formatMoney(r.gross_profit_before_loss)}</td>
                  <td colSpan={6} />
                </tr>
                <tr>
                  <th scope="row">Stock lost (breakage, theft, shortages)</th>
                  <td colSpan={3} />
                  <td className="num">−{formatMoney(r.stock_lost)}</td>
                  <td colSpan={6} />
                </tr>
                <tr>
                  <th scope="row">Gross profit, as in Profit &amp; loss</th>
                  <td colSpan={3} />
                  <td className="num">
                    <strong>{formatMoney(r.gross_profit)}</strong>
                  </td>
                  <td colSpan={6} />
                </tr>
              </tfoot>
            </table>
          </div>
          <p className={styles.note}>
            Steel sold by weight is counted in tons; bags and pieces are counted apart, so a bag of
            cement never inflates the tons. A bill belongs to the user who saved it; a credit note
            reduces the bill&apos;s brand, shop and user.
          </p>
        </>
      ) : null}
      {r && r.rows.length === 0 && !r.data_note ? (
        <p className={styles.empty}>No bills in this month.</p>
      ) : null}
    </div>
  );
}
