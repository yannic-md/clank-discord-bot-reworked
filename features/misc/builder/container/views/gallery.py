from discord import ButtonStyle, Interaction, SelectOption
from discord.ui import ActionRow

from core.discord_api.limits import MAX_V2_MEDIA_GALLERY_ITEMS
from features.misc.builder.container.modals.media import MediaGalleryItemModal
from features.misc.builder.container.models import ComponentKind
from features.misc.builder.container.session import ContainerBuilderSession
from features.misc.builder.container.translations import kind_empty_text, kind_label, t, ts
from features.misc.builder.container.util.render import preview_item
from features.misc.builder.container.util.tree import find_node, find_parent
from features.misc.builder.container.views.base import BuilderLayoutView, add_button, add_select, empty_node_container, show


class MediaGalleryItemsView(BuilderLayoutView):
    """Screen to add, edit, remove and reorder the items of one media gallery."""

    def __init__(
        self,
        session: ContainerBuilderSession,
        *,
        node_id: int,
        active_index: int | None = None,
        error: str | None = None,
    ) -> None:
        """`node_id` is the media gallery, `active_index` the selected item (defaults to the first) and `error` an optional
        error box to show.
        """
        from features.misc.builder.container.views.component_list import ComponentKindListView

        super().__init__()
        self.session = session
        self.node_id = node_id

        node = find_node(session, node_id)
        assert node is not None and node.kind == ComponentKind.MEDIA_GALLERY
        items = node.gallery_items

        if active_index is not None and not (0 <= active_index < len(items)):
            active_index = None
        if active_index is None and items:
            active_index = 0

        if items:
            self.add_item(preview_item(session, node))
        else:
            empty_text = kind_empty_text(session.language, ComponentKind.MEDIA_GALLERY)
            gallery_name = kind_label(session.language, ComponentKind.MEDIA_GALLERY)
            self.add_item(empty_node_container(session, node, f"### 🖼️ ~ {gallery_name}\n{empty_text}"))

        nav_row: ActionRow = ActionRow()

        async def on_back(interaction: Interaction) -> None:
            """Go back to the media gallery list."""
            parent = find_parent(session, node_id)
            back_parent_id = parent.id if parent else None
            back_view = ComponentKindListView(session, kind=ComponentKind.MEDIA_GALLERY, parent_id=back_parent_id)
            await show(interaction, back_view)

        add_button(nav_row, on_back, label=ts(session.language, "buttons.back"), style=ButtonStyle.gray, emoji="◀️")

        async def on_add(interaction: Interaction) -> None:
            """Open the modal to add items, or show the limit error if the gallery is full."""
            if len(items) >= MAX_V2_MEDIA_GALLERY_ITEMS:
                error = t(session.language, "errors.gallery_max_items", max=MAX_V2_MEDIA_GALLERY_ITEMS)
                await show(
                    interaction,
                    MediaGalleryItemsView(session, node_id=node_id, active_index=active_index, error=error),
                )
                return
            await interaction.response.send_modal(MediaGalleryItemModal(session, node_id=node_id, item_index=None))

        add_button(
            nav_row,
            on_add,
            label=t(session.language, "buttons.item_add"),
            style=ButtonStyle.green,
            emoji="➕",
            disabled=len(items) >= MAX_V2_MEDIA_GALLERY_ITEMS,
        )

        async def on_edit(interaction: Interaction) -> None:
            """Open the modal to replace the media of the selected item."""
            assert active_index is not None
            await interaction.response.send_modal(MediaGalleryItemModal(session, node_id=node_id, item_index=active_index))

        add_button(
            nav_row,
            on_edit,
            label=t(session.language, "buttons.edit"),
            style=ButtonStyle.blurple,
            emoji="✏️",
            disabled=active_index is None,
        )

        async def on_remove(interaction: Interaction) -> None:
            """Delete the selected item."""
            assert active_index is not None
            del items[active_index]
            await show(interaction, MediaGalleryItemsView(session, node_id=node_id))

        add_button(
            nav_row,
            on_remove,
            label=t(session.language, "buttons.delete"),
            style=ButtonStyle.red,
            emoji="🗑️",
            disabled=active_index is None,
        )
        self.add_item(nav_row)

        select_row: ActionRow = ActionRow()
        if items:
            select_options = [
                SelectOption(
                    label=t(
                        session.language,
                        "placeholders.item_option",
                        number=index + 1,
                        description=item.description or t(session.language, "placeholders.item_no_description"),
                    )[:100],
                    value=str(index),
                    default=index == active_index,
                )
                for index, item in enumerate(items)
            ]
            select_placeholder = t(session.language, "placeholders.switch_item")
            select_disabled = False
        else:
            select_options = [SelectOption(label="—", value="__none__")]
            select_placeholder = t(session.language, "placeholders.switch_item_empty")
            select_disabled = True

        async def on_switch(interaction: Interaction) -> None:
            """Select another item of the gallery."""
            if not items:
                return
            new_index = int(switch_select.values[0])
            await show(interaction, MediaGalleryItemsView(session, node_id=node_id, active_index=new_index))

        switch_select = add_select(
            select_row, on_switch, options=select_options, placeholder=select_placeholder, disabled=select_disabled
        )
        self.add_item(select_row)

        order_row: ActionRow = ActionRow()

        async def on_up(interaction: Interaction) -> None:
            """Move the selected item one position up."""
            assert active_index is not None and active_index > 0
            items[active_index - 1], items[active_index] = items[active_index], items[active_index - 1]
            await show(interaction, MediaGalleryItemsView(session, node_id=node_id, active_index=active_index - 1))

        async def on_down(interaction: Interaction) -> None:
            """Move the selected item one position down."""
            assert active_index is not None and active_index < len(items) - 1
            items[active_index + 1], items[active_index] = items[active_index], items[active_index + 1]
            await show(interaction, MediaGalleryItemsView(session, node_id=node_id, active_index=active_index + 1))

        item_up_disabled = active_index is None or active_index <= 0
        item_down_disabled = active_index is None or active_index >= len(items) - 1
        add_button(
            order_row,
            on_up,
            label=ts(session.language, "buttons.up"),
            style=ButtonStyle.blurple,
            emoji="⬆️",
            disabled=item_up_disabled,
        )
        add_button(
            order_row,
            on_down,
            label=ts(session.language, "buttons.down"),
            style=ButtonStyle.blurple,
            emoji="⬇️",
            disabled=item_down_disabled,
        )
        if items:
            self.add_item(order_row)

        if error:
            self.add_error(error)
