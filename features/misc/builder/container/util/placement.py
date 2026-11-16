import copy
from collections.abc import Iterator
from dataclasses import dataclass, replace

from discord import SelectOption

from features.misc.builder.container.models import KIND_EMOJIS, ComponentKind, ComponentNode
from features.misc.builder.container.session import ContainerBuilderSession
from features.misc.builder.container.translations import t
from features.misc.builder.container.util.options import label_for, snippet_for
from features.misc.builder.container.util.tree import remaining_budget
from features.misc.builder.interactive.draft import ItemDraft, row_has_room
from features.misc.builder.interactive.editor import draft_name, fit_lines
from features.misc.builder.interactive.messages import t as shared_t

NEW_ROW_COST: int = 2
"""A new row uses the row itself plus its first button."""
ACCESSORY_COST: int = 2
"""A button next to a text turns the text into a section: section + text + button instead of just the text."""

UNPLACE_VALUE: str = "unplace"
NEW_ROW_MESSAGE_VALUE: str = "new_row:root"
"""The place "a new row in the message" - the one place that always exists."""
PREVIEW_ROWS: int = 3
"""How many rows of the placed buttons the placement screen previews: the rest of the 40 components a message may
have are used by its own controls."""
OUTLINE_BUDGET: int = 1800
"""How many characters of the placement screen the outline of the message may take: a text holds 4000, and the screen
has an explanation and a hint besides."""
OUTLINE_SNIPPET: int = 30
"""How many characters of a text or container the outline shows."""
TREE_MIDDLE: str = "┣"
TREE_LAST: str = "┗"
"""What leads a line of the contents of a container: every one but the last, and the last."""


@dataclass(frozen=True, slots=True)
class Placement:
    """Where one button currently sits: `node` is its row, or the text it sits next to."""

    node: ComponentNode
    parent: ComponentNode | None
    """The container holding `node`, or `None` if it sits directly in the message."""


def iter_nodes(nodes: list[ComponentNode]) -> Iterator[tuple[ComponentNode, ComponentNode | None]]:
    """Every node of the tree together with the container holding it (`None` for the top level)."""
    for node in nodes:
        yield node, None
        if node.kind == ComponentKind.CONTAINER:
            for child in node.children:
                yield child, node


def placed_item_ids(nodes: list[ComponentNode]) -> list[int]:
    """The ids of all buttons placed anywhere in the tree, in the order they appear in the message."""
    ids: list[int] = []
    for node, _ in iter_nodes(nodes):
        if node.kind == ComponentKind.ACTION_ROW:
            ids.extend(node.item_ids)
        elif node.accessory_item_id is not None:
            ids.append(node.accessory_item_id)
    return ids


def find_placement(session: ContainerBuilderSession, item_id: int) -> Placement | None:
    """Where the button sits, or `None` if it is not placed in the message."""
    for node, parent in iter_nodes(session.components):
        if item_id in node.item_ids or node.accessory_item_id == item_id:
            return Placement(node, parent)
    return None


def describe_placement(session: ContainerBuilderSession, item_id: int) -> str | None:
    """Localized description of where the button sits, or `None` if it is not placed."""
    placement = find_placement(session, item_id)
    if placement is None:
        return None

    if placement.node.kind == ComponentKind.ACTION_ROW:
        return _row_label(session, placement.node, placement.parent)

    return t(session.language, "info.placement.text", text=snippet_for(placement.node, session.language, 30) or "…")


def _row_position(
    session: ContainerBuilderSession, row: ComponentNode, parent: ComponentNode | None
) -> tuple[int | None, int]:
    """Which container the row is in (`None` for the message itself) and its number: rows are counted within the list
    that holds them."""
    siblings = parent.children if parent else session.components
    number = [node for node in siblings if node.kind == ComponentKind.ACTION_ROW].index(row) + 1
    if parent is None:
        return None, number
    containers = [node for node in session.components if node.kind == ComponentKind.CONTAINER]
    return containers.index(parent) + 1, number


def _row_label(session: ContainerBuilderSession, row: ComponentNode, parent: ComponentNode | None) -> str:
    """ "In the message - row 2" / "In container 1 - row 1"."""
    container, number = _row_position(session, row, parent)
    if container is None:
        return t(session.language, "info.placement.message_row", row=number)
    return t(session.language, "info.placement.container_row", container=container, row=number)


