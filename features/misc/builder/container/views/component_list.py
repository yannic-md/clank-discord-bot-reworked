from discord import ButtonStyle, Interaction, SelectOption
from discord.ui import ActionRow, Item, Modal

from features.misc.builder.container.modals.content import ContainerModal, SeparatorModal, TextDisplayModal
from features.misc.builder.container.modals.media import ThumbnailModal
from features.misc.builder.container.models import KIND_EMOJIS, MAX_USER_COMPONENTS, ComponentKind, ComponentNode
from features.misc.builder.container.session import ContainerBuilderSession
from features.misc.builder.container.translations import kind_empty_text, kind_info_text, kind_label, t, ts
from features.misc.builder.container.util.options import label_for, move_targets, sub_options_for
from features.misc.builder.container.util.render import preview_item
from features.misc.builder.container.util.tree import (
    describe_location,
    find_node,
    get_list,
    is_empty_node,
    node_cost,
    remaining_budget,
)
from features.misc.builder.container.views.base import (
    BuilderLayoutView,
    add_button,
    add_select,
    empty_node_container,
    info_container,
    show,
)


class ComponentKindListView(BuilderLayoutView):
    """Screen listing all components of one kind - in the message or inside a container - with controls to add, edit, remove,
    reorder and move them.
    """

    def __init__(
        self,
        session: ContainerBuilderSession,
        *,
        kind: ComponentKind,
        parent_id: int | None,
        error: str | None = None,
    ) -> None:
        """`kind` is the component kind to list, `parent_id` the container to list it from (`None` for the top level) and
        `error` an optional error box to show.
        """
        from features.misc.builder.container.views.gallery import MediaGalleryItemsView
        from features.misc.builder.container.views.gui import MainView, MessageContentView
        from features.misc.builder.container.views.move import MoveView
        from features.misc.builder.container.views.order import ComponentOrderView

        super().__init__()
        self.session = session
        self.kind = kind
        self.parent_id = parent_id

        owning_list = get_list(session, parent_id)
        nodes = [node for node in owning_list if node.kind == kind]

        selection_key = (parent_id, kind)
        active_id = session.active_selection.get(selection_key)
        if active_id is not None and not any(node.id == active_id for node in nodes):
            active_id = None
        if active_id is None and nodes:
            active_id = nodes[0].id
        if active_id is not None:
            session.active_selection[selection_key] = active_id
        else:
            session.active_selection.pop(selection_key, None)

        active_node = find_node(session, active_id) if active_id is not None else None

        # Replaces the info container outright once a component is selected, per the spec.
        preview: Item | None = None
        if active_node is None:
            location = describe_location(session, parent_id)
            header = f"### {KIND_EMOJIS[kind]} ~ {kind_label(session.language, kind)} - {location}"
            self.add_item(info_container(f"{header}\n{kind_info_text(session.language, kind)}"))
        elif is_empty_node(active_node):
            empty_text = kind_empty_text(session.language, kind)
            header = f"### {KIND_EMOJIS[kind]} ~ {kind_label(session.language, kind)}"
            self.add_item(empty_node_container(session, active_node, f"{header}\n{empty_text}"))
        else:
            preview = preview_item(session, active_node)

        nav_row: ActionRow = ActionRow()

        async def on_back(interaction: Interaction) -> None:
            """Go back to the screen this list was opened from."""
            if parent_id is not None:
                await show(interaction, ComponentKindListView(session, kind=ComponentKind.CONTAINER, parent_id=None))
            elif kind == ComponentKind.CONTAINER:
                await show(interaction, MainView(session))
            else:
                await show(interaction, MessageContentView(session))

        add_button(nav_row, on_back, label=ts(session.language, "buttons.back"), style=ButtonStyle.gray, emoji="◀️")

        can_add = remaining_budget(session) >= 1

        async def on_add(interaction: Interaction) -> None:
            """Add a component of this kind, or show the limit error if the message is full."""
            if remaining_budget(session) < 1:
                error = t(session.language, "errors.component_limit", limit=MAX_USER_COMPONENTS)
                await show(interaction, ComponentKindListView(session, kind=kind, parent_id=parent_id, error=error))
                return

            if kind == ComponentKind.MEDIA_GALLERY:
                new_node = ComponentNode(id=session.new_id(), kind=kind)
                owning_list.append(new_node)
                session.active_selection[selection_key] = new_node.id
                await show(interaction, MediaGalleryItemsView(session, node_id=new_node.id))
                return

            await interaction.response.send_modal(_modal_for_kind(session, kind, parent_id=parent_id, node_id=None))

        add_label = t(session.language, "buttons.component_add", kind=kind_label(session.language, kind))
        add_button(nav_row, on_add, label=add_label, style=ButtonStyle.green, emoji="➕", disabled=not can_add)

        async def on_edit(interaction: Interaction) -> None:
            """Edit the selected component - galleries open their item screen, all other kinds a modal."""
            assert active_node is not None
            if kind == ComponentKind.MEDIA_GALLERY:
                await show(interaction, MediaGalleryItemsView(session, node_id=active_node.id))
                return
            modal = _modal_for_kind(session, kind, parent_id=parent_id, node_id=active_node.id)
            await interaction.response.send_modal(modal)

        edit_label = t(session.language, "buttons.edit")
        add_button(nav_row, on_edit, label=edit_label, style=ButtonStyle.blurple, emoji="✏️", disabled=active_node is None)

        async def on_remove(interaction: Interaction) -> None:
            """Delete the selected component."""
            assert active_node is not None
            owning_list.remove(active_node)
            await show(interaction, ComponentKindListView(session, kind=kind, parent_id=parent_id))

        remove_label = t(session.language, "buttons.delete")
        add_button(nav_row, on_remove, label=remove_label, style=ButtonStyle.red, emoji="🗑️", disabled=active_node is None)
        self.add_item(nav_row)

        if kind == ComponentKind.TEXT_DISPLAY and active_node is not None:
            # The thumbnail belongs to the selected text display, so its button sits right below the
            # add / edit / delete buttons.
            thumbnail_row: ActionRow = ActionRow()
            text_node = active_node

            async def on_thumbnail(interaction: Interaction) -> None:
                """Open the thumbnail modal for the selected text display."""
                await interaction.response.send_modal(ThumbnailModal(session, node_id=text_node.id))

            # Creating a thumbnail turns the text into a section: it uses two more components of the budget.
            can_create = text_node.has_accessory or remaining_budget(session) >= 2
            thumbnail_label = t(
                session.language, "buttons.thumbnail_edit" if text_node.has_accessory else "buttons.thumbnail_create"
            )
            add_button(
                thumbnail_row,
                on_thumbnail,
                label=thumbnail_label,
                style=ButtonStyle.gray,
                emoji="🖼️",
                disabled=not can_create,
            )
            self.add_item(thumbnail_row)

        switch_row: ActionRow = ActionRow()
        if nodes:
            switch_options = [
                SelectOption(
                    label=label_for(node, index + 1, session.language)[:100],
                    value=str(node.id),
                    default=node.id == active_id,
                )
                for index, node in enumerate(nodes)
            ]
            switch_placeholder = t(session.language, "placeholders.switch_component")
            switch_disabled = False
        else:
            switch_options = [SelectOption(label="—", value="__none__")]
            switch_placeholder = t(
                session.language, "placeholders.switch_component_empty", kind=kind_label(session.language, kind)
            )
            switch_disabled = True

        async def on_switch(interaction: Interaction) -> None:
            """Select another component of this kind."""
            if not nodes:
                return
            session.active_selection[selection_key] = int(switch_select.values[0])
            await show(interaction, ComponentKindListView(session, kind=kind, parent_id=parent_id))

        switch_select = add_select(
            switch_row, on_switch, options=switch_options, placeholder=switch_placeholder, disabled=switch_disabled
        )
        self.add_item(switch_row)

        if active_node is not None:
            sub_options = sub_options_for(active_node, session.language)
            if sub_options:
                sub_row: ActionRow = ActionRow()

                async def on_sub_select(interaction: Interaction) -> None:
                    """Open the list of child components of the selected container."""
                    assert active_node is not None
                    value = sub_select.values[0]
                    child_kind = ComponentKind(value.removeprefix("child_"))
                    await show(interaction, ComponentKindListView(session, kind=child_kind, parent_id=active_node.id))

                sub_select = add_select(
                    sub_row,
                    on_sub_select,
                    options=sub_options,
                    placeholder=t(session.language, "placeholders.child_elements"),
                )
                self.add_item(sub_row)

        # Moves the active component relative to the other components of the same kind - the ones this
        # screen lists in its dropdown - so "up"/"down" are disabled exactly when it is the first/last one
        # shown there. Components of other kinds in between keep their place (the "Reihenfolge" screens
        # edit the full, mixed order). Placed below both dropdowns above, so it's always the last row on
        # this screen. It also hosts the kind-specific extras (move for everything but containers, child
        # order for containers).
        position = nodes.index(active_node) if active_node is not None else None
        reorder_row: ActionRow = ActionRow()

        def swap_with(neighbour: ComponentNode) -> None:
            """Swap the selected component with `neighbour` in the list owning them."""
            assert active_node is not None
            first, second = owning_list.index(active_node), owning_list.index(neighbour)
            owning_list[first], owning_list[second] = owning_list[second], owning_list[first]

        async def on_up(interaction: Interaction) -> None:
            """Move the selected component one position up."""
            assert position is not None and position > 0
            swap_with(nodes[position - 1])
            await show(interaction, ComponentKindListView(session, kind=kind, parent_id=parent_id))

        async def on_down(interaction: Interaction) -> None:
            """Move the selected component one position down."""
            assert position is not None and position < len(nodes) - 1
            swap_with(nodes[position + 1])
            await show(interaction, ComponentKindListView(session, kind=kind, parent_id=parent_id))

        up_disabled = position is None or position <= 0
        down_disabled = position is None or position >= len(nodes) - 1
        add_button(
            reorder_row,
            on_up,
            label=ts(session.language, "buttons.up"),
            style=ButtonStyle.blurple,
            emoji="⬆️",
            disabled=up_disabled,
        )
        add_button(
            reorder_row,
            on_down,
            label=ts(session.language, "buttons.down"),
            style=ButtonStyle.blurple,
            emoji="⬇️",
            disabled=down_disabled,
        )

        if kind != ComponentKind.CONTAINER:

            async def on_move(interaction: Interaction) -> None:
                """Open the screen to move the selected component into another container."""
                assert active_node is not None
                await show(interaction, MoveView(session, node_id=active_node.id))

            can_move = active_node is not None and bool(move_targets(session, active_node))
            add_button(
                reorder_row,
                on_move,
                label=t(session.language, "buttons.move"),
                style=ButtonStyle.gray,
                emoji="↔️",
                disabled=not can_move,
            )

        if kind == ComponentKind.CONTAINER:

            async def on_child_order(interaction: Interaction) -> None:
                """Open the order screen for the contents of the selected container."""
                assert active_node is not None
                await show(interaction, ComponentOrderView(session, parent_id=active_node.id))

            child_count = len(active_node.children) if active_node is not None else 0
            add_button(
                reorder_row,
                on_child_order,
                label=t(session.language, "buttons.order_contents"),
                style=ButtonStyle.gray,
                emoji="🔀",
                disabled=child_count < 2,
            )
        if active_node is not None:
            # Moving and reordering only make sense once there is something to move.
            self.add_item(reorder_row)

        if preview is not None and active_node is not None:
            # The preview goes first - but a huge container next to the controls would exceed Discord's limit.
            header = f"### {KIND_EMOJIS[kind]} ~ {kind_label(session.language, kind)}"
            too_large = t(session.language, "info.preview_too_large", amount=node_cost(active_node))
            self.add_item_top(preview, fallback=lambda: info_container(f"{header}\n{too_large}"))

        if error:
            self.add_error(error)


def _modal_for_kind(
    session: ContainerBuilderSession, kind: ComponentKind, *, parent_id: int | None, node_id: int | None
) -> Modal:
    """The modal to create or edit a component of `kind`; media galleries have none and raise `ValueError`."""
    if kind == ComponentKind.TEXT_DISPLAY:
        return TextDisplayModal(session, parent_id=parent_id, node_id=node_id)
    if kind == ComponentKind.CONTAINER:
        return ContainerModal(session, node_id=node_id)
    if kind == ComponentKind.SEPARATOR:
        return SeparatorModal(session, parent_id=parent_id, node_id=node_id)
    raise ValueError(f"no modal for {kind}")  # MEDIA_GALLERY is handled without a modal
