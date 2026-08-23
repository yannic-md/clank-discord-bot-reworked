import logging
from logging import Logger
from typing import Any

from discord import HTTPException, Interaction, InteractionType
from discord.ui import Button, ChannelSelect, MentionableSelect, RoleSelect, Select, UserSelect, View

from core.enums.language import SupportedLanguage
from core.i18n.resolve import get_language
from core.i18n.translator import translate

logger: Logger = logging.getLogger("discord")
_warned_about_missing_view_store: bool = False

# `custom_id` prefixes for screens that want their message's content/embeds preserved.
_PRESERVE_MESSAGE_PREFIXES: tuple[str, ...] = ("embed_builder:",)


def _has_live_handler(interaction: Interaction) -> bool:
    """Check whether some registered `discord.ui.View` will actually handle `interaction`.

    Mirrors the exact lookup discord.py's own dispatcher (`ViewStore.dispatch_view`) already
    performs internally when the gateway event comes in: the view bound to this specific message
    first, falling back to a message-independent (persistent) registration. If neither matches,
    the interaction is guaranteed to otherwise be dropped silently.

    Reaches into discord.py's private view store rather than re-implementing persistence, so this
    stays correct automatically as views are added anywhere in the bot, now or in the future.
    """
    data: dict[str, Any] = interaction.data or {}  # type: ignore[assignment]
    custom_id = data.get("custom_id")
    component_type = data.get("component_type")
    if custom_id is None or component_type is None:
        return True

    try:
        # noinspection PyProtectedMember
        views_by_message = interaction.client._connection._view_store._views
    except AttributeError:
        global _warned_about_missing_view_store

        if not _warned_about_missing_view_store:
            logger.error("Could not inspect discord.py's view store - skipping dead-interaction check.")
            _warned_about_missing_view_store = True
        return True

    message_id: int | None = interaction.message.id if interaction.message is not None else None
    key = (component_type, custom_id)

    if message_id is not None and key in views_by_message.get(message_id, {}):
        return True

    return key in views_by_message.get(None, {})


async def _replace_message(interaction: Interaction, message: str) -> None:
    """Default handling: overwrite the dead message with the error and drop its view entirely."""
    try:
        await interaction.response.edit_message(content=message, embeds=[], view=None)
    except HTTPException:
        # The interaction likely expired or was already acknowledged elsewhere; nothing more we can do.
        logger.warning("Could not deliver dead-interaction reply for interaction %s", interaction.id)


async def _disable_and_notify(interaction: Interaction, message: str) -> None:
    """Gentle handling for `_PRESERVE_MESSAGE_PREFIXES` screens: disable the message's components
    in place - leaving its content/embeds completely untouched - and report the error as a
    separate ephemeral reply instead.
    """
    if interaction.message is None:
        await _replace_message(interaction, message)
        return

    disabled_view: View = View.from_message(interaction.message, timeout=None)
    for child in disabled_view.children:
        if isinstance(child, (Button, Select, UserSelect, RoleSelect, MentionableSelect, ChannelSelect)):
            child.disabled = True

    # Stopped so discord.py doesn't bother tracking this throwaway view any further.
    disabled_view.stop()

    try:
        await interaction.response.edit_message(view=disabled_view)
        await interaction.followup.send(message, ephemeral=True)
    except HTTPException:
        logger.warning("Could not deliver dead-interaction reply for interaction %s", interaction.id)


async def handle_dead_interaction(interaction: Interaction) -> None:
    """Bot-wide fallback for button/select clicks that no live view will ever handle.

    `discord.ui.View`s across this bot are mostly non-persistent, in-memory session state that a bot restart
    discards - but old messages with their components still exist on Discord. Without this,
    clicking one afterwards just leaves the interaction unacknowledged, and Discord shows a bare
    "This interaction failed" with no explanation.
    """
    if interaction.type is not InteractionType.component:
        return

    if _has_live_handler(interaction):
        return

    language: SupportedLanguage = await get_language(interaction)
    message: str = translate(language, "errors.dead_interaction")

    custom_id: str = (interaction.data or {}).get("custom_id", "")  # type: ignore[assignment,call-overload]
    if custom_id.startswith(_PRESERVE_MESSAGE_PREFIXES):
        await _disable_and_notify(interaction, message)
    else:
        await _replace_message(interaction, message)
