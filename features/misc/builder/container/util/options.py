import re

from discord import SelectOption

from core.discord_api.limits import MAX_SELECT_OPTION_LABEL
from core.enums.language import SupportedLanguage
from features.misc.builder.container.models import (
    ALLOWED_CHILD_KINDS,
    KIND_EMOJIS,
    MESSAGE_CONTENT_EMOJI,
    ComponentKind,
    ComponentNode,
)
from features.misc.builder.container.session import ContainerBuilderSession
from features.misc.builder.container.translations import kind_label, t
from features.misc.builder.container.util.tree import find_parent

_LINE_MARKER: re.Pattern[str] = re.compile(r"^\s*(?:#{1,3} |-# |>>> |> |[-*] |\d+\. )")
_CODE_FENCE: re.Pattern[str] = re.compile(r"```(?:[\w+-]*\n)?(.*?)```", re.DOTALL)
_MARKDOWN_LINK: re.Pattern[str] = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_CUSTOM_EMOJI: re.Pattern[str] = re.compile(r"<a?(:\w+:)\d+>")
_INLINE_MARKERS: re.Pattern[str] = re.compile(r"\*\*\*|\*\*|\*|__|~~|\|\||`")  # bold/italic/underline/strike/spoiler/code
_UNDERSCORE_ITALIC: re.Pattern[str] = re.compile(r"(?<!\w)_(.+?)_(?!\w)")  # _italic_, but not snake_case


def _plain(text: str) -> str:
    """The text without Discord markdown, collapsed onto one line - dropdown labels can't render formatting."""
    text = _CODE_FENCE.sub(r"\1", text)
    text = "\n".join(_LINE_MARKER.sub("", line) for line in text.split("\n"))
    text = _MARKDOWN_LINK.sub(r"\1", text)
    text = _CUSTOM_EMOJI.sub(r"\1", text)
    text = _INLINE_MARKERS.sub("", text)
    text = _UNDERSCORE_ITALIC.sub(r"\1", text)
    return " ".join(text.split())


def snippet_for(node: ComponentNode, language: SupportedLanguage, max_length: int = 40) -> str | None:
    """A short description of what `node` contains, cut off with "…" after `max_length` characters."""
    if node.kind == ComponentKind.TEXT_DISPLAY:
        text = _plain(node.content)
    elif node.kind == ComponentKind.CONTAINER:
        first = node.children[0] if node.children else None
        if first is not None and first.kind == ComponentKind.TEXT_DISPLAY:
            # A container starting with a text is best recognised by that text.
            text = _plain(first.content)
        else:
            text = t(language, "placeholders.snippet_container_children", count=len(node.children)) if node.children else ""
    elif node.kind == ComponentKind.MEDIA_GALLERY:
        text = t(language, "placeholders.snippet_gallery_items", count=len(node.gallery_items)) if node.gallery_items else ""
    else:
        text = t(language, "placeholders.snippet_visible" if node.visible else "placeholders.snippet_hidden")

    if not text:
        return None
    return text if len(text) <= max_length else f"{text[: max_length - 1]}…"


def label_for(node: ComponentNode, number: int, language: SupportedLanguage) -> str:
    kind = kind_label(language, node.kind)
    # The snippet may use whatever room the dropdown label (100 characters) has left after "Kind 1: ".
    room = MAX_SELECT_OPTION_LABEL - len(t(language, "placeholders.option_snippet", kind=kind, number=number, snippet=""))
    snippet = snippet_for(node, language, max_length=room)
    if snippet:
        return t(language, "placeholders.option_snippet", kind=kind, number=number, snippet=snippet)
    return t(language, "placeholders.option_label_empty", kind=kind, number=number)


def move_targets(session: ContainerBuilderSession, node: ComponentNode) -> list[SelectOption]:
    """Where `node` can be moved to: the message itself (if it sits in a container) and every
    other container. Containers cannot be nested, so containers themselves are never moved."""
    if node.kind == ComponentKind.CONTAINER:
        return []

    current_parent = find_parent(session, node.id)
    options: list[SelectOption] = []
    if current_parent is not None:
        options.append(
            SelectOption(label=t(session.language, "select.content.label"), value="root", emoji=MESSAGE_CONTENT_EMOJI)
        )

    containers = [candidate for candidate in session.components if candidate.kind == ComponentKind.CONTAINER]
    for index, container in enumerate(containers):
        if current_parent is not None and container.id == current_parent.id:
            continue
        options.append(
            SelectOption(
                label=label_for(container, index + 1, session.language)[:100],
                value=str(container.id),
                emoji=KIND_EMOJIS[ComponentKind.CONTAINER],
            )
        )
    return options[:25]  # Discord's select option limit


def sub_options_for(node: ComponentNode, language: SupportedLanguage) -> list[SelectOption]:
    """Options for a selected component's second dropdown (only containers have one: child kinds)."""
    if node.kind != ComponentKind.CONTAINER:
        return []

    return [
        SelectOption(
            label=f"{kind_label(language, kind)} ({sum(1 for child in node.children if child.kind == kind)})",
            value=f"child_{kind.value}",
            description=t(language, f"select.{kind.value}.description"),
            emoji=KIND_EMOJIS[kind],
        )
        for kind in ALLOWED_CHILD_KINDS
    ]
