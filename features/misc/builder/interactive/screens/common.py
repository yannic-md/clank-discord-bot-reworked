from collections.abc import Awaitable, Callable, Sequence
from typing import NamedTuple

from discord import Interaction, SelectOption

from features.misc.builder.interactive.draft import ItemDraft
from features.misc.builder.interactive.editor import BULLET, BULLET_ACTIVE
from features.misc.builder.interactive.models import Condition, ItemConfig
from features.misc.builder.interactive.screens.controls import Callback, dropdown
from features.misc.builder.interactive.screens.host import Host
from features.misc.builder.interactive.screens.spec import Control, EditorSession
from features.misc.builder.interactive.ui import scope_of


def clamp(index: int | None, length: int) -> int | None:
    """`index` limited to the valid positions of a list with `length` entries (`None` for an empty list)."""
    if length == 0:
        return None
    return min(max(index or 0, 0), length - 1)


def bullet(active: bool) -> str:
    """The bullet in front of an entry of a list: a different one marks the entry that is selected."""
    return BULLET_ACTIVE if active else BULLET


def list_body(description: str, heading: str, entries: Sequence[str]) -> str:
    """The text of a screen that lists things: its description and - if there are entries - the list below `heading`."""
    lines = [description]
    if entries:
        lines += ["", f"**{heading}:**"]
    lines.extend(entries)
    return "\n".join(lines)


def swap[T](entries: list[T], index: int, offset: int) -> None:
    """Let the entry at `index` and the one `offset` places further trade places."""
    target = index + offset
    entries[index], entries[target] = entries[target], entries[index]


def switch_dropdown(
    options: list[SelectOption], placeholder: str, on_switch: Callable[[Interaction, str], Awaitable[None]]
) -> Control:
    """The dropdown that selects another entry of a list; `on_switch` gets the value of the entry chosen."""

    async def on_use(interaction: Interaction, values: list[str]) -> None:
        """Select the entry that was chosen - there is nothing to choose while the list is empty."""
        if options:
            await on_switch(interaction, values[0])

    return dropdown("switch", on_use, options=options, placeholder=placeholder, disabled=not options)


class ItemScope(NamedTuple):
    """The element being edited and the config whose actions or restrictions are changed - the element's own, or that
    of one of its options (which inherits the restrictions of the dropdown)."""

    draft: ItemDraft
    config: ItemConfig
    inherited: list[Condition]


def item_scope(session: EditorSession, item_id: int, option_key: str | None) -> ItemScope:
    """The scope of an element (or of one of its options)."""
    draft = session.library.require(item_id)
    scope = scope_of(draft, option_key)
    assert scope is not None
    return ItemScope(draft, *scope)


def back_to_element(host: Host, draft: ItemDraft, item_id: int, option_key: str | None) -> Callback:
    """The callback of the "back" button of the lists of what an element does or who may use it: back to the form, to the
    option list, or to the overview of the elements."""

    async def on_back(interaction: Interaction) -> None:
        """Go back to the form, the option list, or the item list."""
        if draft.is_form:
            await host.form(interaction, item_id)
            return
        if option_key is not None:
            await host.options(interaction, item_id, active_key=option_key)
            return
        await host.hub(interaction)

    return on_back
