from typing import Literal

from discord import Forbidden, HTTPException
from discord.app_commands import AppCommand, CommandSyncFailure, TranslationError
from discord.ext import commands
from discord.ext.commands import AutoShardedBot, Cog

from core.discord_api.checks import is_owner


class OwnerCommands(Cog):
    """
    A cog for owner-only commands, specifically for synchronizing application commands with Discord servers.

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
        try:
            synced: list[AppCommand] = await self.client.tree.sync(guild=ctx.guild if (guilds and guilds == "~") else None)
        except CommandSyncFailure, TranslationError:
            await ctx.reply(
                "› `❌` - Ich konnte die Befehle nicht synchronisieren - mindestens ein Befehl enthält "
                "ungültige Daten! <a:deny:819942197192294440>"
            )
            return
        except Forbidden:
            await ctx.reply(
                "› `❌` - Ich konnte die Befehle nicht synchronisieren - der Bot wurde nicht mit dem "
                "`application.commands` Scope eingeladen! <a:deny:819942197192294440>"
            )
            return
        except HTTPException:
            # workaround to some weird discord API errors. Sometimes the sync "fail" but that's not the truth
            synced = await ctx.bot.tree.fetch_commands(guild=ctx.guild if (guilds and guilds == "~") else None)

        if not guilds or guilds != "~":
            await ctx.reply(
                f"› `✅` - Ich habe `{len(synced)}` Befehle mit **allen** Servern synchronisiert! "
                f"<a:hack:772187514286506005>"
            )
        else:
            await ctx.reply(
                f"› `✅` - Ich habe `{len(synced)}` Befehle mit dem **aktuellen** Server "
                f"synchronisiert! <a:hack:772187514286506005>"
            )


async def setup(client: AutoShardedBot) -> None:
    await client.add_cog(OwnerCommands(client))
