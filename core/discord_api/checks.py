from discord import Interaction
from discord.ext.commands import Context

from core.dotenv_setup import OWNER_ID


def is_owner(ctx: Context | Interaction) -> bool:
    """
    Check if the command was run by the bot owner.

    This decorator checks if the author of the command (either a Context or Interaction)
    is the owner of the bot. If the author is not the owner, it raises a CheckFailure.

    Args:
        ctx (Context | Interaction): The context or interaction of the command.

    Returns:
        bool: True if the author is the bot owner, otherwise raises CheckFailure.

    Raises:
        CheckFailure: If the author is not the bot owner.
    """
    author_id: int = ctx.author.id if isinstance(ctx, Context) else ctx.user.id
    return not (OWNER_ID.isdigit() and author_id != int(OWNER_ID))
