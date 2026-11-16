from discord import SelectOption
from discord.ui import Button, Item, Select

from features.misc.builder.interactive.draft import ItemDraft
from features.misc.builder.interactive.runtime import InteractiveButton, InteractiveSelect

NO_OPTIONS: str = "__none__"
"""The value of the single "—" entry a dropdown without options shows: Discord needs at least one."""


def select_options(draft: ItemDraft) -> list[SelectOption]:
    """The options a dropdown shows. Each option's `value` is its key - what Discord reports back when it is used."""
    return [
        SelectOption(label=option.label, value=option.key, emoji=option.emoji, description=option.description)
        for option in draft.options
    ]


def preview_component(draft: ItemDraft) -> Item:
    """The button or dropdown as it looks in a builder preview. It is always disabled: a real one would find no stored
    item yet, and a preview is only there to be looked at."""
    if draft.is_link:
        return Button(label=draft.label, emoji=draft.emoji, url=draft.url, disabled=True)

    if draft.is_select:
        minimum, maximum = draft.selection_range()
        options = select_options(draft)
        return Select(
            options=options or [SelectOption(label="—", value=NO_OPTIONS)],
            placeholder=draft.placeholder,
            min_values=minimum if options else 1,
            max_values=maximum if options else 1,
            disabled=True,
        )

    return Button(label=draft.label, emoji=draft.emoji, style=draft.style, disabled=True)


def final_component(draft: ItemDraft) -> Item:
    """The button or dropdown for the message that is actually sent. Interactive ones need the id of their stored item."""
    if draft.is_link:
        return Button(label=draft.label, emoji=draft.emoji, url=draft.url)

    assert draft.db_id is not None, "an interactive item must be stored before it can be sent"
    if draft.is_select:
        minimum, maximum = draft.selection_range()
        return InteractiveSelect(
            draft.db_id,
            options=select_options(draft),
            placeholder=draft.placeholder,
            min_values=minimum,
            max_values=maximum,
        )
    return InteractiveButton(draft.db_id, label=draft.label, emoji=draft.emoji, style=draft.style)
