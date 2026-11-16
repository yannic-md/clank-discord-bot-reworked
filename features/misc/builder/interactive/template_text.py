from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from typing import Any

from discord import Embed

from core.discord_api.limits import (
    MAX_EMBED_AUTHOR_NAME,
    MAX_EMBED_DESCRIPTION,
    MAX_EMBED_FIELD_NAME,
    MAX_EMBED_FIELD_VALUE,
    MAX_EMBED_FOOTER_TEXT,
    MAX_EMBED_GLOBAL_TEXT,
    MAX_EMBED_TITLE,
    MAX_V2_MEDIA_GALLERY_ITEM_DESCRIPTION,
    MAX_V2_TEXT_DISPLAY_LENGTH,
    MAX_V2_THUMBNAIL_DESCRIPTION,
    MAX_V2_TOTAL_TEXT_LENGTH,
)
from core.enums.language import SupportedLanguage
from features.misc.builder.container.models import ComponentKind, ComponentNode
from features.misc.builder.interactive.messages import t
from features.misc.builder.interactive.variables import find_variables

ELLIPSIS: str = "…"
PARAGRAPH_BREAK: str = "\n\n"
"""Sets two hints of the same message apart: a blank line between them."""
MAX_LISTED_VARIABLES: int = 8
"""How many variables the notice names; a template that uses more gets "…" behind the last."""


@dataclass(frozen=True, slots=True)
class TextSlot:
    """One text of a template: what it says, how long Discord lets it be, and how to put another text in its place."""

    text: str
    limit: int
    write: Callable[[str], None]
    counted: bool = True
    """Whether it counts towards the limit for all the text of one message."""


def _dict_slot(owner: dict[str, Any], key: str, limit: int) -> TextSlot | None:
    """The text at `key` of a stored embed (or of a part of it), if it has one."""
    value = owner.get(key)
    if not isinstance(value, str) or not value:
        return None
    return TextSlot(value, limit, lambda text: owner.__setitem__(key, text))


def embed_slots(entry: object) -> list[TextSlot]:
    """The texts of a stored embed (its dict form): title, description, the names and values of the fields, the text of the
    footer and the name of the author. Writing to a slot changes `entry`. What is stored is never trusted: anything that is
    not shaped like an embed has no texts."""
    if not isinstance(entry, dict):
        return []

    candidates: list[TextSlot | None] = [
        _dict_slot(entry, "title", MAX_EMBED_TITLE),
        _dict_slot(entry, "description", MAX_EMBED_DESCRIPTION),
    ]
    embed_fields = entry.get("fields")
    for embed_field in embed_fields if isinstance(embed_fields, list) else []:
        if isinstance(embed_field, dict):
            candidates.append(_dict_slot(embed_field, "name", MAX_EMBED_FIELD_NAME))
            candidates.append(_dict_slot(embed_field, "value", MAX_EMBED_FIELD_VALUE))
    footer, author = entry.get("footer"), entry.get("author")
    if isinstance(footer, dict):
        candidates.append(_dict_slot(footer, "text", MAX_EMBED_FOOTER_TEXT))
    if isinstance(author, dict):
        candidates.append(_dict_slot(author, "name", MAX_EMBED_AUTHOR_NAME))
    return [slot for slot in candidates if slot is not None]


def _attribute_slot(owner: object, name: str, limit: int, *, counted: bool = True) -> TextSlot | None:
    """The text in the attribute `name` of a component (or of an item of a gallery), if it has one."""
    value = getattr(owner, name)
    if not isinstance(value, str) or not value:
        return None
    return TextSlot(value, limit, lambda text: setattr(owner, name, text), counted=counted)


def node_slots(nodes: Sequence[ComponentNode]) -> list[TextSlot]:
    """The texts of container components (and of those inside containers): the text of every text display, and the
    descriptions of thumbnails and gallery items. Writing to a slot changes the component."""
    candidates: list[TextSlot | None] = []
    for node in nodes:
        if node.kind is ComponentKind.TEXT_DISPLAY:
            candidates.append(_attribute_slot(node, "content", MAX_V2_TEXT_DISPLAY_LENGTH))
            candidates.append(_attribute_slot(node, "thumbnail_description", MAX_V2_THUMBNAIL_DESCRIPTION, counted=False))
        elif node.kind is ComponentKind.MEDIA_GALLERY:
            candidates.extend(
                _attribute_slot(item, "description", MAX_V2_MEDIA_GALLERY_ITEM_DESCRIPTION, counted=False)
                for item in node.gallery_items
            )
        elif node.kind is ComponentKind.CONTAINER:
            candidates.extend(node_slots(node.children))
    return [slot for slot in candidates if slot is not None]


