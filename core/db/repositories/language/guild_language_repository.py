from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.dialects.mysql.dml import Insert as MySQLInsert

from core.db.base import async_session
from core.db.models.language.guild_language import GuildLanguage
from core.enums.language import DEFAULT_LANGUAGE, SupportedLanguage


async def get_guild_language(guild_id: int) -> SupportedLanguage:
    """Fetch the language configured for a guild.

    Args:
        guild_id (int): Snowflake ID of the guild.

    Returns:
        SupportedLanguage: The guild's configured language, or `DEFAULT_LANGUAGE`
            if no settings row exists yet for the guild.
    """
    async with async_session() as session:
        settings: GuildLanguage | None = await session.get(GuildLanguage, guild_id)
        return settings.language if settings else DEFAULT_LANGUAGE


async def set_guild_language(guild_id: int, language: SupportedLanguage) -> None:
    """Create or update the language configured for a guild.

    Args:
        guild_id (int): Snowflake ID of the guild.
        language (SupportedLanguage): The language to store for the guild.
    """
    async with async_session() as session:
        stmt: MySQLInsert = mysql_insert(GuildLanguage).values(guild_id=guild_id, language=language)
        stmt = stmt.on_duplicate_key_update(language=stmt.inserted.language)
        await session.execute(stmt)
        await session.commit()
