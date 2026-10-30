import { Search } from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";

import type { TableFilters } from "@/hooks/useTableFilters";

import { SelectField, TextField } from "./Field";
import styles from "./TableToolbar.module.css";

export interface StatusOption {
  value: string;
  label: string;
}

/**
 * Search, an optional status filter and an optional date range above a list. The search box waits
 * for a pause in typing before it changes the URL; "/" jumps to it from anywhere on the screen.
 */
export function TableToolbar({
  filters,
  searchLabel = "Search",
  searchPlaceholder,
  statusLabel = "Status",
  allStatusesLabel = "All statuses",
  statusOptions,
  dateRange = false,
  extra,
  debounceMs = 300,
}: {
  filters: TableFilters;
  searchLabel?: string;
  searchPlaceholder?: string;
  statusLabel?: string;
  allStatusesLabel?: string;
  statusOptions?: StatusOption[];
  dateRange?: boolean;
  /** More filters of the screen, e.g. a place select; keep their value in the URL too. */
  extra?: ReactNode;
  debounceMs?: number;
}) {
  const { q, set } = filters;
  const [text, setText] = useState(q);
  const input = useRef<HTMLInputElement>(null);
  const written = useRef(q);

  // Back/forward or a pasted link changes the URL: follow it. (Not our own write, or typing
  // would be overwritten by the older value while the box is still being typed in.)
  useEffect(() => {
    if (q !== written.current) setText(q);
  }, [q]);

  // Typing: write to the URL after a pause.
  useEffect(() => {
    if (text === q) return;
    const timer = setTimeout(() => {
      written.current = text;
      set("q", text);
    }, debounceMs);
    return () => clearTimeout(timer);
  }, [text, q, set, debounceMs]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement).tagName;
      if (e.key === "/" && tag !== "INPUT" && tag !== "TEXTAREA" && tag !== "SELECT") {
        e.preventDefault();
        input.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <div className={styles.toolbar} role="search">
      <label className={styles.search}>
        <span className={styles.label}>{searchLabel}</span>
        <span className={styles.searchBox}>
          <Search size={18} aria-hidden="true" />
          <input
            ref={input}
            type="search"
            value={text}
            placeholder={searchPlaceholder}
            onChange={(e) => setText(e.target.value)}
          />
        </span>
      </label>
      {statusOptions ? (
        <SelectField
          label={statusLabel}
          value={filters.status}
          onChange={(e) => set("status", e.target.value)}
        >
          <option value="">{allStatusesLabel}</option>
          {statusOptions.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </SelectField>
      ) : null}
      {extra}
      {dateRange ? (
        <>
          <TextField
            label="From"
            type="date"
            value={filters.from}
            onChange={(e) => set("from", e.target.value)}
          />
          <TextField
            label="To"
            type="date"
            value={filters.to}
            onChange={(e) => set("to", e.target.value)}
          />
        </>
      ) : null}
    </div>
  );
}
