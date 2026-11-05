"""Bill designs for the Milestone 28 tests: a design that prints every field of a slot, so it
passes the GST checks, and ways to break it."""

from app.domain.bill_template import fields_for

PAGE = "<style>@page { size: A4; margin: 8mm } td { border: 1px solid #000 }</style>"


def design(
    slot: str,
    *,
    marker: str = "DESIGN",
    drop: tuple[str, ...] = (),
    head: str = "",
    body: str = "",
) -> str:
    """Every field of the slot once, the item and HSN rows as table rows, then `body`."""
    singles, items, hsn = [], [], []
    for field in fields_for(slot):
        if field.key in drop:
            continue
        if field.image:
            singles.append(f'<img src="{{{{{field.key}}}}}" alt="{field.key}">')
        elif field.key.startswith("item."):
            items.append(f"<td>{{{{{field.key}}}}}</td>")
        elif field.key.startswith("hsn."):
            hsn.append(f"<td>{{{{{field.key}}}}}</td>")
        else:
            singles.append(f"<div>{{{{{field.key}}}}}</div>")
    return (
        f"<!doctype html><html><head><meta charset=utf-8><title>{marker}</title>{PAGE}{head}"
        f"</head><body><p>{marker}</p>{''.join(singles)}"
        f"<table><tr>{''.join(items)}</tr></table>"
        f"<table><tr>{''.join(hsn)}</tr></table>{body}</body></html>"
    )
