import { CornerDownLeft, Search } from "lucide-react";
import { useEffect, useId, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { useNavigate } from "react-router";

import { actionsFor } from "@/actions";
import type { Role } from "@/api/types";
import { modulesFor } from "@/modules";

import styles from "./CommandSearch.module.css";
import { iconFor } from "./moduleIcons";

interface Entry {
  id: string;
  group: "Actions" | "Go to";
  label: string;
  hint: string;
  path: string;
  icon: ReturnType<typeof iconFor>;
  text: string;
}

/** Search box that doubles as a command palette: Ctrl+K or / to focus, arrows, Enter to go. */
export function CommandSearch({ role }: { role: Role }) {
  const navigate = useNavigate();
  const listId = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const rootRef = useRef<HTMLDivElement>(null);
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);

  const entries = useMemo<Entry[]>(() => {
    const actions = actionsFor(role).map((a) => ({
      id: `action-${a.id}`,
      group: "Actions" as const,
      label: a.label,
      hint: a.hint,
      path: a.path,
      icon: a.icon,
      text: `${a.label} ${a.hint} ${a.keywords ?? ""}`.toLowerCase(),
    }));
    const screens = modulesFor(role).map((m) => ({
      id: `go-${m.path}`,
      group: "Go to" as const,
      label: m.label,
      hint: m.purpose,
      path: m.path,
      icon: iconFor(m.path),
      text: `${m.label} ${m.purpose}`.toLowerCase(),
    }));
    return [...actions, ...screens];
  }, [role]);

  const results = useMemo(() => {
    const words = query.toLowerCase().split(/\s+/).filter(Boolean);
    return entries.filter((e) => words.every((w) => e.text.includes(w))).slice(0, 9);
  }, [entries, query]);

  // Ctrl+K / Cmd+K anywhere, or "/" when not typing in a field.
  useEffect(() => {
    const onKey = (event: globalThis.KeyboardEvent) => {
      const typing = (event.target as HTMLElement | null)?.closest("input, textarea, select");
      if (
        (event.key === "k" && (event.ctrlKey || event.metaKey)) ||
        (event.key === "/" && !typing)
      ) {
        event.preventDefault();
        inputRef.current?.focus();
        setOpen(true);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    if (!open) return;
    const onPointer = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("pointerdown", onPointer);
    return () => document.removeEventListener("pointerdown", onPointer);
  }, [open]);

  function go(entry: Entry | undefined) {
    if (!entry) return;
    setOpen(false);
    setQuery("");
    inputRef.current?.blur();
    void navigate(entry.path);
  }

  function onKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setOpen(true);
      setActive((i) => (results.length ? (i + 1) % results.length : 0));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActive((i) => (results.length ? (i - 1 + results.length) % results.length : 0));
    } else if (event.key === "Enter") {
      event.preventDefault();
      go(results[active]);
    } else if (event.key === "Escape") {
      setOpen(false);
      setQuery("");
      inputRef.current?.blur();
    }
  }

  const showList = open && results.length > 0;
  const activeId = showList ? `${listId}-${active}` : undefined;
  let lastGroup = "";

  return (
    <div className={styles.root} ref={rootRef}>
      <Search className={styles.icon} size={18} strokeWidth={2} aria-hidden="true" />
      <input
        ref={inputRef}
        className={styles.input}
        type="search"
        role="combobox"
        aria-label="Search screens and actions"
        aria-expanded={showList}
        aria-controls={listId}
        aria-activedescendant={activeId}
        aria-autocomplete="list"
        placeholder="Search screens and actions…"
        value={query}
        onChange={(e) => {
          setQuery(e.target.value);
          setActive(0);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={onKeyDown}
      />
      <kbd className={styles.hint} aria-hidden="true">
        Ctrl K
      </kbd>
      {open && query && results.length === 0 ? (
        <div className={styles.panel} role="status">
          <p className={styles.empty}>Nothing matches “{query}”. Try a screen name or “bill”.</p>
        </div>
      ) : null}
      <ul
        id={listId}
        role="listbox"
        aria-label="Results"
        className={styles.panel}
        hidden={!showList}
      >
        {results.map((entry, i) => {
          const Icon = entry.icon;
          const heading = entry.group !== lastGroup ? entry.group : null;
          lastGroup = entry.group;
          return (
            <li
              key={entry.id}
              id={`${listId}-${i}`}
              role="option"
              aria-selected={i === active}
              className={styles.option}
              data-heading={heading ?? undefined}
              onPointerEnter={() => setActive(i)}
              onPointerDown={(e) => e.preventDefault()}
              onClick={() => go(entry)}
            >
              <span className={styles.optionIcon} aria-hidden="true">
                <Icon size={16} strokeWidth={2} />
              </span>
              <span className={styles.optionText}>
                <span className={styles.optionLabel}>{entry.label}</span>
                <span className={styles.optionHint}>{entry.hint}</span>
              </span>
              <CornerDownLeft className={styles.enter} size={14} aria-hidden="true" />
            </li>
          );
        })}
      </ul>
    </div>
  );
}
