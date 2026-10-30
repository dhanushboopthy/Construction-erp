import { ChevronRight } from "lucide-react";
import type { ReactNode } from "react";

import { moveRowFocus } from "@/hooks/useKeys";

import { Avatar } from "./Avatar";
import { Button } from "./Button";
import styles from "./DataTable.module.css";

export interface Column<T> {
  id: string;
  header: string;
  cell: (row: T) => ReactNode;
  /** Money and quantities: right aligned, tabular figures. */
  numeric?: boolean;
}

/** The two-line first cell: the name (or title) over a quieter line, with an optional avatar. */
export function PrimaryCell({
  name,
  sub,
  avatar = false,
}: {
  name: string;
  sub?: ReactNode;
  avatar?: boolean;
}) {
  return (
    <span className={styles.primary}>
      {avatar ? <Avatar name={name} size={32} /> : null}
      <span className={styles.primaryText}>
        <span className={styles.name}>{name}</span>
        {sub ? <span className={styles.sub}>{sub}</span> : null}
      </span>
    </span>
  );
}

/**
 * The list pattern of every screen. Rows are 64 px with a two-line first cell, right-aligned
 * figures, a status column and a chevron. When `onOpen` is given the first cell is a button:
 * Up/Down move between rows, Enter opens, and the selected row carries the accent marker (the
 * "List + editor" pattern in docs/DESIGN.md). Loading, error and empty are drawn here.
 */
export function DataTable<T>({
  caption,
  columns,
  rows,
  rowKey,
  onOpen,
  selectedKey,
  loading = false,
  error,
  onRetry,
  empty,
  footer,
}: {
  /** Names the table for screen readers. */
  caption: string;
  columns: Column<T>[];
  rows: T[];
  rowKey: (row: T) => string | number;
  onOpen?: (row: T) => void;
  selectedKey?: string | number | null;
  loading?: boolean;
  error?: string | null;
  onRetry?: () => void;
  /** Shown when there are no rows. */
  empty: ReactNode;
  footer?: ReactNode;
}) {
  if (loading) {
    return (
      <div className={styles.wrap}>
        <p role="status" className={styles.message}>
          Loading…
        </p>
      </div>
    );
  }
  if (error) {
    return (
      <div className={styles.wrap}>
        <div role="alert" className={`${styles.message} ${styles.error}`}>
          <p>{error}</p>
          {onRetry ? <Button onClick={onRetry}>Try again</Button> : null}
        </div>
      </div>
    );
  }
  if (rows.length === 0) {
    return (
      <div className={styles.wrap}>
        <p className={styles.message}>{empty}</p>
      </div>
    );
  }
  return (
    <div className={styles.wrap}>
      <table className={styles.table} aria-label={caption}>
        <thead>
          <tr>
            {columns.map((c) => (
              <th key={c.id} scope="col" className={c.numeric ? styles.numeric : undefined}>
                {c.header}
              </th>
            ))}
            {onOpen ? <th scope="col" className={styles.chevronHead} aria-label="Open" /> : null}
          </tr>
        </thead>
        <tbody onKeyDown={moveRowFocus}>
          {rows.map((row) => {
            const key = rowKey(row);
            const selected = selectedKey != null && selectedKey === key;
            return (
              <tr
                key={key}
                className={[styles.row, selected ? styles.selected : "", onOpen ? styles.open : ""]
                  .filter(Boolean)
                  .join(" ")}
                onClick={onOpen ? () => onOpen(row) : undefined}
              >
                {columns.map((c, i) => (
                  <td key={c.id} className={c.numeric ? `${styles.numeric} num` : undefined}>
                    {i === 0 && onOpen ? (
                      <button
                        type="button"
                        className={styles.rowButton}
                        data-row={key}
                        aria-current={selected ? "true" : undefined}
                        onClick={(e) => {
                          e.stopPropagation();
                          onOpen(row);
                        }}
                      >
                        {c.cell(row)}
                      </button>
                    ) : (
                      c.cell(row)
                    )}
                  </td>
                ))}
                {onOpen ? (
                  <td className={styles.chevron}>
                    <ChevronRight size={18} aria-hidden="true" />
                  </td>
                ) : null}
              </tr>
            );
          })}
        </tbody>
      </table>
      {footer ? <div className={styles.footer}>{footer}</div> : null}
    </div>
  );
}
