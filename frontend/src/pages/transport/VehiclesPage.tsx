import { useState, type FormEvent } from "react";

import { toFormError } from "@/api/errors";
import { useCreateVehicle, useToggleVehicle, useVehicles } from "@/api/transport";
import { useAuth } from "@/auth/AuthContext";
import { Button } from "@/components/Button";
import { TextField } from "@/components/Field";
import styles from "@/components/Ledger.module.css";

/** Hired vehicles. Each one gets a supplier account, so freight is paid like any supplier bill. */
export function VehiclesPage() {
  const { user } = useAuth();
  const owner = user?.role === "owner";
  const list = useVehicles(true);
  const create = useCreateVehicle();
  const toggle = useToggleVehicle();
  const [number, setNumber] = useState("");
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setDone(null);
    if (number.trim().length < 4) return setError("Enter the vehicle number, like TN09AB1234.");
    if (name.trim().length < 2) return setError("Enter the owner's name.");
    setError(null);
    try {
      const made = await create.mutateAsync({
        number: number.trim(),
        owner_name: name.trim(),
        phone: phone.trim() || null,
      });
      setDone(`Vehicle ${made.number} added.`);
      setNumber("");
      setName("");
      setPhone("");
    } catch (err) {
      setError(toFormError(err).message);
    }
  }

  const rows = list.data ?? [];
  return (
    <div className={styles.stack}>
      {owner ? (
        <form className={styles.stack} onSubmit={(e) => void onSubmit(e)} aria-label="Add vehicle">
          <div className={styles.inline}>
            <TextField
              label="Vehicle number"
              value={number}
              onChange={(e) => setNumber(e.target.value)}
            />
            <TextField label="Owner name" value={name} onChange={(e) => setName(e.target.value)} />
            <TextField label="Phone" value={phone} onChange={(e) => setPhone(e.target.value)} />
            <Button type="submit" variant="primary" disabled={create.isPending}>
              Add vehicle
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
      {list.isSuccess && rows.length === 0 ? (
        <p className={styles.empty}>No vehicles yet. Add the first hired vehicle above.</p>
      ) : null}
      {rows.length > 0 ? (
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th scope="col">Number</th>
                <th scope="col">Owner</th>
                <th scope="col">Phone</th>
                <th scope="col">Status</th>
                {owner ? <th scope="col" /> : null}
              </tr>
            </thead>
            <tbody>
              {rows.map((v) => (
                <tr key={v.id}>
                  <td>{v.number}</td>
                  <td>{v.owner_name}</td>
                  <td>{v.phone ?? "—"}</td>
                  <td>{v.is_active ? "In use" : "Switched off"}</td>
                  {owner ? (
                    <td>
                      <Button
                        variant="quiet"
                        onClick={() => toggle.mutate({ id: v.id, is_active: !v.is_active })}
                      >
                        {v.is_active ? `Switch off ${v.number}` : `Switch on ${v.number}`}
                      </Button>
                    </td>
                  ) : null}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </div>
  );
}
