import sqlalchemy.dialects.mysql
from sqlalchemy.dialects.mysql.dml import Insert as MySQLInsert

from core.db.base import async_session
from core.db.models.language.user_language import UserLanguage
from core.enums.language import DEFAULT_LANGUAGE, SupportedLanguage


async def get_user_language(user_id: int) -> SupportedLanguage:
    """Fetch the language configured for a user.

    Args:
        user_id (int): Snowflake ID of the user.

    Returns:
        SupportedLanguage: The guild's configured language, or `DEFAULT_LANGUAGE`
            if no settings row exists yet for the guild.
    """
    async with async_session() as session:
        settings: UserLanguage | None = await session.get(UserLanguage, user_id)
        return settings.language if settings else DEFAULT_LANGUAGE


async def set_user_language(user_id: int, language: SupportedLanguage) -> None:
    """Create or update the language configured for a user.

    Args:
        user_id (int): Snowflake ID of the user.
        language (SupportedLanguage): The language to store for the user.
    """
    async with async_session() as session:
        stmt: MySQLInsert = sqlalchemy.dialects.mysql.insert(UserLanguage).values(user_id=user_id, language=language)
        stmt = stmt.on_duplicate_key_update(language=stmt.inserted.language)
        await session.execute(stmt)
        await session.commit()
