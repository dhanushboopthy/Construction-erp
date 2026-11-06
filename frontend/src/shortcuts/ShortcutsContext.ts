import { createContext, useContext, useEffect, useRef } from "react";

import type { ShortcutAction } from "./registry";

export interface ShortcutsState {
  /** What this user can give a shortcut to, with their defaults. */
  actions: ShortcutAction[];
  /** The shortcut each action has now: the user's own, else the default. */
  combos: Record<string, string>;
  /** What the user changed (action id to shortcut), as saved. */
  saved: Record<string, string>;
  loading: boolean;
  /** Save the user's changes, replacing the saved ones. Rejects with the server's message. */
  save: (changes: Record<string, string>) => Promise<void>;
  /** The editor turns the keys off while it listens for a new combination. */
  pause: (on: boolean) => void;
  /** A page tells the app what its "new" button does. Returns the way to take it back. */
  register: (id: string, handler: () => void) => () => void;
}

export const ShortcutsContext = createContext<ShortcutsState | null>(null);

export function useShortcuts(): ShortcutsState {
  const value = useContext(ShortcutsContext);
  if (!value) throw new Error("useShortcuts must be used inside <ShortcutsProvider>");
  return value;
}

/** The shortcut an action has now, for showing it ("Alt+2"), or undefined outside the app. */
export function useComboFor(id: string): string | undefined {
  return useContext(ShortcutsContext)?.combos[id];
}

/** Run `handler` when the user presses the shortcut they have for page action `id`. Does
 * nothing outside the signed-in app. */
export function useShortcut(id: string, handler: () => void): void {
  const state = useContext(ShortcutsContext);
  const latest = useRef(handler);
  useEffect(() => {
    latest.current = handler;
  });
  const register = state?.register;
  useEffect(() => register?.(id, () => latest.current()), [register, id]);
}
