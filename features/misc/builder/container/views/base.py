"""Common base of every screen of the container builder, plus its small UI helpers."""

import contextlib
from collections.abc import Callable, Coroutine
from typing import Any

from discord import ButtonStyle, Colour, HTTPException, Interaction, Message, NotFound, SelectOption
from discord.ui import ActionRow, Button, Container, Item, LayoutView, Select, TextDisplay

from core.discord_api.limits import MAX_V2_TOTAL_COMPONENTS
from core.setup.errors import error_handler
from features.misc.builder.container.models import ComponentKind, ComponentNode
from features.misc.builder.container.session import ContainerBuilderSession
from features.misc.builder.container.util.tree import find_parent
from features.misc.builder.session import BUILDER_VIEW_TIMEOUT

ItemCallback = Callable[[Interaction], Coroutine[Any, Any, Any]]


class BuilderLayoutView(LayoutView):
    """Base class of every container-builder screen: a layout view that disables its controls on timeout."""

    message: Message | None = None
    session: ContainerBuilderSession

    def __init__(self) -> None:
        """Create the view with the shared builder timeout."""
        super().__init__(timeout=BUILDER_VIEW_TIMEOUT)
        self.overflow_notes: list[str] = []
        """Status texts that no longer fit into the 40-component budget of this screen (a message with the
        maximum number of components leaves no room for an extra box) - `show` sends them as separate,
        ephemeral follow-up messages instead."""

    async def on_timeout(self) -> None:
        """Disable all buttons and selects of the sent message once the view expires."""
        if self.message is None:
            return

        for child in self.walk_children():
            if isinstance(child, (Button, Select)):
                child.disabled = True

        with contextlib.suppress(HTTPException, NotFound):
            await self.message.edit(view=self)

    def add_status(self, box: Container) -> None:
        """Show `box` directly above the first row of buttons/dropdowns, so errors and
        status messages sit in the same place on every screen. If the screen has no room left
        for it (Discord allows 40 components per message), its text becomes a follow-up message."""
        if self._total_children + box._total_count > MAX_V2_TOTAL_COMPONENTS:
            texts = [child.content for child in box.children if isinstance(child, TextDisplay)]
            self.overflow_notes.append("\n".join(texts))
            return

        rows = [child for child in self.children if isinstance(child, ActionRow)]
        for row in rows:
            self.remove_item(row)
        self.add_item(box)
        for row in rows:
            self.add_item(row)

    def add_error(self, message: str) -> None:
        """Add an error box with `message` to the screen."""
        self.add_status(error_container(message))

    def add_item_top(self, item: Item, *, fallback: Callable[[], Item]) -> None:
        """Put `item` above everything already on the screen - or `fallback()` if `item` would push the
        screen over Discord's 40-component limit (e.g. the preview of a huge container next to the controls)."""
        others = self.children
        for child in others:
            self.remove_item(child)

        if self._total_children + item._total_count + sum(child._total_count for child in others) > MAX_V2_TOTAL_COMPONENTS:
            item = fallback()

        self.add_item(item)
        for child in others:
            self.add_item(child)

    async def on_error(self, interaction: Interaction, error: Exception, item: Item) -> None:
        """Forward unhandled errors to the central error handler."""
        await error_handler(interaction, error)  # type: ignore[arg-type]


async def show(interaction: Interaction, view: BuilderLayoutView) -> None:
    """Re-render the builder onto `view`, replacing whatever screen is currently shown."""
    track_active_view(view)
    await interaction.response.edit_message(view=view)
    view.message = await interaction.original_response()
    await send_overflow_notes(interaction, view)


async def send_overflow_notes(interaction: Interaction, view: BuilderLayoutView) -> None:
    """Send the status texts that did not fit onto the screen as ephemeral follow-up messages."""
    notes, view.overflow_notes = view.overflow_notes, []
    for note in notes:
        await interaction.followup.send(note, ephemeral=True)


def track_active_view(view: BuilderLayoutView) -> None:
    """Make `view` the session's active screen and stop the one it replaces."""
    session = view.session
    if session.active_view is not None and session.active_view is not view:
        assert isinstance(session.active_view, BuilderLayoutView)
        session.active_view.stop()
    session.active_view = view


def info_container(text: str) -> Container:
    """Blurple container showing `text`."""
    return Container(TextDisplay(text), accent_colour=Colour.blurple())


def empty_node_container(session: ContainerBuilderSession, node: ComponentNode, text: str) -> Container:
    """Info box shown in place of a node that has no visible content yet. It takes the colour the
    real thing will have: a container's own accent colour, or - for an empty child - its parent's."""
    parent = find_parent(session, node.id)
    if node.kind == ComponentKind.CONTAINER:
        colour = node.accent_colour
    elif parent is not None:
        colour = parent.accent_colour
    else:
        colour = Colour.blurple()
    return Container(TextDisplay(text), accent_colour=colour)


def error_container(message: str) -> Container:
    """Red container showing `message`."""
    return Container(TextDisplay(message), accent_colour=Colour.red())


def add_button(
    row: ActionRow,
    callback: ItemCallback,
    *,
    label: str | None = None,
    style: ButtonStyle = ButtonStyle.secondary,
    emoji: str | None = None,
    disabled: bool = False,
) -> Button:
    """Create a button that runs `callback`, add it to `row` and return it."""
    button_item: Button = Button(label=label, style=style, emoji=emoji, disabled=disabled)
    button_item.callback = callback  # type: ignore[assignment]
    row.add_item(button_item)
    return button_item


def add_select(
    row: ActionRow,
    callback: ItemCallback,
    *,
    options: list[SelectOption],
    placeholder: str | None = None,
    disabled: bool = False,
    min_values: int = 1,
    max_values: int = 1,
) -> Select:
    """Create a select that runs `callback`, add it to `row` and return it; no `options` yields a "—" placeholder."""
    select_item: Select = Select(
        options=options or [SelectOption(label="—", value="__none__")],
        placeholder=placeholder,
        disabled=disabled,
        min_values=min_values,
        max_values=max_values,
    )
    select_item.callback = callback  # type: ignore[assignment]
    row.add_item(select_item)
    return select_item
