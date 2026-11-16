from collections.abc import Awaitable, Callable, Sequence

from discord import ButtonStyle, Interaction, SelectOption

from core.enums.language import SupportedLanguage
from features.misc.builder.interactive.draft import ItemDraft
from features.misc.builder.interactive.messages import common, screen
from features.misc.builder.interactive.render import NO_OPTIONS, preview_component
from features.misc.builder.interactive.screens.controls import Callback, back_button, button, dropdown, preview
from features.misc.builder.interactive.screens.host import Host
from features.misc.builder.interactive.screens.spec import Screen

Place = Callable[[Interaction, str], Awaitable[None]]
"""Puts the element in the place with the given value - or takes it out of the message again."""


def add_confirmation(page: Screen, language: SupportedLanguage, on_place: Place, new_row: str, on_no: Callback) -> None:
    """While nothing is placed there is nothing to choose from: ask only whether to place the element in a row of its own
    (`new_row` is the value of that place)."""

    async def on_yes(interaction: Interaction) -> None:
        """Place the element in a row of its own."""
        await on_place(interaction, new_row)

    page.add(0, button("yes", on_yes, label=common(language, "buttons.yes"), style=ButtonStyle.green, emoji="✅"))
    page.add(0, button("no", on_no, label=common(language, "buttons.no"), style=ButtonStyle.red, emoji="🛑"))


def add_back(page: Screen, host: Host) -> None:
    """The button back to the overview of the elements."""

    async def on_back(interaction: Interaction) -> None:
        """Go back to the item list."""
        await host.hub(interaction)

    page.add(0, back_button(host.session.language, on_back))


def add_row_movers(page: Screen, host: Host, item_id: int, neighbours: Sequence[int], move: Callable[[int], object]) -> None:
    """Two buttons in a row can swap places: the buttons that move the element along its row, one place at a time.
    `neighbours` are the elements of its row and `move` moves it by the given number of places."""
    if len(neighbours) < 2:
        return

    language = host.session.language
    position = neighbours.index(item_id)

    def mover(offset: int) -> Callback:
        """The callback that moves the element `offset` places along its row and shows the screen again."""

        async def go(interaction: Interaction) -> None:
            """Move the element along its row."""
            move(offset)
            await host.placement(interaction, item_id)

        return go

    page.add(
        0,
        button(
            "left",
            mover(-1),
            label=common(language, "buttons.left"),
            style=ButtonStyle.blurple,
            emoji="⬅️",
            disabled=position == 0,
        ),
    )
    page.add(
        0,
        button(
            "right",
            mover(1),
            label=common(language, "buttons.right"),
            style=ButtonStyle.blurple,
            emoji="➡️",
            disabled=position == len(neighbours) - 1,
        ),
    )


def add_target_dropdown(page: Screen, language: SupportedLanguage, options: list[SelectOption], on_place: Place) -> None:
    """The dropdown with the places the element can go."""

    async def on_select(interaction: Interaction, values: list[str]) -> None:
        """Put the element in the chosen place."""
        if values[0] != NO_OPTIONS:
            await on_place(interaction, values[0])

    page.add(
        1,
        dropdown(
            "target",
            on_select,
            options=options,
            placeholder=screen(language, "placeholders.placement_target" if options else "placeholders.placement_empty"),
            disabled=not options,
        ),
    )


def add_previews(page: Screen, rows: Sequence[Sequence[ItemDraft]], limit: int) -> None:
    """The placed elements as the message shows them - at most `limit` rows, one row of controls each, below the dropdown.
    They are disabled, as they are only a preview."""
    for offset, row in enumerate(rows[:limit]):
        for placed in row:
            page.add(2 + offset, preview(f"preview:{placed.id}", preview_component(placed)))
