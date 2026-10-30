import { useState } from "react";
import { useSearchParams } from "react-router";

import { SelectField, TextField } from "@/components/Field";
import styles from "@/components/Ledger.module.css";

import { UsersView } from "../UsersView";

const STATES = [
  { value: "", label: "Any status" },
  { value: "active", label: "Active" },
  { value: "locked", label: "Locked out" },
  { value: "inactive", label: "Deactivated" },
];

export function UsersPage() {
  const [params, setParams] = useSearchParams();
  const [q, setQ] = useState(params.get("q") ?? "");
  const state = params.get("state") ?? "";

  const setFilter = (key: string, value: string) =>
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        if (value) next.set(key, value);
        else next.delete(key);
        return next;
      },
      { replace: true },
    );

  return (
    <section aria-labelledby="users-title" className={styles.page}>
      <div className={styles.toolbar}>
        <h1 id="users-title" className={styles.title}>
          Users
        </h1>
        <p className={styles.keys}>↑↓ move · Enter open · Esc close</p>
      </div>
      <form
        className={styles.filters}
        role="search"
        onSubmit={(e) => {
          e.preventDefault();
          setFilter("q", q.trim());
        }}
      >
        <div className={styles.search}>
          <TextField
            label="Search"
            type="search"
            placeholder="Name or username"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onBlur={() => setFilter("q", q.trim())}
          />
        </div>
        <SelectField
          label="Status"
          value={state}
          onChange={(e) => setFilter("state", e.target.value)}
        >
          {STATES.map((s) => (
            <option key={s.value} value={s.value}>
              {s.label}
            </option>
          ))}
        </SelectField>
      </form>
      <UsersView q={params.get("q") ?? ""} state={state} />
    </section>
  );
}
