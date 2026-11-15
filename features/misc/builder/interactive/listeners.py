import logging
from collections.abc import Coroutine
from logging import Logger
from typing import Any

from discord import (
    Guild,
    Interaction,
    InteractionType,
    RawBulkMessageDeleteEvent,
    RawMessageDeleteEvent,
    RawThreadDeleteEvent,
)
from discord.abc import GuildChannel
from discord.ext.commands import AutoShardedBot, Cog

from core.db.repositories.interactive_builder.interactive_item_repository import (
    delete_items_for_channel,
    delete_items_for_guild,
    delete_items_for_messages,
)
from core.setup.errors import error_handler
from features.misc.builder.interactive.runtime import (
    FORM_PREFIX,
    InteractiveButton,
    InteractiveSelect,
    handle_form_submit,
)
from features.misc.builder.tasks import run_in_background

logger: Logger = logging.getLogger("discord")


async def _guarded(cleanup: Coroutine[Any, Any, None]) -> None:
    """Await a cleanup and only log its failure: there is nobody to report a missed cleanup to."""
    try:
        await cleanup
    except Exception:
        logger.exception("Could not clean up interactive builder items.")


class InteractiveCleanup(Cog):
    """Drops the stored items of messages, channels and guilds that no longer exist."""

    def __init__(self, client: AutoShardedBot) -> None:
        """Store the bot client."""
        self.client: AutoShardedBot = client

    @Cog.listener()
    async def on_raw_message_delete(self, payload: RawMessageDeleteEvent) -> None:
        """Drop the items of a deleted message."""
        run_in_background(_guarded(delete_items_for_messages([payload.message_id])))

    @Cog.listener()
    async def on_raw_bulk_message_delete(self, payload: RawBulkMessageDeleteEvent) -> None:
        """Drop the items of messages deleted in bulk."""
        run_in_background(_guarded(delete_items_for_messages(payload.message_ids)))

    @Cog.listener()
    async def on_guild_channel_delete(self, channel: GuildChannel) -> None:
        """Drop the items of every message in a deleted channel."""
        run_in_background(_guarded(delete_items_for_channel(channel.id)))

    @Cog.listener()
    async def on_raw_thread_delete(self, payload: RawThreadDeleteEvent) -> None:
        """Drop the items of every message in a deleted thread."""
        run_in_background(_guarded(delete_items_for_channel(payload.thread_id)))

    @Cog.listener()
    async def on_guild_remove(self, guild: Guild) -> None:
        """Drop all items of a guild the bot was removed from."""
        run_in_background(_guarded(delete_items_for_guild(guild.id)))


class FormSubmissions(Cog):
    """Carries out the forms users submit."""

    def __init__(self, client: AutoShardedBot) -> None:
        """Store the bot client."""
        self.client: AutoShardedBot = client

    @Cog.listener()
    async def on_interaction(self, interaction: Interaction) -> None:
        """Run a submitted form. Done here rather than in the modal object so that a form that was opened before a
        restart can still be submitted."""
        if interaction.type is not InteractionType.modal_submit:
            return

        custom_id = (interaction.data or {}).get("custom_id", "")  # type: ignore[call-overload]
        if not isinstance(custom_id, str) or not custom_id.startswith(f"{FORM_PREFIX}:"):
            return

        try:
            await handle_form_submit(interaction)
        except Exception as error:
            await error_handler(interaction, error)  # type: ignore[arg-type]


async def setup(client: AutoShardedBot) -> None:
    """Register the handlers of interactive buttons and dropdowns and the cleanup listeners."""
    client.add_dynamic_items(InteractiveButton, InteractiveSelect)
    await client.add_cog(InteractiveCleanup(client))
    await client.add_cog(FormSubmissions(client))


async def teardown(client: AutoShardedBot) -> None:
    """Unregister the handlers of interactive buttons and dropdowns again, so a reload does not register them twice."""
    client.remove_dynamic_items(InteractiveButton, InteractiveSelect)
