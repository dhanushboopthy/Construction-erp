import type { Role } from "@/api/types";
import { modulesFor } from "@/modules";

/**
 * Everything a user can give a shortcut to, with its default. The server stores only what a
 * user changed, so adding an action here, or changing a default, reaches everyone who has not
 * touched it.
 */
export interface ShortcutAction {
  /** "go:/items" jumps to a screen; "new" is the current page's "new" button. */
  id: string;
  label: string;
  group: "Go to a screen" | "On the current page";
  hint?: string;
  default: string;
}

/** What a page can do when its shortcut is pressed. A page registers the one it has. */
export const PAGE_ACTIONS: ShortcutAction[] = [
  {
    id: "new",
    label: "New record",
    group: "On the current page",
    hint: "Opens the form to add something on the page you are on (a bill, an item, a party…)",
    default: "Alt+N",
  },
];

export const goId = (path: string) => `go:${path}`;

/** The actions this role has: a jump to each screen it can open, and the page actions. */
export function shortcutActionsFor(role: Role): ShortcutAction[] {
  const screens = modulesFor(role).map<ShortcutAction>((m) => ({
    id: goId(m.path),
    label: m.label,
    group: "Go to a screen",
    hint: m.purpose,
    default: `Alt+${m.shortcut.toUpperCase()}`,
  }));
  return [...screens, ...PAGE_ACTIONS];
}
