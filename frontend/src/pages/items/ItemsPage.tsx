import { useCallback, useRef, useState } from "react";

import { useItems, type ItemRow } from "@/api/masters";
import type { ItemCategory, ItemOwner } from "@/api/types";
import { useAuth } from "@/auth/AuthContext";
import { Button } from "@/components/Button";
import { DataTable, type Column } from "@/components/DataTable";
import { PageHeader } from "@/components/PageHeader";
import { StatusPill } from "@/components/StatusPill";
import { TableToolbar } from "@/components/TableToolbar";
import styles from "@/components/Ledger.module.css";
import { plural } from "@/lib/format";
import { useAltKey } from "@/hooks/useKeys";
import { useTableFilters } from "@/hooks/useTableFilters";

import { ItemDetail, ItemEditor } from "./ItemEditor";
import { CATEGORIES, categoryLabel } from "./itemLabels";
import { ImportPanel } from "./ImportPanel";

type Mode =
  { kind: "closed" } | { kind: "new" } | { kind: "import" } | { kind: "edit"; id: number };

const COLUMNS: Column<ItemRow>[] = [
  { id: "name", header: "Name", cell: (r) => r.name },
  { id: "category", header: "Category", cell: (r) => categoryLabel(r.category) },
  { id: "brand", header: "Brand", cell: (r) => r.brand ?? "—" },
  { id: "size", header: "Size", cell: (r) => r.size ?? "—" },
  { id: "unit", header: "Unit", cell: (r) => r.base_unit },
  { id: "gst", header: "GST %", numeric: true, cell: (r) => r.gst_rate },
  { id: "hsn", header: "HSN", cell: (r) => r.hsn },
  {
    id: "status",
    header: "Status",
    cell: (r) => (
      <StatusPill
        tone={r.is_active ? "good" : "neutral"}
        label={r.is_active ? "Active" : "Inactive"}
      />
    ),
  },
];

export function ItemsPage() {
  const { user } = useAuth();
  const isOwner = user?.role === "owner";
  const filters = useTableFilters();
  const q = filters.q;
  const category = filters.status as ItemCategory | "";
  const [mode, setMode] = useState<Mode>({ kind: "closed" });
  const [notice, setNotice] = useState<string | null>(null);
  const query = useItems(q, category);
  const listRef = useRef<HTMLTableSectionElement>(null);

  const openNew = useCallback(() => {
    if (!isOwner) return;
    setNotice(null);
    setMode({ kind: "new" });
  }, [isOwner]);
  useAltKey("n", openNew);

  const close = useCallback(() => {
    const id = mode.kind === "edit" ? mode.id : null;
    setMode({ kind: "closed" });
    requestAnimationFrame(() => {
      const row = id ? listRef.current?.querySelector<HTMLElement>(`[data-row="${id}"]`) : null;
      (row ?? document.querySelector<HTMLElement>("[role=search] input"))?.focus();
    });
  }, [mode]);

  const rows = query.data?.items ?? [];
  const selected = mode.kind === "edit" ? rows.find((r) => r.id === mode.id) : undefined;

  return (
    <section aria-labelledby="items-title" className={styles.page}>
      <PageHeader
        eyebrow="Catalogue"
        title="Items"
        titleId="items-title"
        subtitle="What the shop sells: units, GST and HSN. / search · Alt+N new · ↑↓ move · Enter open · Esc close"
        actions={
          isOwner ? (
            <>
              <Button variant="primary" onClick={openNew} aria-keyshortcuts="Alt+N">
                Add item
              </Button>
              <Button onClick={() => setMode({ kind: "import" })}>Import from Excel</Button>
            </>
          ) : null
        }
      />
      <TableToolbar
        filters={filters}
        searchPlaceholder="Name, brand or size"
        statusLabel="Category"
        allStatusesLabel="All categories"
        statusOptions={CATEGORIES.map((c) => ({ value: c.value, label: c.label }))}
      />
      {notice ? (
        <p role="status" className={styles.saved}>
          {notice}
        </p>
      ) : null}
      <div className={styles.split}>
        <div ref={listRef}>
          <DataTable
            caption="Items"
            columns={COLUMNS}
            rows={rows}
            rowKey={(r) => r.id}
            selectedKey={selected?.id ?? null}
            onOpen={(item) => {
              setNotice(null);
              setMode({ kind: "edit", id: item.id });
            }}
            loading={query.isPending}
            error={query.isError ? "Items could not be loaded." : null}
            onRetry={() => void query.refetch()}
            empty={
              q || category
                ? "No items match. Clear the search to see all."
                : isOwner
                  ? "No items yet. Add one with Alt+N, or import a sheet from Excel."
                  : "No items yet. Ask the owner to add them."
            }
            footer={query.isSuccess ? plural(query.data.total, "item") : undefined}
          />
        </div>
        {mode.kind === "new" && isOwner ? (
          <ItemEditor
            key="new"
            onClose={close}
            onDone={(item) => {
              setNotice("Item created.");
              setMode({ kind: "edit", id: item.id });
            }}
          />
        ) : mode.kind === "import" && isOwner ? (
          <ImportPanel onClose={close} />
        ) : selected && isOwner ? (
          <ItemEditor
            key={selected.id}
            item={selected as ItemOwner}
            onClose={close}
            onDone={() => setNotice("Changes saved.")}
          />
        ) : selected ? (
          <ItemDetail key={selected.id} item={selected} onClose={close} />
        ) : null}
      </div>
    </section>
  );
}
