from discord import Interaction

from features.misc.builder.embed.session import BuilderSession
from features.misc.builder.embed.util.embed_ops import non_empty_embeds
from features.misc.builder.embed.validation import append_error, text_limit_problem


async def reject(interaction: Interaction, session: BuilderSession, message: str) -> None:
    """Show the main screen again with `message` below it: nothing of what the modal was given is applied."""
    from features.misc.builder.embed.views import EmbedBuilderGUI

    await append_error(interaction, non_empty_embeds(session.embeds), EmbedBuilderGUI(session), message)


async def reject_text_limit(interaction: Interaction, session: BuilderSession, over: int) -> None:
    """Show the main screen again with the reason why the text was not applied: it is `over` characters too long for
    what Discord takes in one message."""
    await reject(interaction, session, text_limit_problem(session.language, over))
