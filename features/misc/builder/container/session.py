from dataclasses import dataclass, field

from discord import Member, Message, Thread
from discord.abc import GuildChannel
from discord.ui import LayoutView

from core.enums.language import SupportedLanguage
from features.misc.builder.container.models import ComponentKind, ComponentNode, ContainerTemplate
from features.misc.builder.container.translations import t
from features.misc.builder.session import WebhookSender


@dataclass
class ContainerBuilderSession:
    """In-memory, per-invocation state for one `/container-builder` interaction.

    Lives only on the current screen's view hierarchy for the duration of the interaction
    (view timeout); nothing here is persisted.
    """

    guild_id: int
    slashcmd_author_id: int
    slashcmd_author: Member
    slashcmd_channel: GuildChannel | Thread
    language: SupportedLanguage

    components: list[ComponentNode] = field(default_factory=list)
    next_id: int = 1
    webhook: WebhookSender = field(default_factory=WebhookSender)
    templates: list[ContainerTemplate] = field(default_factory=list)
    """The invoking user's templates loaded from the database, refreshed by the template
    screen whenever it opens or changes the set."""
    active_template_name: str | None = None
    edit_mode: bool = False
    target_message: Message | None = None
    """Set (together with `edit_mode`) when one of the bot's own messages is being edited in place;
    otherwise a loaded message is only a copy and gets sent as a new message."""
    channel: GuildChannel | Thread | None = None
    """Explicit target channel chosen via the "Kanal" button; `None` means the invocation channel."""
    active_view: LayoutView | None = field(default=None, repr=False)
    """The currently shown screen's view - tracked so switching screens can `stop()` the
    previous one, whose own timeout would otherwise still fire independently later and
    overwrite the message with its now-stale (and no longer displayed) buttons."""

    active_selection: dict[tuple[int | None, ComponentKind | None], int] = field(default_factory=dict)
    """Remembers, per (parent container id or None, kind - or None for the order screen),
    which component id was last selected there, so switching screens and coming back
    doesn't reset the selection back to the first item every time."""

    @property
    def target_channel(self) -> GuildChannel | Thread:
        """The channel the message will be sent to: the explicit override, or the invocation channel."""
        return self.channel or self.slashcmd_channel

    def new_id(self) -> int:
        node_id = self.next_id
        self.next_id += 1
        return node_id

    def __post_init__(self) -> None:
        # A fresh `/container-builder` invocation always starts with one seeded TextDisplay,
        # so the main screen's live preview is never blank on first use.
        if not self.components:
            self.components.append(
                ComponentNode(
                    id=self.new_id(), kind=ComponentKind.TEXT_DISPLAY, content=t(self.language, "main.default_content")
                )
            )
