import { useCallback, useEffect, useRef, useState, type RefObject } from "react";

/**
 * Open/close state for a small menu: closes on a click outside or Esc (focus goes back).
 * `ignore` lists other elements that open it (a second button), so clicking them is not "outside".
 */
export function usePopover<T extends HTMLElement = HTMLDivElement>(
  ignore: RefObject<HTMLElement | null>[] = [],
) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<T>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);

  const close = useCallback((refocus = false) => {
    setOpen(false);
    if (refocus) triggerRef.current?.focus();
  }, []);

  useEffect(() => {
    if (!open) return;
    const onPointer = (event: PointerEvent) => {
      const target = event.target as Node;
      if (rootRef.current?.contains(target)) return;
      if (ignore.some((ref) => ref.current?.contains(target))) return;
      close();
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") close(true);
    };
    document.addEventListener("pointerdown", onPointer);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onPointer);
      document.removeEventListener("keydown", onKey);
    };
    // `ignore` holds refs, which never change identity.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, close]);

  return { open, setOpen, toggle: () => setOpen((o) => !o), close, rootRef, triggerRef };
}

export type Popover = ReturnType<typeof usePopover<HTMLDivElement>>;
