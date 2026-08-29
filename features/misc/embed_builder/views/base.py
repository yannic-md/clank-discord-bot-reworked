import contextlib

from discord import AllowedMentions, Colour, Embed, HTTPException, Interaction, Member, Message, NotFound, Thread
from discord.abc import GuildChannel
from discord.ui import Button, ChannelSelect, Item, MentionableSelect, RoleSelect, Select, UserSelect, View

from core.i18n.translator import translate
from core.setup.errors import error_handler
from features.misc.embed_builder.session import BUILDER_VIEW_TIMEOUT, BuilderSession
from features.misc.embed_builder.util.embed_ops import embed_snippet, non_empty_embeds
from features.misc.embed_builder.validation import append_error


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
        super().__init__(timeout=BUILDER_VIEW_TIMEOUT)

    async def on_timeout(self) -> None:
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
    key: str = "builder.placeholders.embed_option_snippet" if snippet else "builder.placeholders.embed_option_label_empty"
    return translate(session.language, key, number=number, snippet=snippet or "")


def build_allowed_mentions(channel: GuildChannel | Thread, member: Member) -> AllowedMentions:
    """Build `AllowedMentions` reflecting whether `member` may ping @everyone/@here/roles in `channel`.

    Never blocks sending: a user without the `mention_everyone` permission can still
    send content containing those mentions, they just won't actually notify anyone -
    the confirm screen warns about this beforehand (see `SendConfirmView`).
    """
    has_permission: bool = channel.permissions_for(member).mention_everyone
    return AllowedMentions(everyone=has_permission, roles=has_permission, users=True, replied_user=False)


async def has_message_content(interaction: Interaction, session: BuilderSession, view: BuilderScreenView) -> bool:
    """Block sending/saving a message with neither content nor any filled-out embed."""
    if session.message_content or non_empty_embeds(session.embeds):
        return True

    message: str = translate(session.language, "builder.errors.nothing_to_send")
    await append_error(interaction, view.embeds, view, message)
    return False


def create_success_embed(session: BuilderSession, key: str, jump_url: str | None = None) -> Embed:
    description: str = translate(session.language, key)
    if jump_url:
        description += f"\n\n{translate(session.language, 'builder.info.success.jump_link', jump_url=jump_url)}"

    return Embed(description=description, colour=Colour.green())
