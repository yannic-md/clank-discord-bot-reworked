import asyncio

import discord
from aiohttp import ClientSession

from core.bot import ClankReworked
from core.setup.dotenv import BOT_PREFIX, BOT_TOKEN
from core.setup.logger import setup_db_logging, setup_logging


async def main() -> None:
    """Initialize logging, create bot client, and start the Discord bot."""
    setup_logging()
    setup_db_logging()

    async with ClientSession() as web_client:  # noqa: SIM117
        async with ClankReworked(command_prefix=BOT_PREFIX, web_client=web_client, intents=discord.Intents.all()) as bot:
            if BOT_TOKEN == "MISSING":
                print("Bot Token was not set. Check .env!")
                return

            try:
                await bot.start(BOT_TOKEN, reconnect=True)
            except discord.PrivilegedIntentsRequired:
                print(
                    "Your bot is using privileged intents from discord, but they are not enabled in"
                    " the Discord Developer Portal. Do it here: https://discord.com/developers/applications/"
                )
                return


# Don't run the login twice
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Exiting...")
        exit(0)
