from pydantic import Field

from app.schemas.common import Schema


class ShortcutItem(Schema):
    action_id: str = Field(min_length=1, max_length=60, description='e.g. "go:/items" or "new"')
    combo: str = Field(min_length=1, max_length=40, description='e.g. "Alt+N" or "Alt+Shift+7"')


class ShortcutsIn(Schema):
    items: list[ShortcutItem] = Field(
        max_length=100, description="Everything the user changed; actions left out use the default"
    )


class ShortcutsOut(Schema):
    items: list[ShortcutItem]
