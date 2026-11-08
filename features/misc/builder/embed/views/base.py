import contextlib

from discord import Colour, Embed, HTTPException, Interaction, Message, NotFound
from discord.ui import Button, ChannelSelect, Item, MentionableSelect, RoleSelect, Select, UserSelect, View

from core.i18n.translator import translate
from core.setup.errors import error_handler
from features.misc.builder.embed.session import BuilderSession
from features.misc.builder.embed.util.embed_ops import embed_snippet, non_empty_embeds
from features.misc.builder.embed.validation import append_error
from features.misc.builder.session import BUILDER_VIEW_TIMEOUT


class BuilderScreenView(View):
    """Common base for every screen of the embed builder.

    `content`/`embeds` describe what the screen renders; concrete subclasses
    always overwrite these in `__init__`, so the empty list default here is
    never actually mutated in place.
    """

    content: str | None = None
    embeds: list[Embed] = []
    message: Message | None = None
    session: BuilderSession

    def __init__(self) -> None:
        """Create the view with the shared builder timeout."""
        super().__init__(timeout=BUILDER_VIEW_TIMEOUT)

    async def on_timeout(self) -> None:
        """Disable all controls of the sent message once the view expires."""
        if self.message is None:
            return

        for child in self.children:
            if isinstance(child, (Button, Select, UserSelect, RoleSelect, MentionableSelect, ChannelSelect)):
                child.disabled = True

        with contextlib.suppress(HTTPException, NotFound):
            await self.message.edit(view=self)

    async def on_error(self, interaction: Interaction, error: Exception, item: Item) -> None:
        # `error_handler` only relies on duck-typed attributes any exception has
        # (`__cause__`, isinstance checks that gracefully fall through), so reusing
        # the same central error/log-channel pipeline here is safe despite the
        # narrower `AppCommandError` type hint.
        await error_handler(interaction, error)  # type: ignore[arg-type]


async def show(interaction: Interaction, view: BuilderScreenView) -> None:
    """Re-render the builder onto `view`, replacing whatever screen is currently shown."""
    track_active_view(view)
    await interaction.response.edit_message(content=view.content, embeds=view.embeds, view=view)
    view.message = await interaction.original_response()


def track_active_view(view: BuilderScreenView) -> None:
    """Record `view` as the session's currently shown screen, stopping whatever was active before.

    Every screen switch constructs a brand-new `BuilderScreenView`, so without this the
    previous screen's own `on_timeout` would still fire independently on its own schedule
    later and overwrite the message with its now-stale (and no longer displayed) buttons.
    """
    session: BuilderSession = view.session
    if session.active_view is not None and session.active_view is not view:
        assert isinstance(session.active_view, BuilderScreenView)
        session.active_view.stop()

    session.active_view = view


def create_embed_label(session: BuilderSession, embed: Embed, number: int) -> str:
    """ "Embed {number}: {snippet}", or "Embed {number} (empty)" if it has no title/description yet."""
    snippet: str | None = embed_snippet(embed)
    key: str = (
        "builder.embed.placeholders.embed_option_snippet"
        if snippet
        else "builder.embed.placeholders.embed_option_label_empty"
    )
    return translate(session.language, key, number=number, snippet=snippet or "")


async def has_message_content(interaction: Interaction, session: BuilderSession, view: BuilderScreenView) -> bool:
    """Block sending/saving a message with neither content nor any filled-out embed."""
    if session.message_content or non_empty_embeds(session.embeds):
        return True

    message: str = translate(session.language, "builder.embed.errors.nothing_to_send")
    await append_error(interaction, view.embeds, view, message)
    return False


def create_success_embed(session: BuilderSession, key: str, jump_url: str | None = None) -> Embed:
    """Green embed with the text of `key`, plus a link to the message if `jump_url` is given."""
    description: str = translate(session.language, key)
    if jump_url:
        description += f"\n\n{translate(session.language, 'builder.info.success.jump_link', jump_url=jump_url)}"

    return Embed(description=description, colour=Colour.green())
