"""Company data management rules (Milestone 26, ADR 0013): which kinds a request names, what
blocks it, the order, and the typed confirmations. Pure: the catalogue itself (tables, columns)
lives in `services/platform/data_catalogue.py`."""

from collections.abc import Collection, Mapping, Sequence

CONFIRM_DELETE = "DELETE"
ALL_KEY = "all"


class DataError(ValueError):
    def __init__(self, message: str, code: str) -> None:
        super().__init__(message)
        self.code = code


def resolve(keys: Sequence[str] | str, order: Sequence[str]) -> list[str]:
    """The kinds a request names, once each, in catalogue order. An unknown key is refused: a
    typo must never turn "parties and items" into "parties"."""
    wanted = [keys] if isinstance(keys, str) else list(keys)
    if not wanted:
        raise DataError("Choose at least one kind of data.", "NOTHING_SELECTED")
    if ALL_KEY in wanted:
        if len(wanted) > 1:
            raise DataError("'all' cannot be combined with other kinds.", "UNKNOWN_DATA_KIND")
        return list(order)
    unknown = [k for k in wanted if k not in order]
    if unknown:
        raise DataError("Unknown kind of data: " + ", ".join(unknown), "UNKNOWN_DATA_KIND")
    return [k for k in order if k in wanted]


def unselected_blockers(
    selection: Collection[str], blockers: Mapping[str, Mapping[str, int]]
) -> dict[str, dict[str, int]]:
    """For each selected kind, the kinds still holding rows that point at it and that are not
    part of the selection."""
    found: dict[str, dict[str, int]] = {}
    for kind in selection:
        left = {k: n for k, n in blockers.get(kind, {}).items() if n > 0 and k not in selection}
        if left:
            found[kind] = left
    return found


def blocked_message(found: Mapping[str, Mapping[str, int]], labels: Mapping[str, str]) -> str:
    return " ".join(
        f"{labels[kind]} is blocked by "
        + ", ".join(f"{count} {labels[by]}" for by, count in by_kind.items())
        + "."
        for kind, by_kind in found.items()
    )


def selected_confirmation_ok(typed: str | None) -> bool:
    return typed == CONFIRM_DELETE


def all_confirmation_ok(
    typed: str | None, company_name: str | None, actual_name: str, acknowledged: bool
) -> bool:
    """The word, the company's exact name and the tick-box, compared case-sensitively."""
    return typed == CONFIRM_DELETE and company_name == actual_name and acknowledged is True


def order_is_valid(order: Sequence[str], blocked_by: Mapping[str, Collection[str]]) -> bool:
    """Every kind appears once, and each comes after every kind that blocks it."""
    if sorted(order) != sorted(blocked_by) or len(set(order)) != len(order):
        return False
    position = {k: i for i, k in enumerate(order)}
    return all(position[b] < position[k] for k, by in blocked_by.items() for b in by)
