import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router";

import { usePendingEway } from "@/api/compliance";
import { toFormError } from "@/api/errors";
import { openFile } from "@/api/client";
import { useInvoice, useInvoices, type InvoiceFull } from "@/api/sales";
import type { InvoiceOwner } from "@/api/types";
import { useAuth } from "@/auth/AuthContext";
import { Button } from "@/components/Button";
import { TextField } from "@/components/Field";
import styles from "@/components/Ledger.module.css";
import { useAltKey } from "@/hooks/useKeys";
import { formatMoney, plural, trimDecimal } from "@/lib/format";

import { DirectLink } from "./DirectLink";
import { EwayPanel } from "./EwayPanel";
import { InvoiceReturn } from "./InvoiceReturn";

const isOwnerInvoice = (i: InvoiceFull): i is InvoiceOwner => "profit" in i;

export function SalesPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const openId = params.get("open") ? Number(params.get("open")) : null;
  const [q, setQ] = useState("");
  const list = useInvoices(q);
  const detail = useInvoice(openId);
  const pending = usePendingEway();
  const [pdfError, setPdfError] = useState<string | null>(null);
  const canBill = user?.role === "owner" || user?.role === "counter";
  useAltKey("n", () => canBill && void navigate("/sales/new"));
  const rows = list.data?.items ?? [];

  async function print(id: number, copy: string) {
    setPdfError(null);
    try {
      await openFile(`/invoices/${id}/pdf?copy=${copy}`);
    } catch (err) {
      setPdfError(toFormError(err).message);
    }
  }

  const inv = detail.data;
  return (
    <section aria-labelledby="sales-title" className={styles.page}>
      <div className={styles.toolbar}>
        <h1 id="sales-title" className={styles.title}>
          Sales bills
        </h1>
        {canBill ? (
          <Button
            variant="primary"
            onClick={() => void navigate("/sales/new")}
            aria-keyshortcuts="Alt+N"
          >
            New bill
          </Button>
        ) : null}
        <p className={styles.keys}>Alt+N new bill</p>
      </div>
      {canBill && pending.data && pending.data.length > 0 ? (
        <p role="status" className={styles.callout}>
          {plural(pending.data.length, "delivered bill")} still without an e-way bill:{" "}
          {pending.data.slice(0, 5).map((p, i) => (
            <span key={p.invoice_id}>
              {i > 0 ? ", " : ""}
              <button
                type="button"
                className={styles.rowButton}
                onClick={() => setParams({ open: String(p.invoice_id) })}
              >
                {p.number}
              </button>
            </span>
          ))}
          {pending.data.length > 5 ? " and more" : ""}
        </p>
      ) : null}
      <div className={styles.filters}>
        <div className={styles.search}>
          <TextField
            label="Search"
            type="search"
            placeholder="Bill number or customer"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
        </div>
      </div>
      <div className={styles.split}>
        <div className={styles.tableWrap}>
          {list.isPending ? (
            <p role="status" className={styles.empty}>
              Loading bills…
            </p>
          ) : null}
          {list.isSuccess && rows.length === 0 ? (
            <p className={styles.empty}>
              {q
                ? "No bills match."
                : canBill
                  ? "No bills yet. Press Alt+N to make the first one."
                  : "No bills yet."}
            </p>
          ) : null}
          {rows.length > 0 ? (
            <table className={styles.table}>
              <thead>
                <tr>
                  <th scope="col">Number</th>
                  <th scope="col">Date</th>
                  <th scope="col">Customer</th>
                  <th scope="col">Type</th>
                  <th scope="col" className="num">
                    Total (₹)
                  </th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.id} className={openId === r.id ? styles.selected : ""}>
                    <td>
                      <button
                        type="button"
                        className={styles.rowButton}
                        aria-current={openId === r.id ? "true" : undefined}
                        onClick={() => setParams({ open: String(r.id) })}
                      >
                        {r.number}
                      </button>
                    </td>
                    <td>{r.invoice_date}</td>
                    <td>{r.party_name}</td>
                    <td>{r.supply_type}</td>
                    <td className="num">{formatMoney(r.grand_total)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : null}
          {list.isSuccess ? (
            <p className={styles.results}>{plural(list.data.total, "bill")}</p>
          ) : null}
        </div>
        {inv ? (
          <aside
            className={styles.panel}
            aria-labelledby="inv-title"
            onKeyDown={(e) => e.key === "Escape" && setParams({})}
          >
            <div className={styles.panelHead}>
              <h2 id="inv-title">{inv.number}</h2>
              <Button variant="quiet" onClick={() => setParams({})}>
                Close
              </Button>
            </div>
            <p className={styles.sub}>
              {inv.bill_to_name} · {inv.invoice_date} · {inv.supply_type}
              {inv.ship_to_name
                ? ` · deliver to ${inv.ship_to_name}`
                : " · collected from the shop"}
            </p>
            <div className={styles.actions}>
              <Button variant="primary" onClick={() => void print(inv.id, "original")}>
                Print A4 bill
              </Button>
              <Button onClick={() => void print(inv.id, "duplicate")}>Duplicate copy</Button>
            </div>
            {pdfError ? (
              <p role="alert" className={styles.formError}>
                {pdfError}
              </p>
            ) : null}
            {inv.lines.map((l) => (
              <div key={l.id} className={styles.stack}>
                <strong>{l.description}</strong>
                <span className={styles.kv}>
                  <span>
                    {trimDecimal(l.quantity)} {l.unit} at ₹{trimDecimal(l.rate)}/{l.base_unit}
                    {Number(l.returned_qty) > 0
                      ? ` · ${trimDecimal(l.returned_qty)} ${l.base_unit} returned`
                      : ""}
                  </span>
                  <span>{formatMoney(l.taxable)}</span>
                </span>
                {"cost_per_unit" in l ? (
                  <span className={styles.kv}>
                    <span>
                      Profit on this line
                      {l.drop_ship_purchase ? ` · supplied by ${l.drop_ship_purchase}` : ""}
                    </span>
                    <span>{formatMoney(l.profit)}</span>
                  </span>
                ) : null}
                {"cost_per_unit" in l &&
                l.fulfilment_source === "direct" &&
                !l.drop_ship_purchase ? (
                  <DirectLink lineId={l.id} itemId={l.item_id} />
                ) : null}
              </div>
            ))}
            <span className={styles.kv}>
              <span>Taxable</span>
              <span>{formatMoney(inv.taxable_value)}</span>
            </span>
            <span className={styles.kv}>
              <span>{inv.supply_kind === "intra_state" ? "CGST + SGST" : "IGST"}</span>
              <span>
                {formatMoney(String(Number(inv.cgst) + Number(inv.sgst) + Number(inv.igst)))}
              </span>
            </span>
            <div className={styles.billTotal}>
              <span>Bill total</span>
              <strong>₹{formatMoney(inv.grand_total)}</strong>
            </div>
            {isOwnerInvoice(inv) ? (
              <p className={styles.sub}>
                Profit on this bill: ₹{formatMoney(inv.profit)}
                {Number(inv.freight) > 0 ? ` (after freight ₹${formatMoney(inv.freight)})` : ""}
              </p>
            ) : null}
            {canBill && inv.ship_to_name ? (
              <EwayPanel key={`e${inv.id}`} invoiceId={inv.id} owner={user?.role === "owner"} />
            ) : null}
            {canBill ? <InvoiceReturn key={inv.id} inv={inv} /> : null}
          </aside>
        ) : null}
      </div>
    </section>
  );
}
