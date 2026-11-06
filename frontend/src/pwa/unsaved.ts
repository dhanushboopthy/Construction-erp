import { useEffect } from "react";

/**
 * Forms with changes not yet saved (Milestone 29). "Update now" asks here first and does not
 * reload while any is open, so a bill being keyed is never lost to an update. Closing or
 * reloading the tab asks the browser's own "Leave site?" question too.
 */
const open = new Set<symbol>();

export function hasUnsavedChanges(): boolean {
  return open.size > 0;
}

/** Call in a form with `dirty` true while it holds changes not yet saved. */
export function useUnsavedChanges(dirty: boolean): void {
  useEffect(() => {
    if (!dirty) return;
    const token = Symbol("unsaved form");
    open.add(token);
    const warn = (event: BeforeUnloadEvent) => event.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => {
      open.delete(token);
      window.removeEventListener("beforeunload", warn);
    };
  }, [dirty]);
}