def embed_template_texts(content: str, embeds: Iterable[Embed]) -> list[str]:
    """Every text of an embed template: the text of the message and the texts of its embeds."""
    texts = [content] if content else []
    for embed in embeds:
        texts.extend(slot.text for slot in embed_slots(embed.to_dict()))
    return texts


def container_template_texts(nodes: Sequence[ComponentNode]) -> list[str]:
    """Every text of a container template."""
    return [slot.text for slot in node_slots(nodes)]


def fit_texts(texts: list[str], budget: int) -> list[str]:
    """The texts with the last ones cut short - each keeps at least one character, and "…" where it was cut - until all
    of them together fit `budget`."""
    fitted = list(texts)
    excess = sum(len(text) for text in fitted) - budget
    for index in reversed(range(len(fitted))):
        if excess <= 0:
            break
        cut = min(excess, len(fitted[index]) - 1)
        if cut <= 0:
            continue
        fitted[index] = fitted[index][: len(fitted[index]) - cut - 1] + ELLIPSIS
        excess -= cut
    return fitted


def fill_slots(slots: Sequence[TextSlot], render: Callable[[str], str], *, budget: int) -> None:
    """Replace the text of every slot by `render(text)`. Each text stays within what Discord allows for it, and all
    counted ones together within `budget`: what is too long is cut short, as the filled-in variables (the answers of a
    form, for example) can make a text longer than the template ever was."""
    rendered: list[str] = []
    for slot in slots:
        text = render(slot.text)
        if not text.strip():  # a variable that stands for nothing must not leave the text empty
            text = slot.text
        if len(text) > slot.limit:
            text = text[: slot.limit - 1] + ELLIPSIS
        rendered.append(text)

    counted = [index for index, slot in enumerate(slots) if slot.counted]
    for index, text in zip(counted, fit_texts([rendered[index] for index in counted], budget), strict=True):
        rendered[index] = text
    for slot, text in zip(slots, rendered, strict=True):
        slot.write(text)


def fill_embeds(entries: Sequence[dict[str, Any]], render: Callable[[str], str]) -> None:
    """Fill the variables into the texts of stored embeds (their dict form) - all of them together stay within what a
    message may hold."""
    fill_slots([slot for entry in entries for slot in embed_slots(entry)], render, budget=MAX_EMBED_GLOBAL_TEXT)


def fill_nodes(nodes: Sequence[ComponentNode], render: Callable[[str], str]) -> None:
    """Fill the variables into the texts of container components - all texts of the message together stay within what
    Discord allows."""
    fill_slots(node_slots(nodes), render, budget=MAX_V2_TOTAL_TEXT_LENGTH)


@dataclass(frozen=True, slots=True)
class SaveStatus:
    """What to tell someone who has just saved a template."""

    text: str
    warning: bool
    """Whether it is more than a hint: some of the variables in the template do not exist."""


def _listed(names: Sequence[str]) -> str:
    """The variables as code spans, separated by commas - the first few only."""
    shown = ", ".join(f"`{{{name}}}`" for name in names[:MAX_LISTED_VARIABLES])
    return f"{shown} {ELLIPSIS}" if len(names) > MAX_LISTED_VARIABLES else shown


def variables_notice(language: SupportedLanguage, texts: Iterable[str]) -> SaveStatus | None:
    """What to tell about the variables in the `texts` of a template that is saved - or `None` if it uses none.

    A template is sent the normal way as it is, so its variables stay as typed there; a message action fills them in.
    A name in curly braces that is no variable at all - a typo - is never replaced, which is worth knowing."""
    known, unknown = find_variables(texts)
    paragraphs: list[str] = []
    if known:
        paragraphs.append(t(language, "template_variables.known", variables=_listed(known)))
    if unknown:
        paragraphs.append(t(language, "template_variables.unknown", count=len(unknown), variables=_listed(unknown)))
    if not paragraphs:
        return None
    return SaveStatus(PARAGRAPH_BREAK.join(paragraphs), warning=bool(unknown))


def saved_status(confirmation: str, notice: SaveStatus | None) -> SaveStatus:
    """What to tell someone who has just saved a template: the `confirmation` that it is saved and, below it, the notice
    about its variables (if it uses any). The whole is a warning if the notice is one."""
    if notice is None:
        return SaveStatus(confirmation, warning=False)
    return SaveStatus(f"{confirmation}{PARAGRAPH_BREAK}{notice.text}", warning=notice.warning)
