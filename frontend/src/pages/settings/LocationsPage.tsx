import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";

import { toFormError, type FormError } from "@/api/errors";
import { useCreateLocation, useLocations, useUpdateLocation } from "@/api/setup";
import type { Location, LocationKind } from "@/api/types";
import { Button } from "@/components/Button";
import { CheckField, SelectField, TextAreaField, TextField } from "@/components/Field";
import { moveRowFocus, useAltKey } from "@/hooks/useKeys";
import { GST_STATES, stateName } from "@/lib/gstStates";

import styles from "./Settings.module.css";

const KIND_LABEL: Record<LocationKind, string> = { shop: "Shop", godown: "Godown" };

const T = {
  heading: "Shops and godown",
  add: "Add location",
  keys: "Alt+N new · ↑↓ move · Enter open · Esc close",
  loading: "Loading locations…",
  loadFailed: "Locations could not be loaded.",
  empty: "No shops yet. Add the first shop with Alt+N.",
  newTitle: "New location",
  create: "Create location",
  saveChanges: "Save changes",
  saved: "Changes saved.",
  created: "Location created.",
  close: "Close",
  codeHint: "1–2 capital letters or digits, e.g. S3. Starts every bill number (S3/26-27/00001).",
  codeFixed: "The code is printed inside issued bill numbers, so it cannot change.",
};

type Mode = { kind: "closed" } | { kind: "new" } | { kind: "edit"; id: number };

