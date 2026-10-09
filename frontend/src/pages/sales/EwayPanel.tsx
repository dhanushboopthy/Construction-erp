import { useState } from "react";

import {
  useCancelEinvoice,
  useCancelEway,
  useCreateEinvoice,
  useCreateEway,
  useEinvoiceStatus,
  useEwayStatus,
  useEwayVehicle,
  useManualEway,
} from "@/api/compliance";
import { toFormError } from "@/api/errors";
import { Button } from "@/components/Button";
import { TextField } from "@/components/Field";
import styles from "@/components/Ledger.module.css";
import { formatMoney } from "@/lib/format";

const PIN_KEY = "erp.shopPincode";

function rememberedPincode(): string {
  try {
    return window.localStorage.getItem(PIN_KEY) ?? "";
  } catch {
    return "";
  }
}

function remember(pincode: string) {
  try {
    window.localStorage.setItem(PIN_KEY, pincode);
  } catch {
    /* a private window may refuse storage; the field is just empty next time */
  }
}

const PIN = /^[1-9]\d{5}$/;

/** E-way bill and e-invoice for one bill. The shop's own pincode is remembered on this device. */
export function EwayPanel({ invoiceId, owner }: { invoiceId: number; owner: boolean }) {
  const status = useEwayStatus(invoiceId);
  const einvoice = useEinvoiceStatus(invoiceId);
  const create = useCreateEway();
  const manual = useManualEway();
  const vehicle = useEwayVehicle();
  const cancel = useCancelEway();
  const makeIrn = useCreateEinvoice();
  const cancelIrn = useCancelEinvoice();
  const [km, setKm] = useState("");
  const [from, setFrom] = useState(rememberedPincode);
  const [to, setTo] = useState("");
  const [plate, setPlate] = useState("");
  const [number, setNumber] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [showManual, setShowManual] = useState(false);

  const live = status.data?.live ?? null;
  const irn = einvoice.data?.einvoice ?? null;

  async function run(action: () => Promise<unknown>, done: string) {
    setError(null);
    setNote(null);
    try {
      await action();
      setNote(done);
    } catch (err) {
      setError(toFormError(err).message);
    }
  }

  function trip(): { distance_km: number; from_pincode: string; to_pincode: string } | null {
    if (!/^\d+$/.test(km) || Number(km) < 1 || Number(km) > 4000) {
      setError("Enter the distance in km, between 1 and 4000.");
      return null;
    }
    if (!PIN.test(from) || !PIN.test(to)) {
      setError("Pincodes have six digits.");
      return null;
    }
    remember(from);
    return { distance_km: Number(km), from_pincode: from, to_pincode: to };
  }

  if (status.isPending) return <p role="status">Checking the e-way bill…</p>;
  if (!status.data) return null;

  return (
    <div className={styles.stack} role="group" aria-label="E-way bill and e-invoice">
      <h3 style={{ margin: 0 }}>E-way bill</h3>
      {live ? (
        <>
          <span className={styles.kv}>
            <strong>{live.number}</strong>
            <span>
              {live.source === "manual" ? "Typed in" : "Made through the GSP"} · valid to{" "}
              {live.valid_until ?? "—"}
            </span>
          </span>
          <span className={styles.kv}>
            <span>Vehicle</span>
            <span>{live.vehicle_no ?? "Not added yet"}</span>
          </span>
          <div className={styles.inline}>
            <TextField
              label="Vehicle number"
              value={plate}
              onChange={(e) => setPlate(e.target.value)}
            />
            <Button
              onClick={() =>
                void run(
                  () =>
                    vehicle.mutateAsync({
                      invoiceId,
                      body: {
                        vehicle_no: plate,
                        reason: "Vehicle added or changed",
                        from_place: "Shop",
                      },
                    }),
                  "Vehicle updated on the e-way bill.",
                )
              }
            >
              Update vehicle
            </Button>
            {owner && live.can_cancel ? (
              <Button
                onClick={() =>
                  void run(
                    () => cancel.mutateAsync({ invoiceId, body: { reason: "Cancelled by owner" } }),
                    "E-way bill cancelled.",
                  )
                }
              >
                Cancel e-way bill
              </Button>
            ) : null}
          </div>
        </>
      ) : (
        <>
          <p className={styles.sub}>
            {status.data.required
              ? `Needed: this bill is above ₹${formatMoney(status.data.threshold)}.`
              : `Not needed: this bill is not above ₹${formatMoney(status.data.threshold)}.`}
          </p>
          <div className={styles.inline}>
            <TextField
              label="Distance (km)"
              inputMode="numeric"
              value={km}
              onChange={(e) => setKm(e.target.value)}
            />
            <TextField
              label="From pincode"
              inputMode="numeric"
              value={from}
              onChange={(e) => setFrom(e.target.value)}
            />
            <TextField
              label="To pincode"
              inputMode="numeric"
              value={to}
              onChange={(e) => setTo(e.target.value)}
            />
            <TextField
              label="Vehicle (optional)"
              value={plate}
              onChange={(e) => setPlate(e.target.value)}
            />
            <Button
              variant="primary"
              disabled={create.isPending}
              onClick={() => {
                const t = trip();
                if (t)
                  void run(
                    () =>
                      create.mutateAsync({
                        invoiceId,
                        body: { ...t, vehicle_no: plate.trim() || null },
                      }),
                    "E-way bill made.",
                  );
              }}
            >
              Make e-way bill
            </Button>
          </div>
          {showManual ? (
            <div className={styles.inline}>
              <TextField
                label="Number from the portal"
                inputMode="numeric"
                value={number}
                onChange={(e) => setNumber(e.target.value)}
              />
              <Button
                onClick={() => {
                  if (!/^\d{12}$/.test(number))
                    return setError("An e-way bill number has 12 digits.");
                  void run(
                    () =>
                      manual.mutateAsync({
                        invoiceId,
                        body: { number, vehicle_no: plate.trim() || null },
                      }),
                    "E-way bill number saved.",
                  );
                }}
              >
                Save number
              </Button>
            </div>
          ) : (
            <Button variant="quiet" onClick={() => setShowManual(true)}>
              The portal made it by hand? Enter the number
            </Button>
          )}
        </>
      )}

      {einvoice.data?.enabled ? (
        <>
          <h3 style={{ margin: 0 }}>E-invoice</h3>
          {irn && irn.status === "generated" ? (
            <>
              <span className={styles.kv}>
                <span>IRN</span>
                <span style={{ wordBreak: "break-all" }}>{irn.irn}</span>
              </span>
              <span className={styles.kv}>
                <span>Acknowledgement</span>
                <span>{irn.ack_no}</span>
              </span>
              {owner && irn.can_cancel ? (
                <Button
                  onClick={() =>
                    void run(
                      () => cancelIrn.mutateAsync({ invoiceId, reason: "Cancelled by owner" }),
                      "IRN cancelled.",
                    )
                  }
                >
                  Cancel IRN
                </Button>
              ) : null}
            </>
          ) : einvoice.data.required && !irn ? (
            <Button
              disabled={makeIrn.isPending}
              onClick={() => {
                if (!PIN.test(from) || !PIN.test(to))
                  return setError("Fill both pincodes above (six digits) first.");
                remember(from);
                void run(
                  () =>
                    makeIrn.mutateAsync({
                      invoiceId,
                      body: { from_pincode: from, to_pincode: to },
                    }),
                  "IRN made. It prints on the bill with its QR.",
                );
              }}
            >
              Make IRN
            </Button>
          ) : irn ? (
            <p className={styles.sub}>The IRN on this bill was cancelled.</p>
          ) : (
            <p className={styles.sub}>No IRN needed: this bill has no buyer GSTIN.</p>
          )}
        </>
      ) : null}
      {error ? (
        <p role="alert" className={styles.formError}>
          {error}
        </p>
      ) : null}
      {note ? (
        <p role="status" className={styles.saved}>
          {note}
        </p>
      ) : null}
    </div>
  );
}
