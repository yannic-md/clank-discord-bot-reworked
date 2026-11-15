from collections.abc import Awaitable, Callable

from discord import ButtonStyle, Interaction, Role, SelectOption
from discord.app_commands import AppCommandChannel, AppCommandThread
from discord.ui import Button, ChannelSelect, Item, RoleSelect, Select

from core.enums.language import SupportedLanguage
from features.misc.builder.interactive.messages import common, screen
from features.misc.builder.interactive.messages import t as shared_t
from features.misc.builder.interactive.render import NO_OPTIONS
from features.misc.builder.interactive.screens.spec import Control

Callback = Callable[[Interaction], Awaitable[None]]
"""What happens when a button is pressed."""
ValuesCallback = Callable[[Interaction, list[str]], Awaitable[None]]
"""What happens when a dropdown is used - with the values of the chosen options."""
RolesCallback = Callable[[Interaction, list[Role]], Awaitable[None]]
"""What happens when a role picker is used - with the roles that were picked."""
ChannelsCallback = Callable[[Interaction, list[AppCommandChannel | AppCommandThread]], Awaitable[None]]
"""What happens when a channel picker is used - with the channels that were picked."""


def _on_use(item: Item, callback: Callback) -> None:
    """Make `callback` run when `item` is used."""
    item.callback = callback  # type: ignore[method-assign,assignment]


def button(
    name: str,
    callback: Callback,
    *,
    label: str,
    style: ButtonStyle,
    emoji: str,
    disabled: bool = False,
) -> Control:
    """A button that runs `callback`."""
    item: Button = Button(label=label, style=style, emoji=emoji, disabled=disabled)
    _on_use(item, callback)
    return Control(name, item)


def dropdown(
    name: str,
    callback: ValuesCallback,
    *,
    options: list[SelectOption],
    placeholder: str,
    disabled: bool = False,
) -> Control:
    """A dropdown that runs `callback` with the values of the chosen options. Without options it shows a single "—"
    entry, as Discord does not accept a dropdown with none."""
    item: Select = Select(
        options=options or [SelectOption(label="—", value=NO_OPTIONS)], placeholder=placeholder, disabled=disabled
    )

    async def on_use(interaction: Interaction) -> None:
        """Hand over what was chosen."""
        await callback(interaction, item.values)

    _on_use(item, on_use)
    return Control(name, item)


def role_picker(name: str, item: RoleSelect, callback: RolesCallback) -> Control:
    """A role picker (made elsewhere, as it starts out with a choice) that runs `callback` with the roles picked."""

    async def on_use(interaction: Interaction) -> None:
        """Hand over what was picked."""
        await callback(interaction, item.values)

    _on_use(item, on_use)
    return Control(name, item)


def channel_picker(name: str, item: ChannelSelect, callback: ChannelsCallback) -> Control:
    """A channel picker (made elsewhere, as it starts out with a choice) that runs `callback` with the channels
    picked."""

    async def on_use(interaction: Interaction) -> None:
        """Hand over what was picked."""
        await callback(interaction, item.values)

    _on_use(item, on_use)
    return Control(name, item)


def preview(name: str, item: Item) -> Control:
    """A part of a preview of the message being built - a disabled button or dropdown that is only there to be looked at."""
    return Control(name, item)


def back_button(language: SupportedLanguage, callback: Callback) -> Control:
    """The button that goes back to the screen before."""
    return button("back", callback, label=common(language, "buttons.back"), style=ButtonStyle.gray, emoji="◀️")


def add_button(label: str, callback: Callback, *, name: str = "add", disabled: bool = False) -> Control:
    """The green button that adds something."""
    return button(name, callback, label=label, style=ButtonStyle.green, emoji="➕", disabled=disabled)


def edit_button(language: SupportedLanguage, callback: Callback, *, disabled: bool = False) -> Control:
    """The button that changes the selected entry of a list."""
    return button(
        "edit", callback, label=screen(language, "buttons.edit"), style=ButtonStyle.blurple, emoji="✏️", disabled=disabled
    )


def delete_button(language: SupportedLanguage, callback: Callback, *, disabled: bool = False) -> Control:
    """The red button that deletes the selected entry of a list."""
    return button(
        "delete", callback, label=screen(language, "buttons.delete"), style=ButtonStyle.red, emoji="🗑️", disabled=disabled
    )


def up_button(language: SupportedLanguage, callback: Callback, *, disabled: bool = False) -> Control:
    """The button that moves the selected entry of a list up."""
    return button(
        "up", callback, label=common(language, "buttons.up"), style=ButtonStyle.blurple, emoji="⬆️", disabled=disabled
    )


def down_button(language: SupportedLanguage, callback: Callback, *, disabled: bool = False) -> Control:
    """The button that moves the selected entry of a list down."""
    return button(
        "down", callback, label=common(language, "buttons.down"), style=ButtonStyle.blurple, emoji="⬇️", disabled=disabled
    )


def look_button(language: SupportedLanguage, callback: Callback) -> Control:
    """The button that changes how an element looks."""
    return button("look", callback, label=screen(language, "buttons.look"), style=ButtonStyle.blurple, emoji="✏️")


def actions_button(language: SupportedLanguage, callback: Callback) -> Control:
    """The button that opens the list of the actions."""
    return button("actions", callback, label=screen(language, "buttons.actions"), style=ButtonStyle.gray, emoji="⚙️")


def conditions_button(language: SupportedLanguage, callback: Callback) -> Control:
    """The button that opens the list of the restrictions."""
    return button("conditions", callback, label=screen(language, "buttons.conditions"), style=ButtonStyle.gray, emoji="🔒")


def save_button(language: SupportedLanguage, callback: Callback) -> Control:
    """The button that stores the action being edited."""
    return button("save", callback, label=shared_t(language, "action_screen.save"), style=ButtonStyle.green, emoji="💾")
