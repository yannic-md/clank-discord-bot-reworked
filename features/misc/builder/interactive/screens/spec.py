from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Protocol

from discord import Member, Thread
from discord.abc import GuildChannel
from discord.ui import Item

from core.enums.language import SupportedLanguage
from features.misc.builder.interactive.draft import InteractiveLibrary
from features.misc.builder.interactive.editor import Section
from features.misc.builder.session import WebhookSender


class EditorSession(Protocol):
    """The part of a builder session (`BuilderSession`, `ContainerBuilderSession`) the editor screens work with."""

    language: SupportedLanguage
    library: InteractiveLibrary
    webhook: WebhookSender
    active_item_id: int | None
    """The element last selected on the overview."""
    slashcmd_author: Member
    slashcmd_channel: GuildChannel | Thread


@dataclass(frozen=True, slots=True)
class Control:
    """One button, dropdown or preview of a screen. `name` tells it apart from the others on the same screen."""

    name: str
    item: Item


@dataclass(slots=True)
class Screen:
    """A screen of the editor: its texts and its controls, row by row. How it is drawn is up to the builder."""

    title: str
    body: str
    """What the screen says below its title."""
    sections: Sequence[Section] | None = None
    """The summary of an element below the body - if the screen has one."""
    gap: int = 1
    """How many blank lines an embed leaves between the body and the summary."""
    spaced: bool = True
    """Whether a text screen leaves a blank line before a part of the summary that asks for one."""
    warning: bool = False
    """Whether the screen is coloured as a warning (a custom sender limits what can be created)."""
    error: str | None = None
    rows: dict[int, list[Control]] = field(default_factory=dict)
    """The controls by the number of the row they sit in (0 to 4); within a row in the order they were added."""

    def add(self, row: int, control: Control) -> None:
        """Put `control` at the end of row number `row`."""
        self.rows.setdefault(row, []).append(control)
