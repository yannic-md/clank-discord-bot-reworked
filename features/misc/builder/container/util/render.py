from discord import Colour
from discord.ui import ActionRow, Container, Item, LayoutView, MediaGallery, Section, Separator, TextDisplay, Thumbnail

from features.misc.builder.container.models import ComponentKind, ComponentNode
from features.misc.builder.container.session import ContainerBuilderSession
from features.misc.builder.container.util.tree import find_parent
from features.misc.builder.interactive.draft import InteractiveLibrary, ItemDraft
from features.misc.builder.interactive.render import final_component, preview_component


def _button(library: InteractiveLibrary, item_id: int, final: bool) -> Item | None:
    """The discord.py button for a library entry, as shown in a builder preview or in the sent message."""
    draft: ItemDraft | None = library.get(item_id)
    if draft is None:
        return None

    return final_component(draft) if final else preview_component(draft)


def build_item(node: ComponentNode, library: InteractiveLibrary, *, final: bool = False) -> Item:
    """Convert a component node into the matching discord.py item.

    Buttons and dropdowns are built for a builder preview (disabled) unless `final` is set: then they are the real
    ones of the message that is sent, which requires the interactive ones to be stored.
    """
    if node.kind == ComponentKind.TEXT_DISPLAY:
        text_display: TextDisplay = TextDisplay(node.content)
        if node.accessory_item_id is not None:
            button = _button(library, node.accessory_item_id, final)
            if button is not None:
                return Section(text_display, accessory=button)

        if node.has_thumbnail:
            assert node.thumbnail_url is not None
            thumbnail: Thumbnail = Thumbnail(
                node.thumbnail_url, description=node.thumbnail_description, spoiler=node.thumbnail_spoiler
            )
            return Section(text_display, accessory=thumbnail)
        return text_display

    if node.kind == ComponentKind.CONTAINER:
        container: Container = Container(accent_colour=node.accent_colour, spoiler=node.spoiler)
        for child in node.children:
            container.add_item(build_item(child, library, final=final))
        return container

    if node.kind == ComponentKind.MEDIA_GALLERY:
        gallery: MediaGallery = MediaGallery()
        for item in node.gallery_items:
            gallery.add_item(media=item.media_url, description=item.description, spoiler=item.spoiler)
        return gallery

    if node.kind == ComponentKind.ACTION_ROW:
        row: ActionRow = ActionRow()
        for item_id in node.item_ids:
            button = _button(library, item_id, final)
            if button is not None:
                row.add_item(button)
        return row

    return Separator(visible=node.visible, spacing=node.spacing)


def preview_item(session: ContainerBuilderSession, node: ComponentNode) -> Item:
    """`build_item` for a builder preview: children of a container are wrapped in a container
    (using the parent's accent colour) so it's visible that they live inside one."""
    item = build_item(node, session.library)
    parent = find_parent(session, node.id)
    if parent is None:
        return item

    return Container(item, accent_colour=parent.accent_colour)


def preview_items(session: ContainerBuilderSession, nodes: list[ComponentNode]) -> list[Item]:
    """Convert `nodes` into discord.py items for a builder preview, keeping their order."""
    return [build_item(node, session.library) for node in nodes]


def final_items(session: ContainerBuilderSession, nodes: list[ComponentNode]) -> list[Item]:
    """Convert `nodes` into the items of the message that is actually sent (interactive buttons must be stored)."""
    return [build_item(node, session.library, final=True) for node in nodes]


class StaticLayoutView(LayoutView):
    """A plain, non-interactive `LayoutView` for one-off confirmation/success screens
    and for the final message actually sent to the channel."""

    def __init__(self, items: list[Item]) -> None:
        """Wrap `items` in a view that never times out."""
        super().__init__(timeout=None)
        for item in items:
            self.add_item(item)


def text_message_view(text: str, *, colour: Colour | None = None) -> StaticLayoutView:
    """Wrap `text` in a view - inside an accent-coloured container if `colour` is given."""
    content: Item = TextDisplay(text)
    if colour is not None:
        content = Container(content, accent_colour=colour)
    return StaticLayoutView([content])
