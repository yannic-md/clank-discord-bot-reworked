from discord import (
    ClientUser,
    HTTPException,
    Interaction,
    Member,
    Message,
    NotFound,
    StageChannel,
    TextChannel,
    Thread,
    VoiceChannel,
)
from discord.abc import GuildChannel
from discord.app_commands import allowed_installs, checks, command, default_permissions, describe, guild_only, rename
from discord.ext.commands import AutoShardedBot, Cog

from core.discord_api.perms import perms_send_message
from core.enums.language import SupportedLanguage
from core.i18n.discord_translator import cmd
from core.i18n.resolve import get_language
from features.misc.builder.container.session import ContainerBuilderSession
from features.misc.builder.container.translations import ts
from features.misc.builder.container.util.message_import import load_message_into_session
from features.misc.builder.container.views.base import send_overflow_notes, track_active_view
from features.misc.builder.container.views.gui import MainView


class ContainerBuilder(Cog):
    """Cog providing the `/container-builder` slash command."""

    def __init__(self, client: AutoShardedBot) -> None:
        """Store the bot client."""
        self.client: AutoShardedBot = client

    @command(name=cmd("commands.builder.container.name"), description=cmd("commands.builder.container.description"))
    @rename(message_id=cmd("commands.builder.container.parameter.name"))
    @describe(message_id=cmd("commands.builder.container.parameter.description"))
    @allowed_installs(guilds=True, users=False)
    @default_permissions(manage_messages=True)
    @checks.has_permissions(manage_messages=True)
    @perms_send_message
    @guild_only()
    async def container_builder(self, interaction: Interaction, message_id: str | None = None) -> None:
        """Open the container builder - for a new message, or to edit the message `message_id`."""
        assert interaction.guild_id is not None
        assert isinstance(interaction.channel, (TextChannel, VoiceChannel, StageChannel, Thread))
        assert isinstance(interaction.user, Member)

        language: SupportedLanguage = await get_language(interaction)
        channel = interaction.channel
        assert isinstance(channel, GuildChannel | Thread)

        session = ContainerBuilderSession(
            guild_id=interaction.guild_id,
            slashcmd_author_id=interaction.user.id,
            slashcmd_author=interaction.user,
            slashcmd_channel=channel,
            language=language,
        )

        notice: str | None = None
        if message_id is not None:
            try:
                target_message: Message = await channel.fetch_message(int(message_id))
            except ValueError, NotFound, HTTPException:
                await interaction.response.send_message(ts(language, "errors.message_not_found"), ephemeral=True)
                return

            client_user = self.client.user
            assert isinstance(client_user, ClientUser)

            # Own messages are edited in place, everyone else's are copied into a new message.
            fatal_error, notice = load_message_into_session(session, target_message, client_user.id)
            if fatal_error is not None:
                await interaction.response.send_message(fatal_error, ephemeral=True)
                return

        view = MainView(session, notice=notice)
        track_active_view(view)
        await interaction.response.send_message(view=view, ephemeral=True)
        view.message = await interaction.original_response()
        await send_overflow_notes(interaction, view)


async def setup(client: AutoShardedBot) -> None:
    """Register the `ContainerBuilder` cog."""
    await client.add_cog(ContainerBuilder(client))
