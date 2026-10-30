import { useCallback, useRef, useState } from "react";
import { useSearchParams } from "react-router";

import { useParties } from "@/api/masters";
import type { Party } from "@/api/types";
import { useAuth } from "@/auth/AuthContext";
import { Button } from "@/components/Button";
import { DataTable, type Column } from "@/components/DataTable";
import { PageHeader } from "@/components/PageHeader";
import { StatusPill } from "@/components/StatusPill";
import { TableToolbar } from "@/components/TableToolbar";
import styles from "@/components/Ledger.module.css";
import { useAltKey } from "@/hooks/useKeys";
import { useTableFilters } from "@/hooks/useTableFilters";
import { formatMoney, plural } from "@/lib/format";

import { PartyEditor } from "./PartyEditor";
import { TYPE_LABEL } from "./partyLabels";

type Mode = { kind: "closed" } | { kind: "new" } | { kind: "edit"; id: number };

const COLUMNS: Column<Party>[] = [
  { id: "name", header: "Name", cell: (p) => p.name },
  { id: "type", header: "Type", cell: (p) => TYPE_LABEL[p.type] },
  { id: "gstin", header: "GSTIN", cell: (p) => p.gstin ?? "—" },
  { id: "phone", header: "Phone", cell: (p) => p.phone ?? "—" },
  {
    id: "credit",
    header: "Credit limit",
    numeric: true,
    cell: (p) =>
      p.credit_allowed ? (p.credit_limit ? formatMoney(p.credit_limit) : "Default") : "No credit",
  },
  { id: "sites", header: "Sites", numeric: true, cell: (p) => p.sites.length },
  {
    id: "status",
    header: "Status",
    cell: (p) => (
      <StatusPill
        tone={p.is_active ? "good" : "neutral"}
        label={p.is_active ? "Active" : "Inactive"}
      />
    ),
  },
];

export function PartiesPage() {
  const { user } = useAuth();
  const canWrite = user?.role === "owner" || user?.role === "counter";
  const filters = useTableFilters();
  const q = filters.q;
  const kind = filters.status;
  // A link such as /parties?party=12 (the dues table on Today) opens that customer's editor.
  const [params] = useSearchParams();
  const linked = Number(params.get("party"));
  const [mode, setMode] = useState<Mode>(
    Number.isInteger(linked) && linked > 0 ? { kind: "edit", id: linked } : { kind: "closed" },
  );
  const [notice, setNotice] = useState<string | null>(null);
  const query = useParties(q, kind);
  const listRef = useRef<HTMLTableSectionElement>(null);

  const openNew = useCallback(() => {
    if (canWrite) {
      setNotice(null);
      setMode({ kind: "new" });
    }
  }, [canWrite]);
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
    <section aria-labelledby="parties-title" className={styles.page}>
      <PageHeader
        eyebrow="Accounts"
        title="Customers and suppliers"
        titleId="parties-title"
        subtitle="Their sites, credit limits and dues. / search · Alt+N new · ↑↓ move · Enter open · Esc close"
        actions={
          canWrite ? (
            <Button variant="primary" onClick={openNew} aria-keyshortcuts="Alt+N">
              Add party
            </Button>
          ) : null
        }
      />
      <TableToolbar
        filters={filters}
        searchPlaceholder="Name, phone or GSTIN"
        statusLabel="Show"
        allStatusesLabel="Everyone"
        statusOptions={[
          { value: "customer", label: "Customers" },
          { value: "supplier", label: "Suppliers" },
        ]}
      />
      {notice ? (
        <p role="status" className={styles.saved}>
          {notice}
        </p>
      ) : null}
      <div className={styles.split}>
        <div ref={listRef}>
          <DataTable
            caption="Customers and suppliers"
            columns={COLUMNS}
            rows={rows}
            rowKey={(r) => r.id}
            selectedKey={selected?.id ?? null}
            onOpen={(p) => {
              setNotice(null);
              setMode({ kind: "edit", id: p.id });
            }}
            loading={query.isPending}
            error={query.isError ? "Parties could not be loaded." : null}
            onRetry={() => void query.refetch()}
            empty={
              q || kind
                ? "Nobody matches. Clear the search to see all."
                : "No customers or suppliers yet. Add the first with Alt+N."
            }
            footer={query.isSuccess ? plural(query.data.total, "party", "parties") : undefined}
          />
        </div>
        {mode.kind === "new" ? (
          <PartyEditor
            key="new"
            onClose={close}
            onDone={(p) => {
              setNotice("Party created. Add a delivery site below if they are a customer.");
              setMode({ kind: "edit", id: p.id });
            }}
          />
        ) : selected ? (
          <PartyEditor
            key={selected.id}
            party={selected}
            onClose={close}
            onDone={() => setNotice("Changes saved.")}
          />
        ) : null}
      </div>
    </section>
  );
}
