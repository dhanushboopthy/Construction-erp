import { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router";

import { useSchemes } from "@/api/documents";
import { usePurchases, type PurchaseRow } from "@/api/purchasing";
import type { PurchaseOwner } from "@/api/types";
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
import { includesText } from "@/lib/filters";
import { formatMoney, plural, trimDecimal } from "@/lib/format";

import { PurchaseReturn } from "./PurchaseReturn";

const isOwnerRow = (row: PurchaseRow): row is PurchaseOwner => "supplier_payable" in row;

export function PurchasesPage() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const location = useLocation();
  const saved = (location.state as { saved?: string } | null)?.saved;
  const query = usePurchases();
  const alerts = useSchemes(true, user?.role !== "counter");
  const [openId, setOpenId] = useState<number | null>(null);
  useAltKey("n", () => void navigate("/purchases/new"));
  const filters = useTableFilters();
  const all = query.data?.items ?? [];
  const rows = all.filter(
    (p) =>
      includesText(filters.q, p.number, p.supplier_name, p.bill_no) &&
      (!filters.status || p.mode === filters.status),
  );
  const selected = all.find((r) => r.id === openId);
  const columns: Column<PurchaseRow>[] = [
    { id: "number", header: "Number", cell: (p) => p.number },
    { id: "date", header: "Date", cell: (p) => p.bill_date },
    { id: "supplier", header: "Supplier", cell: (p) => p.supplier_name },
    { id: "bill", header: "Bill no.", cell: (p) => p.bill_no },
    { id: "at", header: "At", cell: (p) => p.location_code },
    {
      id: "goes",
      header: "Goes to",
      cell: (p) =>
        p.mode === "stock" ? (
          <StatusPill tone="neutral" label="Stock" />
        ) : (
          <StatusPill tone="accent" label="Customer's site" />
        ),
    },
    ...(all.some(isOwnerRow)
      ? [
          {
            id: "owe",
            header: "We owe (₹)",
            numeric: true,
            cell: (p: PurchaseRow) => (isOwnerRow(p) ? formatMoney(p.supplier_payable) : ""),
          },
        ]
      : []),
  ];

  return (
    <section aria-labelledby="purchases-title" className={styles.page}>
      <PageHeader
        eyebrow="Purchases"
        title="Purchases"
        titleId="purchases-title"
        subtitle="Supplier bills with landed cost. Alt+N new purchase"
        actions={
          <>
            <Button
              variant="primary"
              onClick={() => void navigate("/purchases/new")}
              aria-keyshortcuts="Alt+N"
            >
              New purchase
            </Button>
            <Link to="/purchases/orders">Purchase orders</Link>
            {user?.role !== "counter" ? (
              <Link to="/purchases/schemes">Supplier schemes</Link>
            ) : null}
          </>
        }
      />
      {alerts.data && alerts.data.length > 0 ? (
        <p role="status" className={styles.callout}>
          {alerts.data
            .map(
              (s) =>
                `${s.party_name}: ${s.name} is ${s.pct}% done, ${trimDecimal(s.remaining)} ${s.unit} to go`,
            )
            .join(". ")}
          .
        </p>
      ) : null}
      {saved ? (
        <p role="status" className={styles.saved}>
          Saved as {saved}.
        </p>
      ) : null}
      <TableToolbar
        filters={filters}
        searchPlaceholder="Number, supplier or bill no."
        statusLabel="Goes to"
        allStatusesLabel="Everything"
        statusOptions={[
          { value: "stock", label: "Stock" },
          { value: "direct", label: "Customer's site" },
        ]}
      />
      <div className={styles.split}>
        <DataTable
          caption="Purchases"
          columns={columns}
          rows={rows}
          rowKey={(p) => p.id}
          selectedKey={openId}
          onOpen={(p) => setOpenId(p.id)}
          loading={query.isPending}
          error={query.isError ? "Purchases could not be loaded." : null}
          onRetry={() => void query.refetch()}
          empty={
            filters.q || filters.status
              ? "No purchases match."
              : "No purchases yet. Press Alt+N to enter the first supplier bill."
          }
          footer={query.isSuccess ? plural(rows.length, "purchase") : undefined}
        />
        {selected ? (
          <aside
            className={styles.panel}
            aria-labelledby="purchase-detail"
            onKeyDown={(e) => e.key === "Escape" && setOpenId(null)}
          >
            <div className={styles.panelHead}>
              <h2 id="purchase-detail">{selected.number}</h2>
              <Button variant="ghost" onClick={() => setOpenId(null)}>
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
                {l.weight_flagged ? (
                  <span className={styles.kv}>
                    <span>Weight differs by {l.weight_variance_pct}%</span>
                    <span>{l.weight_note}</span>
                  </span>
                ) : null}
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
            <Attachments
              key={`a${selected.id}`}
              refType="purchase"
              refId={selected.id}
              canAdd={user?.role !== "accountant"}
            />
            {isOwnerRow(selected) ? <PurchaseReturn key={selected.id} purchase={selected} /> : null}
          </aside>
        ) : null}
      </div>
    </section>
  );
}