def _short_row_label(session: ContainerBuilderSession, row: ComponentNode, parent: ComponentNode | None) -> str:
    """ "Row 2" / "Container 1, row 1": a row named short enough to lead a line in a list."""
    container, number = _row_position(session, row, parent)
    if container is None:
        return t(session.language, "info.placement.short_row", row=number)
    return t(session.language, "info.placement.short_container_row", container=container, row=number)


def placement_label(session: ContainerBuilderSession, item_id: int) -> str | None:
    """Where the button sits, short enough to lead a line in a list: "Row 2", "Container 1, row 1" or "Next to a
    text"; `None` if it is not placed."""
    placement = find_placement(session, item_id)
    if placement is None:
        return None
    if placement.node.kind != ComponentKind.ACTION_ROW:
        return t(session.language, "info.placement.short_text")

    return _short_row_label(session, placement.node, placement.parent)


def has_placed_items(session: ContainerBuilderSession) -> bool:
    """Whether any button of the library sits in the message - in a row, or next to a text."""
    for node, _ in iter_nodes(session.components):
        if node.kind == ComponentKind.ACTION_ROW and _row_drafts(session, node):
            return True
        if node.accessory_item_id is not None and session.library.get(node.accessory_item_id) is not None:
            return True
    return False


def preview_rows(session: ContainerBuilderSession) -> list[list[ItemDraft]]:
    """The rows of placed buttons, as items, in the order of the message - what the placement screen previews (a button
    next to a text is no row)."""
    rows = (
        _row_drafts(session, node) for node, _ in iter_nodes(session.components) if node.kind == ComponentKind.ACTION_ROW
    )
    return [drafts for drafts in rows if drafts]


def message_outline(session: ContainerBuilderSession, *, marked: int | None = None) -> str:
    """The whole message as a list, from top to bottom: every text, container, gallery, separator and row of buttons,
    with what sits in a row or next to a text (" ➜ "), and the contents of a container below it. A button can go
    anywhere in a message, so what the buttons are placed among is what makes their places clear. The button `marked`
    stands out in bold. The numbers are those of the places the dropdown offers; what does not fit is summed up."""
    language = session.language
    counts: dict[ComponentKind, int] = {}

    def names(item_ids: list[int]) -> str:
        """The buttons (and dropdowns) with these ids, named as in the lists of the builder."""
        named = []
        for item_id in item_ids:
            draft = session.library.get(item_id)
            if draft is not None:
                name = draft_name(language, draft)
                named.append(f"**{name}**" if item_id == marked else name)
        return " · ".join(named)

    def describe(nodes: list[ComponentNode]) -> list[str]:
        """The lines of a list of nodes: the message itself or the contents of a container."""
        described: list[str] = []
        rows = 0
        for node in nodes:
            emoji = KIND_EMOJIS[node.kind]
            if node.kind == ComponentKind.ACTION_ROW:
                rows += 1
                described.append(
                    f"{emoji} {t(language, 'info.placement.short_row', row=rows)}: {names(node.item_ids) or '—'}"
                )
                continue

            counts[node.kind] = counts.get(node.kind, 0) + 1
            entry = f"{emoji} {label_for(node, counts[node.kind], language, snippet_length=OUTLINE_SNIPPET)}"
            if node.accessory_item_id is not None:
                entry = f"{entry} ➜ {names([node.accessory_item_id])}"
            described.append(entry)
            inner = describe(node.children)
            described.extend(
                f"{TREE_LAST if number == len(inner) else TREE_MIDDLE} {child}" for number, child in enumerate(inner, 1)
            )
        return described

    lines = [f"> {line}" for line in describe(session.components)]
    return "\n".join(
        fit_lines(lines, lambda hidden: f"> {shared_t(language, 'editor.section.more', amount=hidden)}", OUTLINE_BUDGET)
    )


def move_in_row(session: ContainerBuilderSession, item_id: int, offset: int) -> bool:
    """Move the button `offset` places along its row (`-1` to the left, `1` to the right). Returns whether it moved:
    a button that is not in a row, or already at that end of it, stays where it is."""
    placement = find_placement(session, item_id)
    if placement is None or placement.node.kind != ComponentKind.ACTION_ROW:
        return False

    row = placement.node.item_ids
    position = row.index(item_id)
    target = position + offset
    if not 0 <= target < len(row):
        return False

    row[position], row[target] = row[target], row[position]
    return True


