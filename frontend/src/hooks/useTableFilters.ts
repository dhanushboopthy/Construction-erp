import { useCallback } from "react";
import { useSearchParams } from "react-router";

export interface TableFilters {
  q: string;
  status: string;
  from: string;
  to: string;
  /** Sets one filter; an empty value removes it from the URL. */
  set: (key: string, value: string) => void;
  /** Any other filter kept in the URL, e.g. `get("place")`. */
  get: (key: string) => string;
}

/**
 * The filters of a list, kept in the URL query (`?q=&status=&from=&to=`) so Back, reload and a
 * pasted link all show the same rows. Changing a filter replaces the history entry instead of
 * adding one per keystroke.
 */
export function useTableFilters(): TableFilters {
  const [params, setParams] = useSearchParams();
  const set = useCallback<TableFilters["set"]>(
    (key, value) => {
      setParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          if (value) next.set(key, value);
          else next.delete(key);
          return next;
        },
        { replace: true },
      );
    },
    [setParams],
  );
  return {
    q: params.get("q") ?? "",
    status: params.get("status") ?? "",
    from: params.get("from") ?? "",
    to: params.get("to") ?? "",
    set,
    get: (key) => params.get(key) ?? "",
  };
}
