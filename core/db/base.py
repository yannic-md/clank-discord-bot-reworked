from os import getenv

from dotenv import load_dotenv

load_dotenv()
BOT_TOKEN: str = getenv("BOT_TOKEN", "MISSING")
TESTING_GUILD_ID: str = getenv("TESTING_GUILD_ID", "0")
