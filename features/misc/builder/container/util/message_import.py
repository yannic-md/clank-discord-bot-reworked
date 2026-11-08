from discord import Message
from discord import components as api_components

from core.discord_api.limits import MAX_V2_TEXT_DISPLAY_LENGTH
from features.misc.builder.container.models import MAX_USER_COMPONENTS, ComponentKind, ComponentNode, GalleryItem
from features.misc.builder.container.session import ContainerBuilderSession
from features.misc.builder.container.translations import t
from features.misc.builder.container.util.tree import total_cost, truncate_to_budget


def _convert_component(
    session: ContainerBuilderSession, component: api_components.Component, *, nested: bool
) -> tuple[ComponentNode | None, int]:
    """Convert one received component into a node. Returns the node (or `None` if the whole component is
    unsupported) and how many unsupported parts had to be dropped."""
    if isinstance(component, api_components.TextDisplay):
        return ComponentNode(id=session.new_id(), kind=ComponentKind.TEXT_DISPLAY, content=component.content), 0

    if isinstance(component, api_components.SectionComponent):
        texts = [child.content for child in component.children if isinstance(child, api_components.TextDisplay)]
        node = ComponentNode(id=session.new_id(), kind=ComponentKind.TEXT_DISPLAY, content="\n".join(texts))
        accessory = component.accessory
        if isinstance(accessory, api_components.ThumbnailComponent):
            node.thumbnail_url = accessory.media.url
            node.thumbnail_description = accessory.description
            node.thumbnail_spoiler = accessory.spoiler
            return node, 0
        return node, 1  # a button accessory can't be represented

    if isinstance(component, api_components.MediaGalleryComponent):
        gallery = ComponentNode(id=session.new_id(), kind=ComponentKind.MEDIA_GALLERY)
        gallery.gallery_items = [
            GalleryItem(media_url=item.media.url, description=item.description, spoiler=item.spoiler)
            for item in component.items
        ]
        return gallery, 0

    if isinstance(component, api_components.SeparatorComponent):
        separator = ComponentNode(
            id=session.new_id(), kind=ComponentKind.SEPARATOR, visible=component.visible, spacing=component.spacing
        )
        return separator, 0

    if isinstance(component, api_components.Container) and not nested:
        container = ComponentNode(
            id=session.new_id(),
            kind=ComponentKind.CONTAINER,
            accent_colour=component.accent_colour,
            spoiler=component.spoiler,
        )
        unsupported = 0
        for child in component.children:
            child_node, child_unsupported = _convert_component(session, child, nested=True)
            unsupported += child_unsupported
            if child_node is not None:
                container.children.append(child_node)
        return container, unsupported

    return None, 1


def load_message_into_session(
    session: ContainerBuilderSession, message: Message, bot_user_id: int
) -> tuple[str | None, str | None]:
    """Load `message` into the session: the bot's own messages are edited in place, anyone else's
    are copied (and later sent as a new message).

    Returns `(fatal_error, notice)`: a fatal error means nothing was loaded, a notice is a hint to
    show on the first screen (e.g. that parts of the message couldn't be taken over).
    """
    is_own = message.author.id == bot_user_id

    if not message.flags.components_v2:
        # Classic messages can't be turned into Components v2 messages by editing, so only a copy of the text works.
        text = message.content.strip()[:MAX_V2_TEXT_DISPLAY_LENGTH]
        if not text:
            return t(session.language, "errors.load_nothing_usable"), None

        session.components = [ComponentNode(id=session.new_id(), kind=ComponentKind.TEXT_DISPLAY, content=text)]
        return None, t(session.language, "info.load.not_v2")

    nodes: list[ComponentNode] = []
    unsupported = 0
    for component in message.components:
        node, dropped = _convert_component(session, component, nested=False)
        unsupported += dropped
        if node is not None:
            nodes.append(node)

    if not nodes:
        return t(session.language, "errors.load_no_supported"), None

    # Anything beyond the builder's budget is cut off (in order), so the rest of the message is still usable.
    original_cost = total_cost(nodes)
    truncated = original_cost > MAX_USER_COMPONENTS
    if truncated:
        nodes = truncate_to_budget(nodes, MAX_USER_COMPONENTS)

    session.components = nodes
    notices: list[str] = []
    if truncated:
        notices.append(
            t(
                session.language,
                "info.load.truncated",
                original=original_cost,
                max=MAX_USER_COMPONENTS,
                kept=total_cost(nodes),
            )
        )
    if unsupported:
        notices.append(t(session.language, "info.load.unsupported", count=unsupported))

    # Saving over the original would permanently delete everything that wasn't taken over, so such
    # messages are only ever loaded as a copy.
    if is_own and not notices:
        session.edit_mode = True
        session.target_message = message
    elif is_own:
        notices.append(t(session.language, "info.load.copy_only"))

    return None, "\n".join(notices) or None
