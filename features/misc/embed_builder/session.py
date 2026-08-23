from dataclasses import dataclass, field

from discord import Embed, Member, Message, Thread, User
from discord.abc import GuildChannel
from discord.ui import View

from core.enums.language import SupportedLanguage
from features.misc.embed_builder.util.templates import TemplatePlaceholder, get_guild_templates

BUILDER_VIEW_TIMEOUT: float = 900.0


@dataclass
class WebhookSender:
    """Custom sender identity a message can be sent with, via a channel webhook."""

    username: str | None = None
    avatar_url: str | None = None
    webhook_url: str | None = None
    validated_channel_id: int | None = None
    explicit_url: bool = False
    display_name: str | None = None
    """The webhook's own name, captured for status display only - never sent as an
    override, so a URL-only webhook (no explicit `username`) keeps its own identity."""

    @property
    def enabled(self) -> bool:
        return self.username is not None or self.avatar_url is not None or self.webhook_url is not None


@dataclass
class BuilderSession:
    """In-memory, per-invocation state for one `/embed_builder` interaction.

    Lives only on the `EmbedBuilderGUI` view hierarchy for the duration of the
    interaction (view timeout); nothing here is persisted, other than the
    guild-wide template placeholders above.
    """

    guild_id: int
    slashcmd_author_id: int
    slashcmd_author: Member
    slashcmd_channel: GuildChannel | Thread
    language: SupportedLanguage

    content: str = ""
    embeds: list[Embed] = field(default_factory=lambda: [Embed()])
    active_embed_index: int = 0
    channel: GuildChannel | Thread | None = None
    webhook: WebhookSender = field(default_factory=WebhookSender)
    edit_mode: bool = False
    target_message: Message | None = None
    active_field: int | None = None
    active_template_name: str | None = None
    active_view: View | None = field(default=None, repr=False)
    """The currently shown screen's view - tracked so switching screens can `stop()` the
    previous one, whose own timeout would otherwise still fire independently later and
    overwrite the message with its now-stale (and no longer displayed) buttons."""

    @property
    def active_embed(self) -> Embed:
        return self.embeds[self.active_embed_index]

    @property
    def message_content(self) -> str | None:
        return self.content or None

    @property
    def target_channel(self) -> GuildChannel | Thread:
        """The channel a message will be sent to: the explicit override, or the invocation channel."""
        return self.channel or self.slashcmd_channel

    @property
    def templates(self) -> list[TemplatePlaceholder]:
        """Saved templates to restore created embed-messages."""
        return get_guild_templates(self.guild_id)


def is_own_message(message: Message, bot_user: Member | User | None) -> bool:
    return bot_user is not None and message.author.id == bot_user.id
