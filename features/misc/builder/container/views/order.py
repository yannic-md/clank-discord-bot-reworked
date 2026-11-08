from discord import ButtonStyle, Interaction, SelectOption
from discord.ui import ActionRow

from features.misc.builder.container.models import ComponentKind, ComponentNode
from features.misc.builder.container.session import ContainerBuilderSession
from features.misc.builder.container.translations import t, ts
from features.misc.builder.container.util.options import label_for
from features.misc.builder.container.util.tree import content_nodes, describe_location, get_list
from features.misc.builder.container.views.base import BuilderLayoutView, add_button, add_select, info_container, show


class ComponentOrderView(BuilderLayoutView):
    """Reorders one list of components. With `content_only`, the top-level list is shown without
    its containers (the "message content" part), while moves still act on the real, mixed list."""

    def __init__(
        self,
        session: ContainerBuilderSession,
        *,
        parent_id: int | None,
        content_only: bool = False,
        error: str | None = None,
    ) -> None:
        """`parent_id`: container to order (`None` = top level); `content_only`: skip components inside containers."""
        from features.misc.builder.container.views.component_list import ComponentKindListView
        from features.misc.builder.container.views.gui import MainView, MessageContentView

        super().__init__()
        self.session = session
        self.parent_id = parent_id
        self.content_only = content_only

        owning_list = get_list(session, parent_id)
        nodes = content_nodes(owning_list) if content_only else owning_list
        location = t(session.language, "select.content.label") if content_only else describe_location(session, parent_id)

        def swap(first: ComponentNode, second: ComponentNode) -> None:
            """Swap `first` and `second` in the list being ordered."""
            first_index, second_index = owning_list.index(first), owning_list.index(second)
            owning_list[first_index], owning_list[second_index] = owning_list[second_index], owning_list[first_index]

        selection_key: tuple[int | None, ComponentKind | None] = (parent_id, None)
        active_id = session.active_selection.get(selection_key)
        if active_id is not None and not any(node.id == active_id for node in nodes):
            active_id = None
        if active_id is None and nodes:
            active_id = nodes[0].id
        if active_id is not None:
            session.active_selection[selection_key] = active_id
        else:
            session.active_selection.pop(selection_key, None)

        active_index = next((index for index, node in enumerate(nodes) if node.id == active_id), None)

        header = f"### {t(session.language, 'info.order.title', location=location)}"
        description = t(session.language, "info.order.description" if nodes else "info.order.description_empty")
        self.add_item(info_container(f"{header}\n{description}"))

        nav_row: ActionRow = ActionRow()

        async def on_back(interaction: Interaction) -> None:
            """Go back to the screen the order screen was opened from."""
            if parent_id is not None:
                await show(interaction, ComponentKindListView(session, kind=ComponentKind.CONTAINER, parent_id=None))
            elif content_only:
                await show(interaction, MessageContentView(session))
            else:
                await show(interaction, MainView(session))

        add_button(nav_row, on_back, label=ts(session.language, "buttons.back"), style=ButtonStyle.gray, emoji="◀️")

        async def on_up(interaction: Interaction) -> None:
            """Move the selected component one position up."""
            assert active_index is not None and active_index > 0
            swap(nodes[active_index - 1], nodes[active_index])
            await show(interaction, ComponentOrderView(session, parent_id=parent_id, content_only=content_only))

        async def on_down(interaction: Interaction) -> None:
            """Move the selected component one position down."""
            assert active_index is not None and active_index < len(nodes) - 1
            swap(nodes[active_index + 1], nodes[active_index])
            await show(interaction, ComponentOrderView(session, parent_id=parent_id, content_only=content_only))

        up_disabled = active_index is None or active_index <= 0
        down_disabled = active_index is None or active_index >= len(nodes) - 1
        add_button(
            nav_row,
            on_up,
            label=ts(session.language, "buttons.up"),
            style=ButtonStyle.blurple,
            emoji="⬆️",
            disabled=up_disabled,
        )
        add_button(
            nav_row,
            on_down,
            label=ts(session.language, "buttons.down"),
            style=ButtonStyle.blurple,
            emoji="⬇️",
            disabled=down_disabled,
        )
        self.add_item(nav_row)

        select_row: ActionRow = ActionRow()
        if nodes:
            select_options = [
                SelectOption(
                    label=label_for(node, index + 1, session.language)[:100],
                    value=str(node.id),
                    default=node.id == active_id,
                )
                for index, node in enumerate(nodes)
            ]
            select_placeholder = t(session.language, "placeholders.switch_component")
            select_disabled = False
        else:
            select_options = [SelectOption(label="—", value="__none__")]
            select_placeholder = t(session.language, "placeholders.components_empty")
            select_disabled = True

        async def on_switch(interaction: Interaction) -> None:
            """Select another component to move."""
            if not nodes:
                return
            session.active_selection[selection_key] = int(switch_select.values[0])
            await show(interaction, ComponentOrderView(session, parent_id=parent_id, content_only=content_only))

        switch_select = add_select(
            select_row, on_switch, options=select_options, placeholder=select_placeholder, disabled=select_disabled
        )
        self.add_item(select_row)

        if error:
            self.add_error(error)