export function LocationsPage() {
  const locations = useLocations(true);
  const [mode, setMode] = useState<Mode>({ kind: "closed" });
  const [notice, setNotice] = useState<string | null>(null);
  const listRef = useRef<HTMLTableSectionElement>(null);

  const openNew = useCallback(() => {
    setNotice(null);
    setMode({ kind: "new" });
  }, []);
  useAltKey("n", openNew);

  const close = useCallback(() => {
    const id = mode.kind === "edit" ? mode.id : null;
    setMode({ kind: "closed" });
    requestAnimationFrame(() => {
      const row = id ? listRef.current?.querySelector<HTMLElement>(`[data-row="${id}"]`) : null;
      (row ?? listRef.current?.querySelector<HTMLElement>("[data-row]"))?.focus();
    });
  }, [mode]);

  if (locations.isPending) return <p role="status">{T.loading}</p>;
  if (locations.isError) return <p className={styles.formError}>{T.loadFailed}</p>;

  const selected = mode.kind === "edit" ? locations.data.find((l) => l.id === mode.id) : undefined;

  return (
    <>
      <div className={styles.toolbar}>
        <h2>{T.heading}</h2>
        <Button variant="primary" onClick={openNew} aria-keyshortcuts="Alt+N">
          {T.add}
        </Button>
        <p className={styles.keys}>{T.keys}</p>
      </div>
      {notice ? (
        <p role="status" className={styles.saved}>
          {notice}
        </p>
      ) : null}
      <div className={styles.split}>
        <div className={styles.tableWrap}>
          {locations.data.length === 0 ? (
            <p className={styles.empty}>{T.empty}</p>
          ) : (
            <table className={styles.table}>
              <thead>
                <tr>
                  <th scope="col">Code</th>
                  <th scope="col">Name</th>
                  <th scope="col">Kind</th>
                  <th scope="col">State</th>
                  <th scope="col">Phone</th>
                  <th scope="col">Status</th>
                </tr>
              </thead>
              <tbody ref={listRef} onKeyDown={moveRowFocus}>
                {locations.data.map((l) => (
                  <tr
                    key={l.id}
                    className={[
                      selected?.id === l.id ? styles.selected : "",
                      l.is_active ? "" : styles.inactive,
                    ].join(" ")}
                  >
                    <td>
                      <button
                        type="button"
                        className={`${styles.rowButton} ${styles.code}`}
                        data-row={l.id}
                        aria-current={selected?.id === l.id ? "true" : undefined}
                        aria-label={`${l.code}, ${l.name}`}
                        onClick={() => {
                          setNotice(null);
                          setMode({ kind: "edit", id: l.id });
                        }}
                      >
                        {l.code}
                      </button>
                    </td>
                    <td>{l.name}</td>
                    <td>{KIND_LABEL[l.kind]}</td>
                    <td>
                      {l.state_code} {stateName(l.state_code)}
                    </td>
                    <td>{l.phone ?? "—"}</td>
                    <td className={styles.status}>
                      <span className={l.is_active ? styles.statusActive : styles.statusInactive}>
                        {l.is_active ? "Active" : "Inactive"}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
        {mode.kind === "new" ? (
          <LocationEditor
            key="new"
            onClose={close}
            onDone={(loc) => {
              setNotice(T.created);
              setMode({ kind: "edit", id: loc.id });
            }}
          />
        ) : selected ? (
          <LocationEditor
            key={selected.id}
            location={selected}
            onClose={close}
            onDone={() => setNotice(T.saved)}
          />
        ) : null}
      </div>
    </>
  );
}

function LocationEditor({
  location,
  onClose,
  onDone,
}: {
  location?: Location;
  onClose: () => void;
  onDone: (location: Location) => void;
}) {
  const create = useCreateLocation();
  const update = useUpdateLocation();
  const [code, setCode] = useState("");
  const [name, setName] = useState(location?.name ?? "");
  const [kind, setKind] = useState<LocationKind>(location?.kind ?? "shop");
  const [stateCode, setStateCode] = useState(location?.state_code ?? "33");
  const [address, setAddress] = useState(location?.address ?? "");
  const [phone, setPhone] = useState(location?.phone ?? "");
  const [active, setActive] = useState(location?.is_active ?? true);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [serverError, setServerError] = useState<FormError | null>(null);
  const firstField = useRef<HTMLInputElement>(null);

  useEffect(() => firstField.current?.focus(), []);

  const titleId = `location-editor-${location?.id ?? "new"}`;
  const pending = create.isPending || update.isPending;

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    const found: Record<string, string> = {};
    if (!location && !/^[A-Z0-9]{1,2}$/.test(code)) found.code = T.codeHint;
    if (!name.trim()) found.name = "Enter a name, e.g. Shop 3.";
    setErrors(found);
    setServerError(null);
    if (Object.keys(found).length > 0) return;
    const common = {
      name: name.trim(),
      state_code: stateCode,
      address: address.trim(),
      phone: phone.trim() || null,
    };
    try {
      const saved = location
        ? await update.mutateAsync({ id: location.id, body: { ...common, is_active: active } })
        : await create.mutateAsync({ ...common, code, kind });
      onDone(saved);
    } catch (err) {
      setServerError(toFormError(err));
    }
  }

  const fieldError = (key: string) =>
    errors[key] ?? (serverError?.field === key ? serverError.message : null);
  const generalError =
    serverError && !["code", "name"].includes(serverError.field ?? "") ? serverError.message : null;

  return (
    <aside
      className={styles.panel}
      aria-labelledby={titleId}
      onKeyDown={(e) => {
        if (e.key === "Escape") onClose();
      }}
    >
      <div className={styles.panelHead}>
        <h2 id={titleId}>{location ? `${location.code} ${location.name}` : T.newTitle}</h2>
        <Button variant="quiet" onClick={onClose} aria-keyshortcuts="Escape">
          {T.close}
        </Button>
      </div>
      <form onSubmit={(e) => void onSubmit(e)} noValidate>
        {location ? (
          <TextField
            label="Code"
            value={location.code}
            readOnly
            hint={T.codeFixed}
            className={styles.code}
          />
        ) : (
          <TextField
            ref={firstField}
            label="Code"
            value={code}
            maxLength={2}
            autoComplete="off"
            className={styles.code}
            onChange={(e) => setCode(e.target.value.toUpperCase())}
            error={fieldError("code")}
            hint={T.codeHint}
          />
        )}
        <TextField
          ref={location ? firstField : undefined}
          label="Name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          error={fieldError("name")}
        />
        {location ? (
          <TextField label="Kind" value={KIND_LABEL[location.kind]} readOnly />
        ) : (
          <SelectField
            label="Kind"
            value={kind}
            onChange={(e) => setKind(e.target.value as LocationKind)}
            hint="Shops bill customers; the godown only holds stock."
          >
            <option value="shop">Shop</option>
            <option value="godown">Godown</option>
          </SelectField>
        )}
        <SelectField label="State" value={stateCode} onChange={(e) => setStateCode(e.target.value)}>
          {GST_STATES.map((s) => (
            <option key={s.code} value={s.code}>
              {s.code} {s.name}
            </option>
          ))}
        </SelectField>
        <TextAreaField
          label="Address"
          value={address}
          onChange={(e) => setAddress(e.target.value)}
        />
        <TextField
          label="Phone"
          type="tel"
          value={phone}
          onChange={(e) => setPhone(e.target.value)}
        />
        {location ? (
          <CheckField
            label="Active"
            checked={active}
            onChange={(e) => setActive(e.target.checked)}
            hint="Inactive locations stay in old documents but cannot be used for new ones."
          />
        ) : null}
        {generalError ? (
          <p role="alert" className={styles.formError}>
            {generalError}
          </p>
        ) : null}
        <div className={styles.actions}>
          <Button type="submit" variant="primary" disabled={pending}>
            {pending ? "Saving…" : location ? T.saveChanges : T.create}
          </Button>
        </div>
      </form>
    </aside>
  );
}
