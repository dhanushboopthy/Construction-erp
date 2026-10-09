import { useCallback, useEffect, useRef, useState } from "react";

import { useItems, type ItemRow } from "@/api/masters";
import type { ItemCategory, ItemOwner } from "@/api/types";
import { useAuth } from "@/auth/AuthContext";
import { Button } from "@/components/Button";
import { SelectField, TextField } from "@/components/Field";
import styles from "@/components/Ledger.module.css";
import { plural } from "@/lib/format";
import { moveRowFocus, useAltKey } from "@/hooks/useKeys";

import { ItemDetail, ItemEditor } from "./ItemEditor";
import { CATEGORIES, categoryLabel } from "./itemLabels";
import { ImportPanel } from "./ImportPanel";

type Mode =
  { kind: "closed" } | { kind: "new" } | { kind: "import" } | { kind: "edit"; id: number };

export function ItemsPage() {
  const { user } = useAuth();
  const isOwner = user?.role === "owner";
  const [q, setQ] = useState("");
  const [category, setCategory] = useState<ItemCategory | "">("");
  const [mode, setMode] = useState<Mode>({ kind: "closed" });
  const [notice, setNotice] = useState<string | null>(null);
  const query = useItems(q, category);
  const listRef = useRef<HTMLTableSectionElement>(null);
  const search = useRef<HTMLInputElement>(null);

  const openNew = useCallback(() => {
    if (!isOwner) return;
    setNotice(null);
    setMode({ kind: "new" });
  }, [isOwner]);
  useAltKey("n", openNew);

  // "/" jumps to search, like most list screens.
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
    <section aria-labelledby="items-title" className={styles.page}>
      <div className={styles.toolbar}>
        <h1 id="items-title" className={styles.title}>
          Items
        </h1>
        {isOwner ? (
          <>
            <Button variant="primary" onClick={openNew} aria-keyshortcuts="Alt+N">
              Add item
            </Button>
            <Button onClick={() => setMode({ kind: "import" })}>Import from Excel</Button>
          </>
        ) : null}
        <p className={styles.keys}>/ search · Alt+N new · ↑↓ move · Enter open · Esc close</p>
      </div>
      <div className={styles.filters}>
        <div className={styles.search}>
          <TextField
            ref={search}
            label="Search"
            type="search"
            placeholder="Name, brand or size"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
        </div>
        <SelectField
          label="Category"
          value={category}
          onChange={(e) => setCategory(e.target.value as ItemCategory | "")}
        >
          <option value="">All categories</option>
          {CATEGORIES.map((c) => (
            <option key={c.value} value={c.value}>
              {c.label}
            </option>
          ))}
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
              Loading items…
            </p>
          ) : null}
          {query.isError ? <p className={styles.formError}>Items could not be loaded.</p> : null}
          {query.isSuccess && rows.length === 0 ? (
            <p className={styles.empty}>
              {q || category
                ? "No items match. Clear the search to see all."
                : isOwner
                  ? "No items yet. Add one with Alt+N, or import a sheet from Excel."
                  : "No items yet. Ask the owner to add them."}
            </p>
          ) : null}
          {rows.length > 0 ? (
            <table className={styles.table}>
              <thead>
                <tr>
                  <th scope="col">Name</th>
                  <th scope="col">Category</th>
                  <th scope="col">Brand</th>
                  <th scope="col">Size</th>
                  <th scope="col">Unit</th>
                  <th scope="col" className="num">
                    GST %
                  </th>
                  <th scope="col">HSN</th>
                  <th scope="col">Status</th>
                </tr>
              </thead>
              <tbody ref={listRef} onKeyDown={moveRowFocus}>
                {rows.map((item: ItemRow) => (
                  <tr
                    key={item.id}
                    className={[
                      selected?.id === item.id ? styles.selected : "",
                      item.is_active ? "" : styles.inactive,
                    ].join(" ")}
                  >
                    <td>
                      <button
                        type="button"
                        className={styles.rowButton}
                        data-row={item.id}
                        aria-current={selected?.id === item.id ? "true" : undefined}
                        onClick={() => {
                          setNotice(null);
                          setMode({ kind: "edit", id: item.id });
                        }}
                      >
                        {item.name}
                      </button>
                    </td>
                    <td>{categoryLabel(item.category)}</td>
                    <td>{item.brand ?? "—"}</td>
                    <td>{item.size ?? "—"}</td>
                    <td>{item.base_unit}</td>
                    <td className="num">{item.gst_rate}</td>
                    <td>{item.hsn}</td>
                    <td className={styles.status}>
                      <span
                        className={item.is_active ? styles.statusActive : styles.statusInactive}
                      >
                        {item.is_active ? "Active" : "Inactive"}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : null}
          {query.isSuccess ? (
            <p className={styles.results}>{plural(query.data.total, "item")}</p>
          ) : null}
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
