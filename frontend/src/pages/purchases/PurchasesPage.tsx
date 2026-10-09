import { useState } from "react";
import { useLocation, useNavigate } from "react-router";

import { usePurchases, type PurchaseRow } from "@/api/purchasing";
import type { PurchaseOwner } from "@/api/types";
import { Button } from "@/components/Button";
import styles from "@/components/Ledger.module.css";
import { useAltKey } from "@/hooks/useKeys";
import { formatMoney, plural, trimDecimal } from "@/lib/format";

import { PurchaseReturn } from "./PurchaseReturn";

const isOwnerRow = (row: PurchaseRow): row is PurchaseOwner => "supplier_payable" in row;

export function PurchasesPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const saved = (location.state as { saved?: string } | null)?.saved;
  const query = usePurchases();
  const [openId, setOpenId] = useState<number | null>(null);
  useAltKey("n", () => void navigate("/purchases/new"));
  const rows = query.data?.items ?? [];
  const selected = rows.find((r) => r.id === openId);

  return (
    <section aria-labelledby="purchases-title" className={styles.page}>
      <div className={styles.toolbar}>
        <h1 id="purchases-title" className={styles.title}>
          Purchases
        </h1>
        <Button
          variant="primary"
          onClick={() => void navigate("/purchases/new")}
          aria-keyshortcuts="Alt+N"
        >
          New purchase
        </Button>
        <p className={styles.keys}>Alt+N new purchase</p>
      </div>
      {saved ? (
        <p role="status" className={styles.saved}>
          Saved as {saved}.
        </p>
      ) : null}
      <div className={styles.split}>
        <div className={styles.tableWrap}>
          {query.isPending ? (
            <p role="status" className={styles.empty}>
              Loading purchases…
            </p>
          ) : null}
          {query.isError ? (
            <p className={styles.formError}>Purchases could not be loaded.</p>
          ) : null}
          {query.isSuccess && rows.length === 0 ? (
            <p className={styles.empty}>
              No purchases yet. Press Alt+N to enter the first supplier bill.
            </p>
          ) : null}
          {rows.length > 0 ? (
            <table className={styles.table}>
              <thead>
                <tr>
                  <th scope="col">Number</th>
                  <th scope="col">Date</th>
                  <th scope="col">Supplier</th>
                  <th scope="col">Bill no.</th>
                  <th scope="col">At</th>
                  <th scope="col">Goes to</th>
                  {rows.some(isOwnerRow) ? (
                    <th scope="col" className="num">
                      We owe (₹)
                    </th>
                  ) : null}
                </tr>
              </thead>
              <tbody>
                {rows.map((p) => (
                  <tr key={p.id} className={openId === p.id ? styles.selected : ""}>
                    <td>
                      <button
                        type="button"
                        className={styles.rowButton}
                        onClick={() => setOpenId(p.id)}
                        aria-current={openId === p.id ? "true" : undefined}
                      >
                        {p.number}
                      </button>
                    </td>
                    <td>{p.bill_date}</td>
                    <td>{p.supplier_name}</td>
                    <td>{p.bill_no}</td>
                    <td>{p.location_code}</td>
                    <td>{p.mode === "stock" ? "Stock" : "Customer's site"}</td>
                    {isOwnerRow(p) ? (
                      <td className="num">{formatMoney(p.supplier_payable)}</td>
                    ) : null}
                  </tr>
                ))}
              </tbody>
            </table>
          ) : null}
          {query.isSuccess ? (
            <p className={styles.results}>{plural(rows.length, "purchase")}</p>
          ) : null}
        </div>
        {selected ? (
          <aside
            className={styles.panel}
            aria-labelledby="purchase-detail"
            onKeyDown={(e) => e.key === "Escape" && setOpenId(null)}
          >
            <div className={styles.panelHead}>
              <h2 id="purchase-detail">{selected.number}</h2>
              <Button variant="quiet" onClick={() => setOpenId(null)}>
                Close
              </Button>
            </div>
            <p className={styles.sub}>
              {selected.supplier_name} · bill {selected.bill_no} · {selected.bill_date}
              {selected.due_date ? ` · pay by ${selected.due_date}` : ""}
            </p>
            {selected.lines.map((l) => (
              <div key={l.id} className={styles.stack}>
                <strong>{l.item_name}</strong>
                <span className={styles.kv}>
                  <span>Billed</span>
                  <span>
                    {trimDecimal(l.quantity)} {l.unit}
                  </span>
                </span>
                <span className={styles.kv}>
                  <span>Received</span>
                  <span>
                    {trimDecimal(l.received_qty)} {l.base_unit}
                  </span>
                </span>
                {"unit_cost" in l ? (
                  <>
                    <span className={styles.kv}>
                      <span>Goods</span>
                      <span>{formatMoney(l.goods_value)}</span>
                    </span>
                    <span className={styles.kv}>
                      <span>Charges</span>
                      <span>{formatMoney(l.charges_total)}</span>
                    </span>
                    <span className={styles.kv}>
                      <strong>Landed cost per {l.base_unit}</strong>
                      <strong>₹{trimDecimal(l.unit_cost)}</strong>
                    </span>
                  </>
                ) : null}
              </div>
            ))}
            {isOwnerRow(selected) ? (
              <span className={`${styles.kv} ${styles.kvStrong}`}>
                <span>We owe the supplier</span>
                <span>₹{formatMoney(selected.supplier_payable)}</span>
              </span>
            ) : null}
            {isOwnerRow(selected) ? <PurchaseReturn key={selected.id} purchase={selected} /> : null}
          </aside>
        ) : null}
      </div>
    </section>
  );
}
