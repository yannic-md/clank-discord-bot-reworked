from discord import Interaction
from discord.ext.commands import Context

from core.db.repositories.language.guild_language_repository import get_guild_language
from core.db.repositories.language.user_language_repository import get_user_language
from core.enums.language import SupportedLanguage


async def get_language(ctx: Context | Interaction) -> SupportedLanguage:
    """Resolve which language to reply to a command invocation in.

    Args:
        ctx (Context | Interaction): The classic command context or the
            interaction to resolve a language for.

    Returns:
        SupportedLanguage: The language to use when translating a reply.
    """
    if isinstance(ctx, Context):
        if ctx.guild is not None:
            return await get_guild_language(ctx.guild.id)
        return await get_user_language(ctx.author.id)

    if ctx.guild_id is not None:
        return await get_guild_language(ctx.guild_id)
    return await get_user_language(ctx.user.id)
