import { useState, type FormEvent } from "react";

import { toFormError } from "@/api/errors";
import { useInvoices } from "@/api/sales";
import { useLocations } from "@/api/setup";
import { useCreateTrip, useTrips, useVehicles } from "@/api/transport";
import { useAuth } from "@/auth/AuthContext";
import { Button } from "@/components/Button";
import { SelectField, TextField } from "@/components/Field";
import styles from "@/components/Ledger.module.css";
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
  const rows = trips.data?.items ?? [];

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
      {trips.isSuccess && rows.length === 0 ? <p className={styles.empty}>No trips yet.</p> : null}
      {rows.length > 0 ? (
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th scope="col">Date</th>
                <th scope="col">Vehicle</th>
                <th scope="col">Route</th>
                <th scope="col">Bill</th>
                <th scope="col" className="num">
                  Freight (₹)
                </th>
                <th scope="col" className="num">
                  Paid (₹)
                </th>
                <th scope="col">Pay as</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((t) => (
                <tr key={t.id}>
                  <td>{t.trip_date}</td>
                  <td>
                    {t.vehicle_number} · {t.owner_name}
                  </td>
                  <td>
                    {t.from_place} to {t.to_place}
                  </td>
                  <td>{t.invoice_number ?? t.purchase_number ?? "—"}</td>
                  <td className="num">{formatMoney(t.freight_amount)}</td>
                  <td className="num">{formatMoney(t.paid_amount)}</td>
                  <td>{t.pay_ref ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
      {trips.isSuccess ? (
        <p className={styles.results}>{plural(trips.data.total, "trip")}</p>
      ) : null}
    </div>
  );
}
