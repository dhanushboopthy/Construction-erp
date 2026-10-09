import { useEffect, type KeyboardEvent } from "react";

/** Alt + a letter runs `handler` (e.g. Alt+N for "new"). Uses the physical key so it also
 * works on keyboards where Alt changes the character. */
export function useAltKey(letter: string, handler: () => void): void {
  useEffect(() => {
    const code = `Key${letter.toUpperCase()}`;
    const onKey = (event: globalThis.KeyboardEvent) => {
      if (event.altKey && !event.ctrlKey && !event.metaKey && event.code === code) {
        event.preventDefault();
        handler();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [letter, handler]);
}

/** Up and Down arrows move focus between the row buttons of a list (`[data-row]`). */
export function moveRowFocus(event: KeyboardEvent<HTMLElement>): void {
  if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
  const rows = Array.from(event.currentTarget.querySelectorAll<HTMLElement>("[data-row]"));
  const index = rows.indexOf(document.activeElement as HTMLElement);
  const next = event.key === "ArrowDown" ? index + 1 : index - 1;
  const target = rows[Math.max(0, Math.min(rows.length - 1, next))];
  if (target) {
    event.preventDefault();
    target.focus();
  }
}
