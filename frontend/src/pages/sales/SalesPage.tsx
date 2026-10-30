import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router";

import { usePendingEway } from "@/api/compliance";
import { toFormError } from "@/api/errors";
import { openFile } from "@/api/client";
import { useInvoice, useInvoices, type InvoiceFull } from "@/api/sales";
import type { InvoiceOwner, InvoiceSummary } from "@/api/types";
import { useAuth } from "@/auth/AuthContext";
import { Attachments } from "@/components/Attachments";
import { Button } from "@/components/Button";
import { DataTable, type Column } from "@/components/DataTable";
import { PageHeader } from "@/components/PageHeader";
import { StatusPill } from "@/components/StatusPill";
import { TableToolbar } from "@/components/TableToolbar";
import styles from "@/components/Ledger.module.css";
import { useAltKey } from "@/hooks/useKeys";
import { useTableFilters } from "@/hooks/useTableFilters";
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
  const filters = useTableFilters();
  const q = filters.q;
  const list = useInvoices(q);
  const detail = useInvoice(openId);
  const pending = usePendingEway();
  const [pdfError, setPdfError] = useState<string | null>(null);
  const canBill = user?.role === "owner" || user?.role === "counter";
  useAltKey("n", () => canBill && void navigate("/sales/new"));
  // Opening a bill keeps the search and the status filter in the URL.
  const setOpen = (id: number | null) =>
    setParams((prev) => {
      const next = new URLSearchParams(prev);
      if (id === null) next.delete("open");
      else next.set("open", String(id));
      return next;
    });
  const waiting = new Set((pending.data ?? []).map((p) => p.invoice_id));
  const columns: Column<InvoiceSummary>[] = [
    { id: "number", header: "Number", cell: (r) => r.number },
    { id: "date", header: "Date", cell: (r) => r.invoice_date },
    { id: "customer", header: "Customer", cell: (r) => r.party_name },
    { id: "type", header: "Type", cell: (r) => r.supply_type },
    { id: "total", header: "Total (₹)", numeric: true, cell: (r) => formatMoney(r.grand_total) },
    {
      id: "status",
      header: "Status",
      cell: (r) =>
        waiting.has(r.id) ? (
          <StatusPill tone="warn" label="E-way bill pending" />
        ) : (
          <StatusPill tone="good" label="Posted" />
        ),
    },
  ];
  const rows = (list.data?.items ?? []).filter(
    (r) =>
      !filters.status ||
      (filters.status === "eway_pending" ? waiting.has(r.id) : !waiting.has(r.id)),
  );

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
      <PageHeader
        eyebrow="Sales"
        title="Sales bills"
        titleId="sales-title"
        subtitle="GST invoices, newest first. Alt+N new bill"
        actions={
          canBill ? (
            <Button
              variant="primary"
              onClick={() => void navigate("/sales/new")}
              aria-keyshortcuts="Alt+N"
            >
              New bill
            </Button>
          ) : null
        }
      />
      {canBill && pending.data && pending.data.length > 0 ? (
        <p role="status" className={styles.callout}>
          {plural(pending.data.length, "delivered bill")} still without an e-way bill:{" "}
          {pending.data.slice(0, 5).map((p, i) => (
            <span key={p.invoice_id}>
              {i > 0 ? ", " : ""}
              <button
                type="button"
                className={styles.rowButton}
                onClick={() => setOpen(p.invoice_id)}
              >
                {p.number}
              </button>
            </span>
          ))}
          {pending.data.length > 5 ? " and more" : ""}
        </p>
      ) : null}
      <TableToolbar
        filters={filters}
        searchPlaceholder="Bill number or customer"
        statusOptions={[
          { value: "eway_pending", label: "E-way bill pending" },
          { value: "posted", label: "Posted" },
        ]}
      />
      <div className={styles.split}>
        <DataTable
          caption="Sales bills"
          columns={columns}
          rows={rows}
          rowKey={(r) => r.id}
          selectedKey={openId}
          onOpen={(r) => setOpen(r.id)}
          loading={list.isPending}
          error={list.isError ? "Bills could not be loaded." : null}
          onRetry={() => void list.refetch()}
          empty={
            q || filters.status
              ? "No bills match."
              : canBill
                ? "No bills yet. Press Alt+N to make the first one."
                : "No bills yet."
          }
          footer={list.isSuccess ? plural(list.data.total, "bill") : undefined}
        />
        {inv ? (
          <aside
            className={styles.panel}
            aria-labelledby="inv-title"
            onKeyDown={(e) => e.key === "Escape" && setOpen(null)}
          >
            <div className={styles.panelHead}>
              <h2 id="inv-title">{inv.number}</h2>
              <Button variant="ghost" onClick={() => setOpen(null)}>
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
                    {l.weight_flagged
                      ? ` · slip ${trimDecimal(l.slip_weight ?? "0")} ${l.base_unit}, differs ${l.weight_variance_pct}%`
                      : ""}
                    {Number(l.returned_qty) > 0
                      ? ` · ${trimDecimal(l.returned_qty)} ${l.base_unit} returned`
                      : ""}
                  </span>
                  <span>{formatMoney(l.taxable)}</span>
                </span>
                {(l.lots ?? []).length > 0 ? (
                  <span className={styles.sub}>
                    Cement from:{" "}
                    {(l.lots ?? [])
                      .map((x) => `${x.label} (${trimDecimal(x.quantity)})`)
                      .join(", ")}
                  </span>
                ) : null}
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
            <Attachments
              key={`a${inv.id}`}
              refType="sales_invoice"
              refId={inv.id}
              canAdd={canBill}
            />
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
