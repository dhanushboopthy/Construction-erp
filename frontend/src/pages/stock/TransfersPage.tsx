import { useState, type FormEvent } from "react";

import { toFormError } from "@/api/errors";
import { useItems } from "@/api/masters";
import { useCreateTransfer, useTransfers } from "@/api/purchasing";
import { useLocations } from "@/api/setup";
import { useAuth } from "@/auth/AuthContext";
import { Button } from "@/components/Button";
import { SelectField, TextField } from "@/components/Field";
import styles from "@/components/Ledger.module.css";
import { DataTable, type Column } from "@/components/DataTable";
import { TableToolbar } from "@/components/TableToolbar";
import { useTableFilters } from "@/hooks/useTableFilters";
import { includesText } from "@/lib/filters";
import { trimDecimal } from "@/lib/format";
import { unitNames } from "@/pages/items/itemLabels";

interface Row {
  itemId: string;
  quantity: string;
  unit: string;
}

/** Move stock between shops and the godown. Value never changes; quantity must be there (B13). */
export function TransfersPage() {
  const { user } = useAuth();
  const list = useTransfers();
  const filters = useTableFilters();
  const shown = (list.data ?? []).filter((t) =>
    includesText(filters.q, t.number, t.from_code, t.to_code, ...t.lines.map((l) => l.item_name)),
  );
  const columns: Column<NonNullable<typeof list.data>[number]>[] = [
    { id: "number", header: "Number", cell: (t) => t.number },
    { id: "date", header: "Date", cell: (t) => t.transfer_date },
    { id: "from", header: "From", cell: (t) => t.from_code },
    { id: "to", header: "To", cell: (t) => t.to_code },
    {
      id: "items",
      header: "Items",
      cell: (t) =>
        t.lines.map((l) => `${l.item_name} ${trimDecimal(l.quantity)} ${l.base_unit}`).join(", "),
    },
  ];
  const create = useCreateTransfer();
  const locations = useLocations();
  const items = useItems("", "");
  const [from, setFrom] = useState(user?.locations[0] ? String(user.locations[0].id) : "");
  const [to, setTo] = useState("");
  const [note, setNote] = useState("");
  const [rows, setRows] = useState<Row[]>([{ itemId: "", quantity: "", unit: "" }]);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);

  const itemList = (items.data?.items ?? []).filter((i) => i.is_active);
  const places = locations.data ?? [];
  const owner = user?.role === "owner";
  const setRow = (i: number, patch: Partial<Row>) =>
    setRows((rs) => rs.map((r, j) => (j === i ? { ...r, ...patch } : r)));

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setDone(null);
    if (!from || !to) return setError("Pick where the stock leaves from and where it goes.");
    if (from === to) return setError("Choose two different places.");
    if (
      rows.some(
        (r) => !r.itemId || !/^\d+(\.\d{1,3})?$/.test(r.quantity) || Number(r.quantity) <= 0,
      )
    )
      return setError("Every line needs an item and a quantity above 0.");
    setError(null);
    try {
      const made = await create.mutateAsync({
        from_location_id: Number(from),
        to_location_id: Number(to),
        note: note.trim() || null,
        lines: rows.map((r) => ({
          item_id: Number(r.itemId),
          quantity: r.quantity,
          unit: r.unit || null,
        })),
      });
      setDone(`Transfer ${made.number} recorded.`);
      setRows([{ itemId: "", quantity: "", unit: "" }]);
      setNote("");
    } catch (err) {
      setError(toFormError(err).message);
    }
  }

  return (
    <div className={styles.stack}>
      <form
        className={styles.stack}
        onSubmit={(e) => void onSubmit(e)}
        noValidate
        aria-label="New transfer"
      >
        <div className={styles.headerGrid}>
          <SelectField label="From" value={from} onChange={(e) => setFrom(e.target.value)}>
            <option value="">Choose a place</option>
            {places
              .filter((l) => owner || user?.locations.some((x) => x.id === l.id))
              .map((l) => (
                <option key={l.id} value={l.id}>
                  {l.code} {l.name}
                </option>
              ))}
          </SelectField>
          <SelectField label="To" value={to} onChange={(e) => setTo(e.target.value)}>
            <option value="">Choose a place</option>
            {places.map((l) => (
              <option key={l.id} value={l.id}>
                {l.code} {l.name}
              </option>
            ))}
          </SelectField>
          <TextField label="Note" value={note} onChange={(e) => setNote(e.target.value)} />
        </div>
        {rows.map((r, i) => {
          const item = itemList.find((x) => String(x.id) === r.itemId);
          return (
            <div key={i} className={styles.entryRow}>
              <SelectField
                label={`Item ${i + 1}`}
                value={r.itemId}
                onChange={(e) => setRow(i, { itemId: e.target.value, unit: "" })}
              >
                <option value="">Choose an item</option>
                {itemList.map((it) => (
                  <option key={it.id} value={it.id}>
                    {it.name}
                  </option>
                ))}
              </SelectField>
              <TextField
                label="Quantity"
                inputMode="decimal"
                className={styles.amount}
                value={r.quantity}
                onChange={(e) => setRow(i, { quantity: e.target.value })}
              />
              <SelectField
                label="Unit"
                value={r.unit || item?.base_unit || ""}
                onChange={(e) => setRow(i, { unit: e.target.value })}
              >
                {item ? (
                  unitNames(item).map((u) => <option key={u}>{u}</option>)
                ) : (
                  <option value="">—</option>
                )}
              </SelectField>
              <Button
                variant="ghost"
                aria-label={`Remove line ${i + 1}`}
                disabled={rows.length === 1}
                onClick={() => setRows((rs) => rs.filter((_, j) => j !== i))}
              >
                Remove
              </Button>
            </div>
          );
        })}
        {error ? (
          <p role="alert" className={styles.formError}>
            {error}
          </p>
        ) : null}
        {done ? (
          <p role="status" className={styles.saved}>
            {done}
          </p>
        ) : null}
        <div className={styles.actions}>
          <Button onClick={() => setRows((rs) => [...rs, { itemId: "", quantity: "", unit: "" }])}>
            Add line
          </Button>
          <Button type="submit" variant="primary" disabled={create.isPending}>
            Move stock
          </Button>
        </div>
      </form>

      <TableToolbar filters={filters} searchPlaceholder="Number, place or item" />
      <DataTable
        caption="Stock transfers"
        columns={columns}
        rows={shown}
        rowKey={(t) => t.id}
        loading={list.isPending}
        error={list.isError ? "Transfers could not be loaded." : null}
        onRetry={() => void list.refetch()}
        empty={filters.q ? "No transfers match." : "No transfers yet."}
      />
    </div>
  );
}
