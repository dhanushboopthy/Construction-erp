import { useStock, type StockRow } from "@/api/ledger";
import { useLocations } from "@/api/setup";
import type { StockItemOwner } from "@/api/types";
import { useAuth } from "@/auth/AuthContext";
import { DataTable, type Column } from "@/components/DataTable";
import { SelectField } from "@/components/Field";
import styles from "@/components/Ledger.module.css";
import { StatusPill } from "@/components/StatusPill";
import { TableToolbar } from "@/components/TableToolbar";
import { useTableFilters } from "@/hooks/useTableFilters";
import { formatMoney, plural, trimDecimal } from "@/lib/format";

const isOwnerRow = (row: StockRow): row is StockItemOwner => "avg_cost" in row;

/** Stock per item and place, rebuilt from the stock ledger. Cost and value are the owner's. */
export function StockPage() {
  const { user } = useAuth();
  const filters = useTableFilters();
  const q = filters.q;
  const locationId = filters.get("place");
  const locations = useLocations();
  const stock = useStock(q, locationId);
  const all = stock.data ?? [];
  const rows = all.filter(
    (r) =>
      !filters.status ||
      (filters.status === "out" ? Number(r.quantity) <= 0 : Number(r.quantity) > 0),
  );
  const shown = (locations.data ?? []).filter((l) => !locationId || String(l.id) === locationId);
  const owner = user?.role === "owner";
  const totalValue = rows.reduce(
    (sum, r) => (isOwnerRow(r) ? sum + Math.round(Number(r.value) * 100) : sum),
    0,
  );

  const columns: Column<StockRow>[] = [
    { id: "item", header: "Item", cell: (r) => r.name },
    { id: "unit", header: "Unit", cell: (r) => r.base_unit },
    ...shown.map((l) => ({
      id: `loc-${l.id}`,
      header: l.code,
      numeric: true,
      cell: (r: StockRow) =>
        trimDecimal(r.locations.find((x) => x.location_id === l.id)?.quantity ?? "0"),
    })),
    {
      id: "total",
      header: "Total",
      numeric: true,
      cell: (r) => <strong>{trimDecimal(r.quantity)}</strong>,
    },
    {
      id: "status",
      header: "Status",
      cell: (r) =>
        Number(r.quantity) <= 0 ? (
          <StatusPill tone="critical" label="Out of stock" />
        ) : (
          <StatusPill tone="good" label="In stock" />
        ),
    },
    ...(owner
      ? [
          {
            id: "cost",
            header: "Avg cost (₹)",
            numeric: true,
            cell: (r: StockRow) => (isOwnerRow(r) ? trimDecimal(r.avg_cost) : ""),
          },
          {
            id: "value",
            header: "Value (₹)",
            numeric: true,
            cell: (r: StockRow) => (isOwnerRow(r) ? formatMoney(r.value) : ""),
          },
        ]
      : []),
  ];

  return (
    <div className={styles.stack}>
      <TableToolbar
        filters={filters}
        searchPlaceholder="Item, brand or size"
        statusOptions={[
          { value: "in", label: "In stock" },
          { value: "out", label: "Out of stock" },
        ]}
        extra={
          <SelectField
            label="Place"
            value={locationId}
            onChange={(e) => filters.set("place", e.target.value)}
          >
            <option value="">All places</option>
            {(locations.data ?? []).map((l) => (
              <option key={l.id} value={l.id}>
                {l.code} {l.name}
              </option>
            ))}
          </SelectField>
        }
      />
      <DataTable
        caption="Stock levels"
        columns={columns}
        rows={rows}
        rowKey={(r) => r.item_id}
        loading={stock.isPending}
        error={stock.isError ? "Stock could not be loaded." : null}
        onRetry={() => void stock.refetch()}
        empty={
          q || locationId || filters.status
            ? "Nothing matches. Clear the search to see all stock."
            : owner
              ? "No stock yet. Enter opening stock under Settings, then purchases will add to it."
              : "No stock yet. Ask the owner to enter opening stock."
        }
        footer={stock.isSuccess ? plural(rows.length, "item") : undefined}
      />
      {owner && rows.length > 0 ? (
        <div className={styles.totalBand}>
          <span>Stock value at average cost</span>
          <strong>₹{formatMoney((totalValue / 100).toFixed(2))}</strong>
        </div>
      ) : null}
    </div>
  );
}
