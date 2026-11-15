from typing import Protocol

from discord import Colour, SeparatorSpacing

from core.db.repositories.container_builder import container_template_repository as template_repo
from core.discord_api.limits import (
    MAX_EMBED_URL,
    MAX_V2_MEDIA_GALLERY_ITEM_DESCRIPTION,
    MAX_V2_MEDIA_GALLERY_ITEMS,
    MAX_V2_TEXT_DISPLAY_LENGTH,
    MAX_V2_THUMBNAIL_DESCRIPTION,
)
from features.misc.builder.container.models import (
    MAX_USER_COMPONENTS,
    ComponentKind,
    ComponentNode,
    ContainerTemplate,
    GalleryItem,
)
from features.misc.builder.container.util.placement import placed_item_ids
from features.misc.builder.container.util.tree import total_cost, truncate_to_budget
from features.misc.builder.interactive.draft import (
    BUTTONS_PER_ROW,
    InteractiveLibrary,
    ItemDraft,
    adopt_forms,
    row_has_room,
    template_data,
)
from features.misc.builder.session import WebhookSender


class TemplateContext(Protocol):
    """What rebuilding stored nodes needs: a source of node ids, the library to put their buttons in, and the
    sender identity (a custom sender allows link buttons only). The builder session provides all of it."""

    library: InteractiveLibrary
    webhook: WebhookSender

    def new_id(self) -> int:
        """Hand out the next unused node id."""
        ...


def node_to_data(node: ComponentNode, library: InteractiveLibrary) -> dict[str, object]:
    """Serialize a node and its children into the JSON-able dict stored in a template.

    The buttons of a row (or next to a text) are stored inline, as part of that node: a template carries
    its own copy of their definitions, independent of the library of the session that saved it.
    """
    data: dict[str, object] = {"kind": node.kind.value}
    if node.kind == ComponentKind.TEXT_DISPLAY:
        data["content"] = node.content
        if node.has_thumbnail:
            data["thumbnail_url"] = node.thumbnail_url
            data["thumbnail_description"] = node.thumbnail_description
            data["thumbnail_spoiler"] = node.thumbnail_spoiler

        elif node.accessory_item_id is not None and (draft := library.get(node.accessory_item_id)) is not None:
            data["button"] = template_data(library, draft)

    elif node.kind == ComponentKind.CONTAINER:
        data["accent_colour"] = node.accent_colour.value if node.accent_colour is not None else None
        data["spoiler"] = node.spoiler
        data["children"] = [node_to_data(child, library) for child in node.children]

    elif node.kind == ComponentKind.ACTION_ROW:
        drafts = (library.get(item_id) for item_id in node.item_ids)
        data["items"] = [template_data(library, draft) for draft in drafts if draft is not None]

    elif node.kind == ComponentKind.MEDIA_GALLERY:
        data["items"] = [
            {"media_url": item.media_url, "description": item.description, "spoiler": item.spoiler}
            for item in node.gallery_items
        ]
    else:
        data["visible"] = node.visible
        data["spacing"] = node.spacing.value
    return data


def _optional_text(value: object, max_length: int) -> str | None:
    """`value` cut to `max_length`, or `None` if it is not a non-empty string."""
    return value[:max_length] if isinstance(value, str) and value else None


def _drafts(session: TemplateContext, item_ids: list[int]) -> list[ItemDraft]:
    """The items of the library with these ids."""
    drafts = (session.library.get(item_id) for item_id in item_ids)
    return [draft for draft in drafts if draft is not None]


def _draft_from_data(session: TemplateContext, data: object) -> ItemDraft | None:
    """Add the stored button or dropdown - and the forms it opens - to the session's library; `None` if it is
    unusable or the library is full. `form_map` remembers the forms created while loading this template."""
    if session.library.is_full:
        return None

    draft: ItemDraft | None = ItemDraft.from_data(0, data)
    if draft is None:
        return None

    # Buttons that run actions cannot be sent through a webhook, so a template's are left out then.
    if session.webhook.enabled and not draft.is_link:
        return None

    session.library.add(draft)
    adopt_forms(session.library, draft, data.get("forms") if isinstance(data, dict) else None)
    return draft


