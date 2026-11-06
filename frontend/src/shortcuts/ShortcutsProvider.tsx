import { useCallback, useEffect, useMemo, useRef, type ReactNode } from "react";
import { useNavigate } from "react-router";

import { useMyShortcuts, useSaveShortcuts } from "@/api/shortcuts";
import { useAuth } from "@/auth/AuthContext";

import { comboFromEvent, isEditorKey } from "./combo";
import { shortcutActionsFor } from "./registry";
import { ShortcutsContext, type ShortcutsState } from "./ShortcutsContext";

/**
 * The keyboard shortcuts of the signed-in user: the defaults, with whatever they changed on top
 * (saved on the server, so they follow the user to any device). One listener serves the whole
 * app: Alt+key jumps to a screen or presses the page's "new"; Ctrl+Shift+Alt+1 opens the editor
 * from anywhere.
 */
export function ShortcutsProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const navigate = useNavigate();
  const mine = useMyShortcuts(user !== null);
  const saveMutation = useSaveShortcuts();
  const handlers = useRef(new Map<string, () => void>());
  const paused = useRef(false);

  const role = user?.role;
  const actions = useMemo(() => (role ? shortcutActionsFor(role) : []), [role]);

  const saved = useMemo(() => {
    const known = new Set(actions.map((a) => a.id));
    const own: Record<string, string> = {};
    for (const item of mine.data?.items ?? []) {
      if (known.has(item.action_id)) own[item.action_id] = item.combo;
    }
    return own;
  }, [actions, mine.data]);

  const combos = useMemo(() => {
    const all: Record<string, string> = {};
    for (const a of actions) all[a.id] = saved[a.id] ?? a.default;
    return all;
  }, [actions, saved]);

  // Which action a key press runs. An action the user changed wins over one that still has the
  // same shortcut as its default, so a clash can never leave a default in charge.
  const byCombo = useMemo(() => {
    const map = new Map<string, string>();
    for (const a of actions) if (!(a.id in saved)) map.set(a.default, a.id);
    for (const [id, combo] of Object.entries(saved)) map.set(combo, id);
    return map;
  }, [actions, saved]);

  useEffect(() => {
    if (!user) return;
    const onKey = (event: KeyboardEvent) => {
      if (isEditorKey(event)) {
        event.preventDefault();
        void navigate("/shortcuts");
        return;
      }
      if (paused.current) return;
      const combo = comboFromEvent(event);
      const id = combo ? byCombo.get(combo) : undefined;
      if (!id) return;
      if (id.startsWith("go:")) {
        event.preventDefault();
        void navigate(id.slice(3));
        return;
      }
      const handler = handlers.current.get(id);
      if (handler) {
        event.preventDefault();
        handler();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [user, byCombo, navigate]);

  const register = useCallback((id: string, handler: () => void) => {
    handlers.current.set(id, handler);
    return () => {
      if (handlers.current.get(id) === handler) handlers.current.delete(id);
    };
  }, []);

  const pause = useCallback((on: boolean) => {
    paused.current = on;
  }, []);

  const save = useCallback(
    async (changes: Record<string, string>) => {
      const items = Object.entries(changes).map(([action_id, combo]) => ({ action_id, combo }));
      await saveMutation.mutateAsync(items);
    },
    [saveMutation],
  );

  const value = useMemo<ShortcutsState>(
    () => ({ actions, combos, saved, loading: mine.isLoading, save, pause, register }),
    [actions, combos, saved, mine.isLoading, save, pause, register],
  );
  return <ShortcutsContext.Provider value={value}>{children}</ShortcutsContext.Provider>;
}
