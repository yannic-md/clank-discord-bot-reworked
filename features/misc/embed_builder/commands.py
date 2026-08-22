from discord import (
    ClientUser,
    Embed,
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
from core.i18n.translator import translate
from features.misc.embed_builder.session import BuilderSession
from features.misc.embed_builder.views import EmbedBuilderGUI


class EmbedBuilder(Cog):
    def __init__(self, client: AutoShardedBot) -> None:
        self.client: AutoShardedBot = client

    @command(name=cmd("commands.builder.embed.name"), description=cmd("commands.builder.embed.description"))
    @rename(message_id=cmd("commands.builder.embed.parameter.name"))
    @describe(message_id=cmd("commands.builder.embed.parameter.description"))
    @allowed_installs(guilds=True, users=False)
    @default_permissions(manage_messages=True)
    @checks.has_permissions(manage_messages=True)
    @perms_send_message
    @guild_only()
    async def embed_builder(self, interaction: Interaction, message_id: str | None = None) -> None:
        assert interaction.guild_id is not None
        assert isinstance(interaction.channel, (TextChannel, VoiceChannel, StageChannel, Thread))
        assert isinstance(interaction.user, Member)

        language: SupportedLanguage = await get_language(interaction)
        channel = interaction.channel

        content: str = translate(language, "builder.main.default_content")
        embeds: list[Embed] = []
        edit_mode: bool = False
        target_message: Message | None = None

        if message_id is not None:
            try:
                target_message = await channel.fetch_message(int(message_id))
            except ValueError, NotFound, HTTPException:
                await interaction.response.send_message(
                    translate(language, "builder.errors.message_not_found"), ephemeral=True
                )
                return

            assert isinstance(target_message, Message)
            client_user: ClientUser | None = self.client.user
            assert isinstance(client_user, ClientUser)

            edit_mode = target_message.author.id == client_user.id
            content = target_message.content
            embeds = [embed.copy() for embed in target_message.embeds]

        assert isinstance(channel, GuildChannel | Thread)
        session: BuilderSession = BuilderSession(
            guild_id=interaction.guild_id,
            slashcmd_author_id=interaction.user.id,
            slashcmd_author=interaction.user,
            language=language,
            slashcmd_channel=channel,
            content=content,
            embeds=embeds,
            edit_mode=edit_mode,
            target_message=target_message,
        )

        view: EmbedBuilderGUI = EmbedBuilderGUI(session)
        await interaction.response.send_message(content=view.content, embeds=view.embeds, view=view, ephemeral=True)
        view.message = await interaction.original_response()


async def setup(client: AutoShardedBot) -> None:
    await client.add_cog(EmbedBuilder(client))
