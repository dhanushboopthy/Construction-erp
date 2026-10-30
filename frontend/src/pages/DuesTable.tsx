import { Link, useNavigate } from "react-router";

import { useReceivables } from "@/api/receivables";
import { DataTable, PrimaryCell, type Column } from "@/components/DataTable";
import { ProgressBar } from "@/components/ProgressBar";
import { StatusPill } from "@/components/StatusPill";
import { TableToolbar } from "@/components/TableToolbar";
import { useTableFilters } from "@/hooks/useTableFilters";
import { DUE_STATUS, dueStatus, prepareDues, type ReceivableRow } from "@/lib/dues";
import { formatDay, formatMoney } from "@/lib/format";

import styles from "./DuesTable.module.css";

const STATUS_OPTIONS = [
  { value: "overdue", label: "Overdue" },
  { value: "over_limit", label: "Over limit" },
  { value: "near_limit", label: "Near limit" },
  { value: "ok", label: "OK" },
];

const TOP = 8;

const COLUMNS: Column<ReceivableRow>[] = [
  {
    id: "customer",
    header: "Customer",
    cell: (r) => (
      <PrimaryCell
        name={r.party_name}
        avatar
        sub={
          r.oldest_due_date ? `Oldest bill due ${formatDay(r.oldest_due_date)}` : "Nothing due yet"
        }
      />
    ),
  },
  { id: "owes", header: "Owes (₹)", numeric: true, cell: (r) => formatMoney(r.balance) },
  {
    id: "overdue",
    header: "Overdue (₹)",
    numeric: true,
    cell: (r) =>
      Number(r.overdue) > 0 ? (
        <span className={styles.overdue}>
          {formatMoney(r.overdue)}
          <span className={styles.late}>
            {r.days_late === 1 ? "1 day late" : `${r.days_late ?? 0} days late`}
          </span>
        </span>
      ) : (
        "—"
      ),
  },
  {
    id: "credit",
    header: "Credit used",
    cell: (r) =>
      r.utilisation_pct === null ? (
        <span className={styles.muted}>Cash customer</span>
      ) : (
        <div className={styles.credit}>
          <ProgressBar
            value={Number(r.utilisation_pct)}
            label={`Credit used by ${r.party_name}`}
            tone={Number(r.utilisation_pct) > 100 ? "critical" : DUE_STATUS[dueStatus(r)].tone}
          />
        </div>
      ),
  },
  { id: "last", header: "Last payment", cell: (r) => formatDay(r.last_payment_date) },
  {
    id: "status",
    header: "Status",
    cell: (r) => {
      const s = DUE_STATUS[dueStatus(r)];
      return <StatusPill tone={s.tone} label={s.label} />;
    },
  },
];

/** Who owes the shop money, worst first (owner and accountant only: the receivables report is
 * not sent to counter staff). Top 8 with search and a status filter kept in the URL. */
export function DuesTable() {
  const report = useReceivables();
  const filters = useTableFilters();
  const navigate = useNavigate();
  const all = report.data ? prepareDues(report.data.rows, filters) : [];
  const shown = all.slice(0, TOP);

  return (
    <section className={styles.section} aria-labelledby="dues-title">
      <header className={styles.head}>
        <div>
          <h2 id="dues-title">Customer dues</h2>
          <p className={styles.sub}>Who owes the shop money, most overdue first.</p>
        </div>
        <Link to="/reports/receivables" className={styles.viewAll}>
          View all dues
        </Link>
      </header>
      <TableToolbar
        filters={filters}
        searchLabel="Search customers"
        searchPlaceholder="Customer name"
        statusOptions={STATUS_OPTIONS}
      />
      <DataTable
        caption="Customer dues"
        columns={COLUMNS}
        rows={shown}
        rowKey={(r) => r.party_id}
        onOpen={(r) => void navigate(`/parties?party=${r.party_id}`)}
        loading={report.isPending}
        error={report.isError ? "Customer dues could not be loaded." : null}
        onRetry={() => void report.refetch()}
        empty={
          filters.q || filters.status
            ? "No customer matches. Clear the search or the status to see everyone."
            : "No customer owes money today."
        }
        footer={
          all.length > TOP ? `Showing the first ${TOP} of ${all.length} customers.` : undefined
        }
      />
    </section>
  );
}
