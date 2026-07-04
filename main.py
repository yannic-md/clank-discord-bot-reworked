import asyncio

import discord
from aiohttp import ClientSession
from discord.ext import commands

from core.bot import ClankReworked
from core.db.base import BOT_TOKEN
from core.logging_setup import setup_logging


async def main() -> None:
    """Initialize logging, create bot client, and start the Discord bot."""
    setup_logging()

    async with ClientSession() as web_client:
        async with ClankReworked(
            commands.when_mentioned, web_client=web_client, intents=discord.Intents.all()
        ) as bot:
            if BOT_TOKEN == "MISSING":
                print("Bot Token was not set. Check .env!")
                return

            try:
                await bot.start(BOT_TOKEN, reconnect=True)
            except discord.PrivilegedIntentsRequired:
                print(
                    "Your bot is using privileged intents from discord, but they are not enabled in the "
                    "Discord Developer Portal. Do it here: https://discord.com/developers/applications/"
                )
                return


try:
    asyncio.run(main())
except KeyboardInterrupt:
    print("Exiting...")
    exit(0)
