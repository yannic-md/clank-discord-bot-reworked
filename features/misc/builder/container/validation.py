from collections.abc import Iterator

from discord import Attachment, Member, Thread
from discord.abc import GuildChannel

from features.misc.builder.container.models import ComponentKind, ComponentNode
from features.misc.builder.validation import IMAGE_EXTENSIONS, mentions_everyone_or_role

_MEDIA_EXTENSIONS: tuple[str, ...] = (*IMAGE_EXTENSIONS, ".mp4", ".webm", ".mov")


def is_valid_media_attachment(attachment: Attachment) -> bool:
    content_type = (attachment.content_type or "").lower()
    if content_type.startswith(("image/", "video/")):
        return True
    return attachment.filename.lower().endswith(_MEDIA_EXTENSIONS)


def _iter_text_displays(nodes: list[ComponentNode]) -> Iterator[ComponentNode]:
    for node in nodes:
        if node.kind == ComponentKind.TEXT_DISPLAY:
            yield node
        elif node.kind == ComponentKind.CONTAINER:
            yield from _iter_text_displays(node.children)


def contains_mass_mention(nodes: list[ComponentNode]) -> bool:
    """Whether any TextDisplay's content would ping @everyone, @here, or a role.

    TextDisplay content renders like normal message content, including mentions - so the
    same permission-gating concern the embed-builder has for its message content applies here.
    """
    haystack = " ".join(node.content for node in _iter_text_displays(nodes))
    return mentions_everyone_or_role(haystack)


def missing_send_permissions(channel: GuildChannel | Thread, member: Member) -> list[str]:
    """The permissions `member` lacks to see `channel` and post in it."""
    permissions = channel.permissions_for(member)
    return [name for name in ("view_channel", "send_messages") if not getattr(permissions, name)]
