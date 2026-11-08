from discord import ButtonStyle, Interaction
from discord.ui import ActionRow

from features.misc.builder.container.models import ComponentKind
from features.misc.builder.container.session import ContainerBuilderSession
from features.misc.builder.container.translations import kind_label, t, ts
from features.misc.builder.container.util.options import move_targets
from features.misc.builder.container.util.tree import describe_location, find_node, find_parent, get_list
from features.misc.builder.container.views.base import BuilderLayoutView, add_button, add_select, info_container, show


class MoveView(BuilderLayoutView):
    """Moves a component between the message itself and containers (appended at the end)."""

    def __init__(self, session: ContainerBuilderSession, *, node_id: int, error: str | None = None) -> None:
        from features.misc.builder.container.views.component_list import ComponentKindListView

        super().__init__()
        self.session = session
        self.node_id = node_id

        node = find_node(session, node_id)
        assert node is not None and node.kind != ComponentKind.CONTAINER

        parent = find_parent(session, node_id)
        current_parent_id = parent.id if parent else None
        kind_name = kind_label(session.language, node.kind)

        header = f"### {t(session.language, 'info.move.title', kind=kind_name)}"
        location = describe_location(session, current_parent_id)
        description = t(session.language, "info.move.description", location=location)
        self.add_item(info_container(f"{header}\n{description}"))

        nav_row: ActionRow = ActionRow()

        async def on_back(interaction: Interaction) -> None:
            await show(interaction, ComponentKindListView(session, kind=node.kind, parent_id=current_parent_id))

        add_button(nav_row, on_back, label=ts(session.language, "buttons.back"), style=ButtonStyle.gray, emoji="◀️")
        self.add_item(nav_row)

        select_row: ActionRow = ActionRow()
        options = move_targets(session, node)

        async def on_select(interaction: Interaction) -> None:
            value = target_select.values[0]
            if value == "__none__":
                return

            target_id = None if value == "root" else int(value)
            if target_id is not None:
                target = find_node(session, target_id)
                if target is None or target.kind != ComponentKind.CONTAINER:
                    await show(
                        interaction, MoveView(session, node_id=node_id, error=t(session.language, "errors.move_target_gone"))
                    )
                    return

            get_list(session, current_parent_id).remove(node)
            get_list(session, target_id).append(node)
            session.active_selection[(target_id, node.kind)] = node.id
            await show(interaction, ComponentKindListView(session, kind=node.kind, parent_id=target_id))

        target_select = add_select(
            select_row,
            on_select,
            options=options,
            placeholder=t(session.language, "placeholders.move_target" if options else "placeholders.move_target_empty"),
            disabled=not options,
        )
        self.add_item(select_row)

        if error:
            self.add_error(error)