def node_from_data(session: TemplateContext, data: object, *, nested: bool) -> tuple[ComponentNode | None, int]:
    """Rebuild one node from its stored payload. Returns the node (`None` if the payload is unusable)
    and how many stored components had to be dropped on the way. Never trusts the payload: the row may
    be hand-edited or written by an older version."""
    if not isinstance(data, dict):
        return None, 1

    try:
        kind = ComponentKind(data.get("kind"))
    except ValueError:
        return None, 1

    if kind == ComponentKind.TEXT_DISPLAY:
        content = _optional_text(data.get("content"), MAX_V2_TEXT_DISPLAY_LENGTH)
        if content is None:
            return None, 1

        node = ComponentNode(id=session.new_id(), kind=kind, content=content)
        thumbnail_url = _optional_text(data.get("thumbnail_url"), MAX_EMBED_URL)
        if thumbnail_url is not None:
            node.thumbnail_url = thumbnail_url
            node.thumbnail_description = _optional_text(data.get("thumbnail_description"), MAX_V2_THUMBNAIL_DESCRIPTION)
            node.thumbnail_spoiler = data.get("thumbnail_spoiler") is True
            return node, 0

        if "button" in data:
            draft = _draft_from_data(session, data["button"])
            if draft is not None and draft.is_select:  # only a button can sit next to a text
                session.library.remove(draft.id)
                draft = None
            if draft is None:
                return node, 1
            node.accessory_item_id = draft.id

        return node, 0

    if kind == ComponentKind.CONTAINER:
        if nested:  # Discord rejects containers inside containers
            return None, 1

        container = ComponentNode(id=session.new_id(), kind=kind, spoiler=data.get("spoiler") is True)
        colour = data.get("accent_colour")
        if isinstance(colour, int) and not isinstance(colour, bool) and 0 <= colour <= 0xFFFFFF:
            container.accent_colour = Colour(colour)

        dropped = 0
        children = data.get("children")
        for child_data in children if isinstance(children, list) else []:
            child, child_dropped = node_from_data(session, child_data, nested=True)
            dropped += child_dropped
            if child is not None:
                container.children.append(child)
        return container, dropped

    if kind == ComponentKind.ACTION_ROW:
        row: ComponentNode = ComponentNode(id=session.new_id(), kind=kind)
        stored = data.get("items")
        dropped = 0
        for item_data in stored if isinstance(stored, list) else []:
            draft = _draft_from_data(session, item_data) if len(row.item_ids) < BUTTONS_PER_ROW else None
            if draft is not None and not row_has_room(_drafts(session, row.item_ids), draft):
                session.library.remove(draft.id)
                draft = None
            if draft is None:
                dropped += 1
                continue
            row.item_ids.append(draft.id)
        return row, dropped

    if kind == ComponentKind.MEDIA_GALLERY:
        gallery = ComponentNode(id=session.new_id(), kind=kind)
        items = data.get("items")
        dropped = 0
        for item_data in items if isinstance(items, list) else []:
            media_url = _optional_text(item_data.get("media_url"), MAX_EMBED_URL) if isinstance(item_data, dict) else None
            if media_url is None or len(gallery.gallery_items) >= MAX_V2_MEDIA_GALLERY_ITEMS:
                dropped += 1
                continue
            description = _optional_text(item_data.get("description"), MAX_V2_MEDIA_GALLERY_ITEM_DESCRIPTION)
            gallery.gallery_items.append(
                GalleryItem(media_url=media_url, description=description, spoiler=item_data.get("spoiler") is True)
            )
        return gallery, dropped

    try:
        spacing = SeparatorSpacing(data.get("spacing"))
    except ValueError:
        spacing = SeparatorSpacing.small
    separator = ComponentNode(id=session.new_id(), kind=kind, visible=data.get("visible") is not False, spacing=spacing)
    return separator, 0


def nodes_from_data(session: TemplateContext, data: list[dict[str, object]]) -> tuple[list[ComponentNode], int]:
    """Rebuild a whole stored component tree; the second value is how many components were dropped."""
    nodes: list[ComponentNode] = []
    dropped = 0
    known_items: set[int] = set(session.library.items)
    for node_data in data:
        node, node_dropped = node_from_data(session, node_data, nested=False)
        dropped += node_dropped
        if node is not None:
            nodes.append(node)

    # A stored payload can never legitimately exceed the budget, but a hand-edited row must not
    # crash the screens (Discord's hard 40-component cap) - cut it down like an oversized message.
    if total_cost(nodes) > MAX_USER_COMPONENTS:
        nodes = truncate_to_budget(nodes, MAX_USER_COMPONENTS)

    # Buttons of components that did not make it must not linger in the library as unplaced leftovers.
    kept: set[int] = set(placed_item_ids(nodes))
    kept_drafts: list[ItemDraft] = [draft for item_id in kept if (draft := session.library.get(item_id)) is not None]
    kept |= {form.id for form in session.library.referenced_forms(kept_drafts)}
    for item_id in set(session.library.items) - known_items - kept:
        session.library.remove(item_id)
    return nodes, dropped


async def load_user_templates(user_id: int) -> list[ContainerTemplate]:
    """Every template owned by a user, ordered by name."""
    return [
        ContainerTemplate(name=record.name, icon=record.icon, components=record.components_data)
        for record in await template_repo.list_user_templates(user_id)
    ]


async def save_user_template(user_id: int, template: ContainerTemplate) -> None:
    """Persist a template for a user, replacing an existing one of the same name."""
    await template_repo.upsert_user_template(
        user_id=user_id, name=template.name, icon=template.icon, components_data=template.components
    )


async def delete_user_template(user_id: int, name: str) -> None:
    """Delete the template `name` of the user."""
    await template_repo.delete_user_template(user_id, name)