def _drop_empty_rows(session: ContainerBuilderSession) -> None:
    """Remove rows that lost their last button."""
    session.components[:] = [node for node in session.components if node.kind != ComponentKind.ACTION_ROW or node.item_ids]
    for node in session.components:
        if node.kind == ComponentKind.CONTAINER:
            node.children[:] = [child for child in node.children if child.kind != ComponentKind.ACTION_ROW or child.item_ids]


def _real_row_label(session: ContainerBuilderSession, row_id: int) -> str:
    """`_row_label` of the row with this id in the session's actual layout."""
    for node, parent in iter_nodes(session.components):
        if node.id == row_id:
            return _row_label(session, node, parent)
    return ""


def unplace_item(session: ContainerBuilderSession, item_id: int) -> None:
    """Take the button out of the message layout (it stays defined). Rows it leaves empty disappear."""
    for node, _ in iter_nodes(session.components):
        if item_id in node.item_ids:
            node.item_ids.remove(item_id)
        if node.accessory_item_id == item_id:
            node.accessory_item_id = None
    _drop_empty_rows(session)


def delete_item(session: ContainerBuilderSession, item_id: int) -> None:
    """Delete the button altogether: out of the layout and out of the library."""
    unplace_item(session, item_id)
    session.library.remove(item_id)
    if session.active_item_id == item_id:
        session.active_item_id = None


def remove_interactive_items(session: ContainerBuilderSession) -> int:
    """Delete every button that runs actions (all but link buttons) and return how many there were."""
    interactive = session.library.interactive()
    for draft in interactive:
        delete_item(session, draft.id)
    return len(interactive)


def _signature(nodes: list[ComponentNode]) -> list[tuple[object, ...]]:
    """What the layout says about where buttons sit and in which order. The ids of rows are left out: a placement may
    make a row anew without changing anything."""
    signature: list[tuple[object, ...]] = []
    for node in nodes:
        if node.kind == ComponentKind.ACTION_ROW:
            signature.append(("row", tuple(node.item_ids)))
        elif node.kind == ComponentKind.CONTAINER:
            signature.append(("container", node.id, _signature(node.children)))
        else:
            signature.append((node.kind.value, node.id, node.accessory_item_id))
    return signature


def _changes_layout(session: ContainerBuilderSession, draft: ItemDraft, target: str) -> bool:
    """Whether putting the button where `target` says changes the layout - or fails, which is worth telling. A button
    that is alone in the last row of the message gains nothing from "a new row", and nothing from the row it is alone
    in, nor from the text it already sits next to."""
    probe = replace(session, components=copy.deepcopy(session.components))
    return place_item(probe, draft, target) is not None or _signature(probe.components) != _signature(session.components)


def placement_options(session: ContainerBuilderSession, draft: ItemDraft) -> list[SelectOption]:
    """Where the button can go: a new row, a row with room left, or next to a text without a thumbnail/button.

    Costs that would not fit into the message's component budget are left out, and so is a spot that would change
    nothing: the one the button already occupies, or one that puts it back where it was.
    """
    language = session.language
    real = session
    if draft.is_form:
        return []
    current = find_placement(session, draft.id)

    # Moving a button frees the room it uses now, which the new spot may then use - so the spots are judged
    # on a copy of the layout without the button (the real layout stays untouched).
    if current is not None:
        session = replace(session, components=copy.deepcopy(session.components))
        unplace_item(session, draft.id)
    budget = remaining_budget(session)

    options: list[SelectOption] = []
    if current is not None:
        options.append(SelectOption(label=t(language, "select.placement.unplace"), value=UNPLACE_VALUE, emoji="🗑️"))

    if budget >= NEW_ROW_COST:
        options.append(
            SelectOption(label=t(language, "select.placement.new_row_message"), value=NEW_ROW_MESSAGE_VALUE, emoji="➕")
        )
        containers = [node for node in session.components if node.kind == ComponentKind.CONTAINER]
        for index, container in enumerate(containers):
            options.append(
                SelectOption(
                    label=t(language, "select.placement.new_row_container", container=index + 1)[:100],
                    description=snippet_for(container, language, 100),
                    value=f"new_row:{container.id}",
                    emoji="📦",
                )
            )

    if budget >= 1:
        for node, _ in iter_nodes(session.components):
            if node.kind != ComponentKind.ACTION_ROW:
                continue
            if not row_has_room(_row_drafts(session, node), draft):
                continue
            # Rows are named as the user sees them now - the copy may have lost the button's own row.
            options.append(SelectOption(label=_real_row_label(real, node.id)[:100], value=f"row:{node.id}", emoji="🔘"))

    # A dropdown fills a whole row and has no place next to a text. The texts are numbered as the outline of the message
    # numbers them: every text counts, also one that already has a button next to it.
    if budget >= ACCESSORY_COST and not draft.is_select:
        texts = [node for node, _ in iter_nodes(session.components) if node.kind == ComponentKind.TEXT_DISPLAY]
        for number, node in enumerate(texts, 1):
            if node.has_accessory:
                continue
            options.append(
                SelectOption(
                    label=label_for(node, number, language)[:100],
                    description=t(language, "select.placement.next_to_text"),
                    value=f"text:{node.id}",
                    emoji="📝",
                )
            )

    places = [option for option in options if option.value == UNPLACE_VALUE or _changes_layout(real, draft, option.value)]
    return places[:25]  # Discord's select option limit


