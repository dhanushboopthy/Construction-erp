"""Keyboard shortcuts a user may set for themselves.

A shortcut is Alt, optionally Shift, and one letter or digit: "Alt+N", "Alt+Shift+7". Ctrl and
Meta are never allowed, so typing in a field (or the browser's own Ctrl shortcuts) never fires
one, and the key that opens the shortcut editor (Ctrl+Shift+Alt+1) can never be taken.

Which action each shortcut runs is the frontend's list (modules and page actions); the server
stores only what a user changed and checks the combinations. Pure functions: no DB, no HTTP.
"""

import re
from collections.abc import Iterable

# Combinations the browser or the desktop uses (Alt+D the address bar, Alt+F and Alt+E the menu).
# They are refused because the page often never sees them.
RESERVED = frozenset({"Alt+D", "Alt+F", "Alt+E"})

_KEY = re.compile(r"^[A-Z0-9]$")
_ACTION = re.compile(r"^[a-z0-9][a-z0-9_.:/-]{0,59}$")


class ShortcutError(ValueError):
    """A shortcut that cannot be saved. `field` names the offending action id when known."""

    def __init__(self, message: str, field: str | None = None) -> None:
        super().__init__(message)
        self.field = field


def normalise(combo: str) -> str:
    """The stored form of a combination: "alt + shift + n" becomes "Alt+Shift+N".

    Raises ShortcutError for anything that is not Alt (+ Shift) + one letter or digit, and for
    the combinations in RESERVED."""
    parts = [p.strip() for p in str(combo).split("+")]
    if len(parts) < 2 or any(not p for p in parts):
        raise ShortcutError("Use Alt plus a letter or a digit, for example Alt+N")
    *modifiers, key = parts
    lowered = [m.lower() for m in modifiers]
    if "alt" not in lowered:
        raise ShortcutError("A shortcut has to include Alt")
    if any(m not in {"alt", "shift"} for m in lowered) or len(set(lowered)) != len(lowered):
        raise ShortcutError("Only Alt and Shift can go with the key")
    key = key.upper()
    if not _KEY.match(key):
        raise ShortcutError("The key has to be one letter or one digit")
    canonical = "Alt+" + ("Shift+" if "shift" in lowered else "") + key
    if canonical in RESERVED:
        raise ShortcutError(f"{canonical} is used by the browser. Choose another")
    return canonical


def validate_set(items: Iterable[tuple[str, str]]) -> list[tuple[str, str]]:
    """Check a user's whole set of changes and return it with canonical combinations.

    Each item is (action id, combination). An action appears once and a combination runs one
    action. The defaults live in the frontend, so a clash with a default is checked there."""
    checked: list[tuple[str, str]] = []
    actions: set[str] = set()
    combos: dict[str, str] = {}
    for action, combo in items:
        if not _ACTION.match(action):
            raise ShortcutError("Unknown action", field=action)
        if action in actions:
            raise ShortcutError("An action can have only one shortcut", field=action)
        try:
            canonical = normalise(combo)
        except ShortcutError as error:
            raise ShortcutError(str(error), field=action) from None
        if canonical in combos:
            raise ShortcutError(
                f"{canonical} is already used by another action ({combos[canonical]})",
                field=action,
            )
        actions.add(action)
        combos[canonical] = action
        checked.append((action, canonical))
    return checked
