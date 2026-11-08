from dataclasses import replace

from features.misc.builder.container.models import MAX_USER_COMPONENTS, ComponentKind, ComponentNode
from features.misc.builder.container.session import ContainerBuilderSession
from features.misc.builder.container.translations import t


def find_node(session: ContainerBuilderSession, node_id: int) -> ComponentNode | None:
    """The node with this id from the top level or a container's children, or `None`."""
    for node in session.components:
        if node.id == node_id:
            return node
        if node.kind == ComponentKind.CONTAINER:
            for child in node.children:
                if child.id == node_id:
                    return child
    return None


def find_parent(session: ContainerBuilderSession, node_id: int) -> ComponentNode | None:
    """The container owning `node_id` as a child, or `None` if it's top-level or unknown."""
    for node in session.components:
        if node.kind == ComponentKind.CONTAINER and any(child.id == node_id for child in node.children):
            return node
    return None


def get_list(session: ContainerBuilderSession, parent_id: int | None) -> list[ComponentNode]:
    """The actual, mutable list a node with this `parent_id` lives in."""
    if parent_id is None:
        return session.components

    parent = find_node(session, parent_id)
    assert parent is not None and parent.kind == ComponentKind.CONTAINER
    return parent.children


def describe_location(session: ContainerBuilderSession, parent_id: int | None) -> str:
    """Localized name of where `parent_id` lives: the main message or "Child of Container N"."""
    if parent_id is None:
        return t(session.language, "info.location.main")

    parent = find_node(session, parent_id)
    assert parent is not None
    index = session.components.index(parent) + 1
    return t(session.language, "info.location.child_of", index=index)


def node_cost(node: ComponentNode) -> int:
    """How many of the shared 40-component budget this node (plus its descendants) uses."""
    if node.kind == ComponentKind.TEXT_DISPLAY:
        return 3 if node.has_accessory else 1  # wrapped in a Section: section + text + accessory
    if node.kind == ComponentKind.CONTAINER:
        return 1 + sum(node_cost(child) for child in node.children)
    return 1


def total_cost(nodes: list[ComponentNode]) -> int:
    """Component budget used by `nodes` including all their descendants."""
    return sum(node_cost(node) for node in nodes)


def remaining_budget(session: ContainerBuilderSession) -> int:
    """How many more components the message can still hold."""
    return MAX_USER_COMPONENTS - total_cost(session.components)


def content_nodes(nodes: list[ComponentNode]) -> list[ComponentNode]:
    """The "message content" part of a top-level list: everything that is not a container."""
    return [node for node in nodes if node.kind != ComponentKind.CONTAINER]


def count_by_kind(nodes: list[ComponentNode], kind: ComponentKind) -> int:
    """How many components of `kind` exist anywhere in `nodes`, including inside containers."""
    count = 0
    for node in nodes:
        if node.kind == kind:
            count += 1
        if node.kind == ComponentKind.CONTAINER:
            count += count_by_kind(node.children, kind)
    return count


def total_text_length(nodes: list[ComponentNode]) -> int:
    """Combined text length of all text displays in `nodes`, including those inside containers."""
    total = 0
    for node in nodes:
        if node.kind == ComponentKind.TEXT_DISPLAY:
            total += len(node.content)
        elif node.kind == ComponentKind.CONTAINER:
            total += total_text_length(node.children)
    return total


def is_empty_node(node: ComponentNode) -> bool:
    """Whether `node` has no visible content yet (Discord would reject it outright)."""
    if node.kind == ComponentKind.CONTAINER:
        return not any(not is_empty_node(child) for child in node.children)
    if node.kind == ComponentKind.MEDIA_GALLERY:
        return not node.gallery_items
    # a TextDisplay's content is required at creation time and a Separator is always
    # meaningful on its own, so neither can end up empty here.
    return False


def non_empty_nodes(nodes: list[ComponentNode]) -> list[ComponentNode]:
    """Filter out components with no visible content, for the payload actually sent."""
    result: list[ComponentNode] = []
    for node in nodes:
        if node.kind == ComponentKind.CONTAINER:
            filtered_children = non_empty_nodes(node.children)
            if filtered_children:
                result.append(replace(node, children=filtered_children))
            continue

        if not is_empty_node(node):
            result.append(node)

    return result


def count_nodes(nodes: list[ComponentNode]) -> int:
    """Number of `nodes` including all nested children."""
    return sum(1 + count_nodes(node.children) for node in nodes)


def component_media_urls(nodes: list[ComponentNode]) -> list[str]:
    """Every distinct `http(s)` media URL used across `nodes`, in first-seen order. These are the
    uploaded attachments a template restores - Discord serves them behind signed, expiring URLs."""
    urls: list[str] = []
    for node in nodes:
        candidates = [node.thumbnail_url, *(item.media_url for item in node.gallery_items)]
        for url in (*candidates, *component_media_urls(node.children)):
            if url and url.startswith(("http://", "https://")) and url not in urls:
                urls.append(url)
    return urls


def truncate_to_budget(nodes: list[ComponentNode], budget: int) -> list[ComponentNode]:
    """The longest in-order prefix of `nodes` that fits `budget` components. A container that only
    partly fits is kept with as many of its leading children as fit."""
    kept: list[ComponentNode] = []
    remaining = budget
    for node in nodes:
        cost = node_cost(node)
        if cost <= remaining:
            kept.append(node)
            remaining -= cost
            continue

        if node.kind == ComponentKind.CONTAINER and remaining >= 1:
            node.children = truncate_to_budget(node.children, remaining - 1)
            kept.append(node)
        break
    return kept
