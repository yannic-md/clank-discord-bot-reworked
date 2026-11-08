from dataclasses import dataclass, field
from enum import Enum

from discord import Colour, SeparatorSpacing

from core.discord_api.limits import MAX_V2_TOTAL_COMPONENTS

# Both the main screen and the send-confirmation screen render the user's whole component
# tree alongside their own chrome, so the practical cap on the user's own content has to
# leave room for whichever screen's chrome is bigger - the main screen's: a 4-button
# ActionRow (5) and a select ActionRow (2) = 7.
_RESERVED_CHROME_BUDGET: int = 7


MAX_USER_COMPONENTS: int = MAX_V2_TOTAL_COMPONENTS - _RESERVED_CHROME_BUDGET


class ComponentKind(Enum):
    """The kinds of component the container builder can create."""

    TEXT_DISPLAY = "text_display"
    CONTAINER = "container"
    MEDIA_GALLERY = "media_gallery"
    SEPARATOR = "separator"


KIND_EMOJIS: dict[ComponentKind, str] = {
    ComponentKind.TEXT_DISPLAY: "📝",
    ComponentKind.CONTAINER: "📦",
    ComponentKind.MEDIA_GALLERY: "🖼️",
    ComponentKind.SEPARATOR: "📏",
}


# Discord rejects a Container nested inside another Container, so CONTAINER is deliberately
# excluded here - a container can only ever hold these three kinds as children.
ALLOWED_CHILD_KINDS: tuple[ComponentKind, ...] = (
    ComponentKind.TEXT_DISPLAY,
    ComponentKind.MEDIA_GALLERY,
    ComponentKind.SEPARATOR,
)


MESSAGE_CONTENT_VALUE: str = "message_content"


MESSAGE_CONTENT_EMOJI: str = "💬"


ORDER_VALUE: str = "order"


@dataclass
class GalleryItem:
    """One image or video of a media gallery."""

    media_url: str
    description: str | None = None
    spoiler: bool = False


@dataclass
class ComponentNode:
    """One user-authored component. Which fields are meaningful depends on `kind` -
    e.g. `content` is only used for `TEXT_DISPLAY`, `children` only for `CONTAINER`.

    This is the builder's own in-memory data model, not a `discord.ui` object - it gets
    converted into real `discord.ui` items only when something actually needs rendering
    (see `build_item`/`build_items`), the same way the embed-builder keeps `discord.Embed`
    objects around as its live state.
    """

    id: int
    kind: ComponentKind

    content: str = ""  # text_display
    thumbnail_url: str | None = None  # text_display accessory
    thumbnail_description: str | None = None
    thumbnail_spoiler: bool = False

    children: list[ComponentNode] = field(default_factory=list)  # container
    accent_colour: Colour | None = None  # container
    spoiler: bool = False  # container

    gallery_items: list[GalleryItem] = field(default_factory=list)  # media_gallery

    visible: bool = True  # separator
    spacing: SeparatorSpacing = SeparatorSpacing.small  # separator

    @property
    def has_accessory(self) -> bool:
        """Whether this text display has a thumbnail (and is thus rendered as a section)."""
        return self.thumbnail_url is not None


@dataclass(frozen=True, slots=True)
class ContainerTemplate:
    """A saved container-builder draft. `components` is the raw JSON-able payload (see
    `node_to_data`); it is only rebuilt into nodes when the template is actually loaded."""

    name: str
    icon: str
    components: list[dict[str, object]]