def place_item(session: ContainerBuilderSession, draft: ItemDraft, target: str) -> str | None:
    """Put the button where `target` (a value from `placement_options`) says. Returns an error text, or `None`.

    On failure the layout is left exactly as it was.
    """
    language = session.language
    if target == UNPLACE_VALUE:
        unplace_item(session, draft.id)
        return None

    if draft.is_form:
        return t(language, "errors.placement_form")
    if session.webhook.enabled and not draft.is_link:
        return t(language, "errors.placement_webhook")
    if draft.is_select and not draft.options:
        return t(language, "errors.placement_select_empty")

    snapshot = copy.deepcopy(session.components)
    unplace_item(session, draft.id)

    kind, _, raw_id = target.partition(":")
    error = _place(session, draft, kind, raw_id)
    if error is not None:
        session.components = snapshot
    return error


def _place(session: ContainerBuilderSession, draft: ItemDraft, kind: str, raw_id: str) -> str | None:
    """Carry out one placement on the (already unplaced) layout; the error text if it does not work out."""
    language = session.language
    needed = {"new_row": NEW_ROW_COST, "row": 1, "text": ACCESSORY_COST}.get(kind)
    if needed is None:
        return t(language, "errors.placement_target_gone")
    if remaining_budget(session) < needed:
        return t(language, "errors.placement_full")

    if kind == "new_row":
        owning = session.components
        if raw_id != "root":
            container = _find_top_level(session, int(raw_id), ComponentKind.CONTAINER)
            if container is None:
                return t(language, "errors.placement_target_gone")
            owning = container.children
        owning.append(ComponentNode(id=session.new_id(), kind=ComponentKind.ACTION_ROW, item_ids=[draft.id]))
        return None

    node = _find_any(session, int(raw_id))
    if node is None:
        return t(language, "errors.placement_target_gone")

    if kind == "row":
        if node.kind != ComponentKind.ACTION_ROW:
            return t(language, "errors.placement_target_gone")
        if not row_has_room(_row_drafts(session, node), draft):
            return t(language, "errors.placement_row_full")
        node.item_ids.append(draft.id)
        return None

    if node.kind != ComponentKind.TEXT_DISPLAY or node.has_accessory or draft.is_select:
        return t(language, "errors.placement_target_gone")
    node.accessory_item_id = draft.id
    return None


def _row_drafts(session: ContainerBuilderSession, row: ComponentNode) -> list[ItemDraft]:
    """The items sitting in a row."""
    drafts = (session.library.get(item_id) for item_id in row.item_ids)
    return [draft for draft in drafts if draft is not None]


def _find_top_level(session: ContainerBuilderSession, node_id: int, kind: ComponentKind) -> ComponentNode | None:
    """The top-level node with this id and kind, or `None`."""
    return next((node for node in session.components if node.id == node_id and node.kind == kind), None)


def _find_any(session: ContainerBuilderSession, node_id: int) -> ComponentNode | None:
    """The node with this id from the top level or a container's children, or `None`."""
    return next((node for node, _ in iter_nodes(session.components) if node.id == node_id), None)
