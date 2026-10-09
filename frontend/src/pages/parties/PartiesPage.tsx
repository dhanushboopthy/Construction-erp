import { useCallback, useEffect, useRef, useState } from "react";

import { useParties } from "@/api/masters";
import { useAuth } from "@/auth/AuthContext";
import { Button } from "@/components/Button";
import { SelectField, TextField } from "@/components/Field";
import styles from "@/components/Ledger.module.css";
import { moveRowFocus, useAltKey } from "@/hooks/useKeys";
import { formatMoney, plural } from "@/lib/format";

import { PartyEditor } from "./PartyEditor";
import { TYPE_LABEL } from "./partyLabels";

type Mode = { kind: "closed" } | { kind: "new" } | { kind: "edit"; id: number };

export function PartiesPage() {
  const { user } = useAuth();
  const canWrite = user?.role === "owner" || user?.role === "counter";
  const [q, setQ] = useState("");
  const [kind, setKind] = useState("");
  const [mode, setMode] = useState<Mode>({ kind: "closed" });
  const [notice, setNotice] = useState<string | null>(null);
  const query = useParties(q, kind);
  const listRef = useRef<HTMLTableSectionElement>(null);
  const search = useRef<HTMLInputElement>(null);

  const openNew = useCallback(() => {
    if (canWrite) {
      setNotice(null);
      setMode({ kind: "new" });
    }
  }, [canWrite]);
  useAltKey("n", openNew);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement).tagName;
      if (e.key === "/" && tag !== "INPUT" && tag !== "TEXTAREA" && tag !== "SELECT") {
        e.preventDefault();
        search.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const close = useCallback(() => {
    const id = mode.kind === "edit" ? mode.id : null;
    setMode({ kind: "closed" });
    requestAnimationFrame(() => {
      const row = id ? listRef.current?.querySelector<HTMLElement>(`[data-row="${id}"]`) : null;
      (row ?? search.current)?.focus();
    });
  }, [mode]);

  const rows = query.data?.items ?? [];
  const selected = mode.kind === "edit" ? rows.find((r) => r.id === mode.id) : undefined;

  return (
    <section aria-labelledby="parties-title" className={styles.page}>
      <div className={styles.toolbar}>
        <h1 id="parties-title" className={styles.title}>
          Customers and suppliers
        </h1>
        {canWrite ? (
          <Button variant="primary" onClick={openNew} aria-keyshortcuts="Alt+N">
            Add party
          </Button>
        ) : null}
        <p className={styles.keys}>/ search · Alt+N new · ↑↓ move · Enter open · Esc close</p>
      </div>
      <div className={styles.filters}>
        <div className={styles.search}>
          <TextField
            ref={search}
            label="Search"
            type="search"
            placeholder="Name, phone or GSTIN"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
        </div>
        <SelectField label="Show" value={kind} onChange={(e) => setKind(e.target.value)}>
          <option value="">Everyone</option>
          <option value="customer">Customers</option>
          <option value="supplier">Suppliers</option>
        </SelectField>
      </div>
      {notice ? (
        <p role="status" className={styles.saved}>
          {notice}
        </p>
      ) : null}
      <div className={styles.split}>
        <div className={styles.tableWrap}>
          {query.isPending ? (
            <p role="status" className={styles.empty}>
              Loading…
            </p>
          ) : null}
          {query.isError ? <p className={styles.formError}>Parties could not be loaded.</p> : null}
          {query.isSuccess && rows.length === 0 ? (
            <p className={styles.empty}>
              {q || kind
                ? "Nobody matches. Clear the search to see all."
                : "No customers or suppliers yet. Add the first with Alt+N."}
            </p>
          ) : null}
          {rows.length > 0 ? (
            <table className={styles.table}>
              <thead>
                <tr>
                  <th scope="col">Name</th>
                  <th scope="col">Type</th>
                  <th scope="col">GSTIN</th>
                  <th scope="col">Phone</th>
                  <th scope="col" className="num">
                    Credit limit
                  </th>
                  <th scope="col" className="num">
                    Sites
                  </th>
                  <th scope="col">Status</th>
                </tr>
              </thead>
              <tbody ref={listRef} onKeyDown={moveRowFocus}>
                {rows.map((p) => (
                  <tr
                    key={p.id}
                    className={[
                      selected?.id === p.id ? styles.selected : "",
                      p.is_active ? "" : styles.inactive,
                    ].join(" ")}
                  >
                    <td>
                      <button
                        type="button"
                        className={styles.rowButton}
                        data-row={p.id}
                        aria-current={selected?.id === p.id ? "true" : undefined}
                        onClick={() => {
                          setNotice(null);
                          setMode({ kind: "edit", id: p.id });
                        }}
                      >
                        {p.name}
                      </button>
                    </td>
                    <td>{TYPE_LABEL[p.type]}</td>
                    <td>{p.gstin ?? "—"}</td>
                    <td>{p.phone ?? "—"}</td>
                    <td className="num">
                      {p.credit_allowed
                        ? p.credit_limit
                          ? formatMoney(p.credit_limit)
                          : "Default"
                        : "No credit"}
                    </td>
                    <td className="num">{p.sites.length}</td>
                    <td className={styles.status}>
                      <span className={p.is_active ? styles.statusActive : styles.statusInactive}>
                        {p.is_active ? "Active" : "Inactive"}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : null}
          {query.isSuccess ? (
            <p className={styles.results}>{plural(query.data.total, "party", "parties")}</p>
          ) : null}
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
