import { useState, type FormEvent } from "react";

import { toFormError } from "@/api/errors";
import { useAddSite, useUpdateSite } from "@/api/masters";
import type { Party, Site } from "@/api/types";
import { Button } from "@/components/Button";
import { SelectField, TextAreaField, TextField } from "@/components/Field";
import styles from "@/components/Ledger.module.css";
import { GST_STATES, stateName } from "@/lib/gstStates";

/** Delivery sites of a customer: each bill belongs to one site (B9). */
export function SitesSection({ party }: { party: Party }) {
  const add = useAddSite();
  const update = useUpdateSite();
  const [editing, setEditing] = useState<Site | "new" | null>(null);
  const [name, setName] = useState("");
  const [address, setAddress] = useState("");
  const [state, setState] = useState(party.state_code);
  const [gstin, setGstin] = useState("");
  const [error, setError] = useState<{ field: string | null; message: string } | null>(null);

  function begin(site: Site | "new") {
    setEditing(site);
    setError(null);
    if (site === "new") {
      setName("");
      setAddress("");
      setState(party.state_code);
      setGstin("");
    } else {
      setName(site.name);
      setAddress(site.address);
      setState(site.state_code);
      setGstin(site.gstin ?? "");
    }
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (!name.trim()) {
      setError({ field: "name", message: "Enter a site name, e.g. Anna Nagar villa." });
      return;
    }
    const body = {
      name: name.trim(),
      address: address.trim(),
      state_code: state,
      gstin: gstin.trim().toUpperCase() || null,
    };
    try {
      if (editing === "new") await add.mutateAsync({ partyId: party.id, body });
      else if (editing) await update.mutateAsync({ id: editing.id, body });
      setEditing(null);
    } catch (err) {
      setError(toFormError(err));
    }
  }

  return (
    <section className={styles.subsection} aria-labelledby={`sites-${party.id}`}>
      <h3 id={`sites-${party.id}`}>Delivery sites</h3>
      {party.sites.length === 0 ? (
        <p className={styles.sub}>No sites yet. Each bill is made out to one site, so add one.</p>
      ) : (
        <ul className={styles.stack}>
          {party.sites.map((s) => (
            <li key={s.id}>
              <strong>{s.name}</strong> {s.is_active ? "" : "(inactive)"}
              <br />
              <span className={styles.sub}>
                {stateName(s.state_code)} · {s.gstin ?? "URP (no GSTIN)"}
              </span>
              <div className={styles.actions}>
                <Button variant="quiet" onClick={() => begin(s)}>
                  Edit {s.name}
                </Button>
                <Button
                  variant="quiet"
                  onClick={() =>
                    void update.mutateAsync({ id: s.id, body: { is_active: !s.is_active } })
                  }
                >
                  {s.is_active ? "Deactivate" : "Activate"} {s.name}
                </Button>
              </div>
            </li>
          ))}
        </ul>
      )}
      {editing === null ? (
        <div className={styles.actions}>
          <Button onClick={() => begin("new")}>Add site</Button>
        </div>
      ) : (
        <form className={styles.stack} onSubmit={(e) => void onSubmit(e)} noValidate>
          <TextField
            label="Site name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            error={error?.field === "name" ? error.message : null}
            autoFocus
          />
          <TextAreaField
            label="Site address"
            value={address}
            onChange={(e) => setAddress(e.target.value)}
          />
          <SelectField
            label="Site state"
            value={state}
            onChange={(e) => setState(e.target.value)}
            hint="Decides CGST+SGST or IGST on the bill (G5)."
          >
            {GST_STATES.map((s) => (
              <option key={s.code} value={s.code}>
                {s.code} {s.name}
              </option>
            ))}
          </SelectField>
          <TextField
            label="Site GSTIN"
            rule="G13"
            maxLength={15}
            className={styles.code}
            value={gstin}
            onChange={(e) => setGstin(e.target.value)}
            error={error?.field === "gstin" ? error.message : null}
            hint="Leave blank if the site has none; e-way bills then say URP."
          />
          {error && error.field !== "name" && error.field !== "gstin" ? (
            <p role="alert" className={styles.formError}>
              {error.message}
            </p>
          ) : null}
          <div className={styles.actions}>
            <Button type="submit" variant="primary" disabled={add.isPending || update.isPending}>
              {editing === "new" ? "Add site" : "Save site"}
            </Button>
            <Button onClick={() => setEditing(null)}>Cancel</Button>
          </div>
        </form>
      )}
    </section>
  );
}
