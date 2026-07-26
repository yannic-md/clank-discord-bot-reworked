from os import getenv

from dotenv import load_dotenv

load_dotenv()
BOT_TOKEN: str = getenv("BOT_TOKEN", "MISSING")
BOT_PREFIX: str = getenv("BOT_PREFIX", "!")
OWNER_ID: str = getenv("OWNER_ID", "0")
TESTING_GUILD_ID: str = getenv("TESTING_GUILD_ID", "0")
