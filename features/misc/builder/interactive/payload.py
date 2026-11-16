import copy
import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from logging import Logger
from typing import Any

from discord import Embed, Guild, Member
from discord.abc import GuildChannel, Messageable
from discord.ui import LayoutView

from core.discord_api.limits import MAX_EMBED_COUNT, MAX_MESSAGE_CONTENT
from features.misc.builder.interactive.draft import InteractiveLibrary
from features.misc.builder.interactive.models import MessagePayload, PayloadKind
from features.misc.builder.interactive.template_text import fill_embeds, fill_nodes
from features.misc.builder.interactive.variables import render_variables
from features.misc.builder.session import WebhookSender

logger: Logger = logging.getLogger("discord")


@dataclass
class OutgoingMessage:
    """A message ready to be sent: the pieces `send` accepts. A `view` (Components V2) comes without content/embeds."""

    content: str | None = None
    embeds: list[Embed] = field(default_factory=list)
    view: LayoutView | None = None


class _PayloadContext:
    """What rebuilding a container template needs from a "session": ids, a library and the sender identity.

    A message that someone's click sends cannot carry interactive buttons of its own (there is no stored item
    for them), so the context pretends a custom sender is set - which makes the template loading leave those out.
    """

    def __init__(self) -> None:
        """Start with an empty library."""
        self.library: InteractiveLibrary = InteractiveLibrary()
        self.webhook: WebhookSender = WebhookSender(username="-")
        self._next_id: int = 1

    def new_id(self) -> int:
        """Hand out the next unused node id."""
        node_id = self._next_id
        self._next_id += 1
        return node_id


def _container_view(data: list[dict[str, object]], render: Callable[[str], str]) -> LayoutView | None:
    """The Components V2 message a snapshot of a container template describes - its texts with the variables filled in by
    `render`; `None` if nothing usable is left."""
    # Imported here because the container builder itself depends on this package.
    from features.misc.builder.container.util.render import StaticLayoutView, build_item
    from features.misc.builder.container.util.templates import nodes_from_data
    from features.misc.builder.container.util.tree import non_empty_nodes

    context = _PayloadContext()
    nodes, _ = nodes_from_data(context, data)
    nodes = non_empty_nodes(nodes)
    if not nodes:
        return None

    fill_nodes(nodes, render)
    return StaticLayoutView([build_item(node, context.library, final=True) for node in nodes])


def _embeds(data: list[dict[str, object]], render: Callable[[str], str]) -> list[Embed]:
    """The embeds of a snapshot of an embed template - their texts with the variables filled in by `render`; those that
    cannot be rebuilt are left out."""
    entries: list[dict[str, Any]] = [copy.deepcopy(entry) for entry in data[:MAX_EMBED_COUNT]]  # the snapshot stays as it is
    fill_embeds(entries, render)
    embeds: list[Embed] = []
    for entry in entries:
        try:
            embeds.append(Embed.from_dict(entry))
        except KeyError, TypeError, ValueError, AttributeError:  # whatever a hand-edited or old embed breaks on
            logger.warning("interactive-builder: skipping an unrebuildable embed in a message action", exc_info=True)
    return embeds


def build_outgoing(
    payload: MessagePayload,
    *,
    member: Member,
    guild: Guild,
    channel: Messageable | GuildChannel | None,
    answers: Sequence[tuple[str, str]] = (),
) -> OutgoingMessage | None:
    """The message a payload turns into for `member`, or `None` if there is nothing usable to send.

    `answers` are the answers of a submitted form for its `{answers}` placeholders. A text that grows past what
    Discord accepts - answers can be long - is cut off.
    """

    def render(template_text: str) -> str:
        """`template_text` with the variables filled in for `member`."""
        return render_variables(template_text, member=member, guild=guild, channel=channel, answers=answers)

    text = render(payload.text).strip()
    if len(text) > MAX_MESSAGE_CONTENT:
        text = f"{text[: MAX_MESSAGE_CONTENT - 1]}…"

    if payload.kind is PayloadKind.TEXT:
        return OutgoingMessage(content=text) if text else None

    if payload.kind is PayloadKind.EMBED:
        embeds = _embeds(payload.data, render)
        return OutgoingMessage(content=text or None, embeds=embeds) if embeds or text else None

    view = _container_view(payload.data, render)
    return OutgoingMessage(view=view) if view is not None else None
