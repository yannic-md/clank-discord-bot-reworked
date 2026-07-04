from typing import Any

from aiohttp import ClientSession
from discord import ClientUser
from discord.app_commands import AppCommand
from discord.ext import commands
from discord.ext.commands import NoEntryPointError

from utils.extension_finder import discover_extensions


class ClankReworked(commands.AutoShardedBot):
    """Discord bot implementation for the Clank Reworked project.

    This bot keeps shared application state for the shared HTTP client,
    and an optional testing guild ID used to sync application commands during startup.
    """

    def __init__(self, *args: Any, web_client: ClientSession, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.web_client: ClientSession = web_client
        self.loaded_cogs_count: int = 0
        self.synced_commands: list[AppCommand] = []
        self.sync_success: bool = True

    async def setup_hook(self) -> None:
        """
        Load bot extensions and sync application commands for the test guild.
        """
        for extension in discover_extensions():
            try:
                await self.load_extension(extension)
                self.loaded_cogs_count += 1
            except NoEntryPointError:
                continue

    async def on_ready(self) -> None:
        """
        Called when the bot has successfully connected to Discord and is ready.
        """
        user: ClientUser | None = self.user
        assert user is not None

        print(r"  ____  _ _  _       _    _ _     _   ")
        print(r" |  _ \| | || |     | |  | (_)   | |  ")
        print(r" | |_) | | || |_ ___| | _| |_ ___| |_ ")
        print(r" |  _ <| |__   _/ __| |/ / | / __| __|")
        print(r" | |_) | |  | || (__|   <| | \__ \ |_ ")
        print(r" |____/|_|  |_| \___|_|\_\_|_|___/\__|")
        print("                                      ")
        print(f"Developed by Yannic | {user.name}")
        print(
            f"Shard-Count: {self.shard_count} | Latency: {self.latency * 1000:.2f}ms | "
            f"Loaded Cogs: {self.loaded_cogs_count}"
        )
        print("────────────")
