/**
 * Keyboard shortcuts as text. A shortcut is Alt, optionally Shift, and one letter or digit:
 * "Alt+N", "Alt+Shift+7". The same rules as the server (`app/domain/shortcuts.py`), which checks
 * them again on save. Ctrl and Meta are never part of one, so typing in a field and the
 * browser's own Ctrl shortcuts are left alone, and the editor's key (Ctrl+Shift+Alt+1) can never
 * be taken.
 */

/** What the browser or the desktop takes before the page sees it. */
const RESERVED = new Set(["Alt+D", "Alt+F", "Alt+E"]);

/** Why `raw` cannot be a shortcut, or null when it can. */
export function whyNot(raw: string): string | null {
  const parts = raw.split("+").map((p) => p.trim());
  if (parts.length < 2 || parts.some((p) => p === "")) {
    return "Use Alt plus a letter or a digit, for example Alt+N";
  }
  const key = (parts.at(-1) ?? "").toUpperCase();
  const modifiers = parts.slice(0, -1).map((m) => m.toLowerCase());
  if (!modifiers.includes("alt")) return "A shortcut has to include Alt";
  if (
    modifiers.some((m) => m !== "alt" && m !== "shift") ||
    new Set(modifiers).size !== modifiers.length
  ) {
    return "Only Alt and Shift can go with the key";
  }
  if (!/^[A-Z0-9]$/.test(key)) return "The key has to be one letter or one digit";
  const canonical = canonicalOf(modifiers, key);
  if (RESERVED.has(canonical)) return `${canonical} is used by the browser. Choose another`;
  return null;
}

function canonicalOf(modifiers: string[], key: string): string {
  return `Alt+${modifiers.includes("shift") ? "Shift+" : ""}${key}`;
}

/** The stored form ("alt + shift + n" is "Alt+Shift+N"), or null when it is not a valid shortcut. */
export function normaliseCombo(raw: string): string | null {
  if (whyNot(raw) !== null) return null;
  const parts = raw.split("+").map((p) => p.trim());
  return canonicalOf(
    parts.slice(0, -1).map((m) => m.toLowerCase()),
    (parts.at(-1) ?? "").toUpperCase(),
  );
}

export interface KeyLike {
  altKey: boolean;
  ctrlKey: boolean;
  metaKey: boolean;
  shiftKey: boolean;
  code?: string;
  key: string;
}

/** The key part of a press: from the physical key, so Alt does not change it on keyboards where
 * Alt types another character; the typed key is the fallback. */
function keyOf(event: Pick<KeyLike, "code" | "key">): string | null {
  const code = event.code ?? "";
  const letter = /^Key([A-Z])$/.exec(code);
  if (letter?.[1]) return letter[1];
  const digit = /^(?:Digit|Numpad)([0-9])$/.exec(code);
  if (digit?.[1]) return digit[1];
  return /^[a-z0-9]$/i.test(event.key) ? event.key.toUpperCase() : null;
}

/** The shortcut a key press makes ("Alt+Shift+N"), or null when it is not an Alt shortcut. */
export function comboFromEvent(event: KeyLike): string | null {
  if (!event.altKey || event.ctrlKey || event.metaKey) return null;
  const key = keyOf(event);
  return key ? `Alt+${event.shiftKey ? "Shift+" : ""}${key}` : null;
}

/** Ctrl+Shift+Alt+1, the key that opens the shortcut editor from anywhere. */
export function isEditorKey(event: KeyLike): boolean {
  return (
    event.ctrlKey &&
    event.shiftKey &&
    event.altKey &&
    !event.metaKey &&
    (event.code === "Digit1" || event.code === "Numpad1" || event.key === "1" || event.key === "!")
  );
}

/** "Alt+Shift+N" as separate keys for display: ["Alt", "Shift", "N"]. */
export function keysOf(combo: string): string[] {
  return combo.split("+");
}

/** The first action in `combos` (action id to shortcut) that already uses `combo`, other than
 * `except`. */
export function usedBy(
  combos: Record<string, string>,
  combo: string,
  except: string,
): string | undefined {
  return Object.keys(combos).find((id) => id !== except && combos[id] === combo);
}
