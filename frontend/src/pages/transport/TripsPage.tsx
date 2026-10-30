import { useState, type FormEvent } from "react";

import { toFormError } from "@/api/errors";
import { useInvoices } from "@/api/sales";
import { useLocations } from "@/api/setup";
import { useCreateTrip, useTrips, useVehicles } from "@/api/transport";
import { useAuth } from "@/auth/AuthContext";
import { Button } from "@/components/Button";
import { SelectField, TextField } from "@/components/Field";
import styles from "@/components/Ledger.module.css";
import { DataTable, type Column } from "@/components/DataTable";
import { StatusPill } from "@/components/StatusPill";
import { TableToolbar } from "@/components/TableToolbar";
import { useTableFilters } from "@/hooks/useTableFilters";
import { includesText } from "@/lib/filters";
import { formatMoney, plural } from "@/lib/format";

/** One run of one vehicle. Freight becomes payable to the vehicle's owner (pay it under
 * Payments, aimed at the TRIP number). A trip on a sale lowers that sale's profit. */
export function TripsPage() {
  const { user } = useAuth();
  const owner = user?.role === "owner";
  const trips = useTrips();
  const vehicles = useVehicles();
  const locations = useLocations();
  const invoices = useInvoices("");
  const create = useCreateTrip();
  const [vehicleId, setVehicleId] = useState("");
  const [invoiceId, setInvoiceId] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [freight, setFreight] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);

  const places = (locations.data ?? []).filter((l) => l.is_active);
  const filters = useTableFilters();
  const all = trips.data?.items ?? [];
  const rows = all.filter(
    (t) =>
      includesText(
        filters.q,
        t.vehicle_number,
        t.owner_name,
        t.from_place,
        t.to_place,
        t.invoice_number,
        t.purchase_number,
      ) &&
      (!filters.status ||
        (filters.status === "paid"
          ? Number(t.paid_amount) >= Number(t.freight_amount)
          : Number(t.paid_amount) < Number(t.freight_amount))),
  );
  const columns: Column<(typeof all)[number]>[] = [
    { id: "date", header: "Date", cell: (t) => t.trip_date },
    { id: "vehicle", header: "Vehicle", cell: (t) => `${t.vehicle_number} · ${t.owner_name}` },
    { id: "route", header: "Route", cell: (t) => `${t.from_place} to ${t.to_place}` },
    { id: "bill", header: "Bill", cell: (t) => t.invoice_number ?? t.purchase_number ?? "—" },
    {
      id: "freight",
      header: "Freight (₹)",
      numeric: true,
      cell: (t) => formatMoney(t.freight_amount),
    },
    { id: "paid", header: "Paid (₹)", numeric: true, cell: (t) => formatMoney(t.paid_amount) },
    {
      id: "status",
      header: "Status",
      cell: (t) =>
        Number(t.paid_amount) >= Number(t.freight_amount) ? (
          <StatusPill tone="good" label="Paid" />
        ) : (
          <StatusPill tone="warn" label="Unpaid" />
        ),
    },
    { id: "ref", header: "Pay as", cell: (t) => t.pay_ref ?? "—" },
  ];

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setDone(null);
    if (!vehicleId) return setError("Pick the vehicle.");
    if (from.trim().length < 2 || to.trim().length < 2)
      return setError("Say where the trip starts and where it ends.");
    if (!/^\d+(\.\d{1,2})?$/.test(freight)) return setError("Enter the freight in rupees.");
    const place = user?.locations[0]?.id ?? places[0]?.id;
    if (!place) return setError("No shop is set up yet.");
    setError(null);
    try {
      const made = await create.mutateAsync({
        vehicle_id: Number(vehicleId),
        location_id: place,
        invoice_id: invoiceId ? Number(invoiceId) : null,
        from_place: from.trim(),
        to_place: to.trim(),
        freight_amount: freight,
      });
      setDone(
        made.pay_ref
          ? `Trip saved. Freight ₹${formatMoney(made.freight_amount)} is owed to ${made.owner_name} (${made.pay_ref}).`
          : "Trip saved.",
      );
      setFrom("");
      setTo("");
      setFreight("");
    } catch (err) {
      setError(toFormError(err).message);
    }
  }

  return (
    <div className={styles.stack}>
      {owner ? (
        <form className={styles.stack} onSubmit={(e) => void onSubmit(e)} aria-label="Add trip">
          <div className={styles.inline}>
            <SelectField
              label="Vehicle"
              value={vehicleId}
              onChange={(e) => setVehicleId(e.target.value)}
            >
              <option value="">Choose</option>
              {(vehicles.data ?? []).map((v) => (
                <option key={v.id} value={v.id}>
                  {v.number} · {v.owner_name}
                </option>
              ))}
            </SelectField>
            <SelectField
              label="For sales bill"
              value={invoiceId}
              onChange={(e) => setInvoiceId(e.target.value)}
            >
              <option value="">None</option>
              {(invoices.data?.items ?? []).map((i) => (
                <option key={i.id} value={i.id}>
                  {i.number} · {i.party_name}
                </option>
              ))}
            </SelectField>
            <TextField label="From" value={from} onChange={(e) => setFrom(e.target.value)} />
            <TextField label="To" value={to} onChange={(e) => setTo(e.target.value)} />
            <TextField
              label="Freight (₹)"
              inputMode="decimal"
              value={freight}
              onChange={(e) => setFreight(e.target.value)}
            />
            <Button type="submit" variant="primary" disabled={create.isPending}>
              Save trip
            </Button>
          </div>
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
        </form>
      ) : null}
      <TableToolbar
        filters={filters}
        searchPlaceholder="Vehicle, route or bill"
        statusOptions={[
          { value: "paid", label: "Paid" },
          { value: "unpaid", label: "Unpaid" },
        ]}
      />
      <DataTable
        caption="Trips"
        columns={columns}
        rows={rows}
        rowKey={(t) => t.id}
        loading={trips.isPending}
        error={trips.isError ? "Trips could not be loaded." : null}
        onRetry={() => void trips.refetch()}
        empty={filters.q || filters.status ? "No trips match." : "No trips yet."}
        footer={trips.isSuccess ? plural(rows.length, "trip") : undefined}
      />
    </div>
  );
}
