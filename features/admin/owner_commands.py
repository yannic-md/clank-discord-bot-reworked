from typing import Literal

from discord import Forbidden, HTTPException
from discord.app_commands import AppCommand, CommandSyncFailure, TranslationError
from discord.ext import commands
from discord.ext.commands import AutoShardedBot, Cog

from core.db.repositories.language.guild_language_repository import get_guild_language
from core.db.repositories.language.user_language_repository import get_user_language
from core.discord_api.checks import is_owner
from core.enums.language import SupportedLanguage
from core.i18n.translator import translate


class OwnerCommands(Cog):
    """
    A cog for bot-owner only commands, specifically for synchronizing application commands with Discord servers.

    This cog provides administrative commands that can only be executed by the bot owner.
    """

    def __init__(self, client: AutoShardedBot):
        self.client = client

    @commands.command()
    @commands.guild_only()
    @commands.check(is_owner)
    async def sync(self, ctx: commands.Context, guilds: Literal["~"] | None = None) -> None:
        """
        Synchronize application commands with Discord servers.

        Args:
            ctx (commands.Context): The command context.
            guilds (Literal["~"] | None, optional): If "~", sync only for the current guild.
                                                   If None or other value, sync globally. Defaults to None.
        """
        if ctx.guild is not None:
            language: SupportedLanguage = await get_guild_language(ctx.guild.id)
        else:
            language = await get_user_language(ctx.author.id)

        try:
            synced: list[AppCommand] = await self.client.tree.sync(guild=ctx.guild if (guilds and guilds == "~") else None)
        except CommandSyncFailure, TranslationError:
            await ctx.reply(translate(language, "admin.sync.error.invalid_data"))
            return
        except Forbidden:
            await ctx.reply(translate(language, "admin.sync.error.forbidden"))
            return
        except HTTPException:
            # workaround to some weird discord API errors. Sometimes the sync "fail" but that's not the truth
            synced = await ctx.bot.tree.fetch_commands(guild=ctx.guild if (guilds and guilds == "~") else None)

        if not guilds or guilds != "~":
            await ctx.reply(translate(language, "admin.sync.success.other", count_var=len(synced)))
        else:
            await ctx.reply(translate(language, "admin.sync.success.one", count_var=len(synced)))


async def setup(client: AutoShardedBot) -> None:
    await client.add_cog(OwnerCommands(client))
