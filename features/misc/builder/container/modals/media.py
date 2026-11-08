from discord import Attachment, Interaction, RadioGroupOption
from discord.ui import FileUpload, Label, Modal, RadioGroup, TextInput

from core.discord_api.limits import (
    MAX_V2_MEDIA_GALLERY_ITEM_DESCRIPTION,
    MAX_V2_MEDIA_GALLERY_ITEMS,
    MAX_V2_THUMBNAIL_DESCRIPTION,
)
from features.misc.builder.container.models import MAX_USER_COMPONENTS, ComponentKind, GalleryItem
from features.misc.builder.container.session import ContainerBuilderSession
from features.misc.builder.container.translations import t, ts
from features.misc.builder.container.util.tree import find_node, find_parent, remaining_budget
from features.misc.builder.container.validation import is_valid_media_attachment
from features.misc.builder.validation import is_valid_image_attachment


class ThumbnailModal(Modal):
    """Modal to set, replace or remove the thumbnail shown next to a text display."""

    def __init__(self, session: ContainerBuilderSession, *, node_id: int) -> None:
        """`node_id` is the text display the thumbnail belongs to."""
        super().__init__(title=t(session.language, "modals.thumbnail.title"))
        self.session = session
        self.node_id = node_id

        node = find_node(session, node_id)
        assert node is not None

        # Discord only treats the field as optional with `min_values=0` (just `required=False` still
        # demands one file), so an existing thumbnail can be removed by saving without an image.
        optional = node.has_accessory
        self.media_input: FileUpload = FileUpload(required=not optional, min_values=0 if optional else 1, max_values=1)
        self.description_input: TextInput = TextInput(
            label=t(session.language, "modals.description.field"),
            placeholder=t(session.language, "modals.description.placeholder"),
            required=False,
            max_length=MAX_V2_THUMBNAIL_DESCRIPTION,
        )
        self.spoiler_input: RadioGroup = RadioGroup(
            options=[
                RadioGroupOption(label=ts(session.language, "modals.option_no"), value="no", default=True),
                RadioGroupOption(label=ts(session.language, "modals.option_yes"), value="yes"),
            ]
        )

        media_label = ts(session.language, "modals.images.thumbnail")
        self.add_item(Label(text=media_label, component=self.media_input))
        self.add_item(self.description_input)
        self.add_item(Label(text=t(session.language, "modals.spoiler.question"), component=self.spoiler_input))

    async def on_submit(self, interaction: Interaction) -> None:
        """Apply the uploaded image as thumbnail - or remove the existing one if none was uploaded - and show the list."""
        from features.misc.builder.container.views.base import show
        from features.misc.builder.container.views.component_list import ComponentKindListView

        session = self.session
        node = find_node(session, self.node_id)
        assert node is not None

        parent = find_parent(session, self.node_id)
        parent_id = parent.id if parent else None
        session.active_selection[(parent_id, ComponentKind.TEXT_DISPLAY)] = node.id

        async def back(error: str | None = None) -> None:
            """Show the text display list, optionally with the error `error`."""
            view = ComponentKindListView(session, kind=ComponentKind.TEXT_DISPLAY, parent_id=parent_id, error=error)
            await show(interaction, view)

        uploaded: Attachment | None = self.media_input.values[0] if self.media_input.values else None
        description = self.description_input.value.strip() or None
        spoiler = self.spoiler_input.value == "yes"

        if uploaded is None:
            if not node.has_accessory:
                await back(t(session.language, "errors.thumbnail_no_image"))
                return

            if description is not None or spoiler:
                await back(t(session.language, "errors.thumbnail_needs_image"))
                return

            # An empty submission removes the existing thumbnail (the upload is only optional
            # here because a thumbnail exists - Discord enforces it for new ones).
            node.thumbnail_url = None
            node.thumbnail_description = None
            node.thumbnail_spoiler = False
            await back()
            return

        if not is_valid_image_attachment(uploaded):
            await back(ts(session.language, "errors.invalid_image"))
            return

        if not node.has_accessory and remaining_budget(session) < 2:
            await back(t(session.language, "errors.component_limit", limit=MAX_USER_COMPONENTS))
            return

        node.thumbnail_url = uploaded.url
        node.thumbnail_description = description
        node.thumbnail_spoiler = spoiler

        await back()


class MediaGalleryItemModal(Modal):
    """Modal to add gallery items by upload, or to replace the media of one existing item."""

    def __init__(self, session: ContainerBuilderSession, *, node_id: int, item_index: int | None) -> None:
        """`node_id` is the media gallery, `item_index` the item to edit (`None` to add new ones)."""
        super().__init__(title=t(session.language, "modals.gallery.title"))
        self.session = session
        self.node_id = node_id
        self.item_index = item_index

        node = find_node(session, node_id)
        assert node is not None
        existing = node.gallery_items[item_index] if item_index is not None else None

        # Adding accepts as many files at once as the gallery still has free slots (each file
        # becomes its own item); editing always targets exactly one item.
        free_slots = max(1, MAX_V2_MEDIA_GALLERY_ITEMS - len(node.gallery_items))
        max_files = free_slots if existing is None else 1
        # `min_values=0` is what makes the field really optional when editing (keeps the current file).
        self.media_input: FileUpload = FileUpload(
            required=existing is None, min_values=1 if existing is None else 0, max_values=max_files
        )
        self.description_input: TextInput = TextInput(
            label=t(session.language, "modals.description.field" if existing else "modals.gallery.description_all"),
            placeholder=t(session.language, "modals.description.placeholder"),
            required=False,
            max_length=MAX_V2_MEDIA_GALLERY_ITEM_DESCRIPTION,
            default=existing.description if existing else None,
        )
        self.spoiler_input: RadioGroup = RadioGroup(
            options=[
                RadioGroupOption(
                    label=ts(session.language, "modals.option_no"),
                    value="no",
                    default=not (existing.spoiler if existing else False),
                ),
                RadioGroupOption(
                    label=ts(session.language, "modals.option_yes"), value="yes", default=bool(existing and existing.spoiler)
                ),
            ]
        )
        media_label = (
            t(session.language, "modals.gallery.media_edit")
            if existing
            else t(session.language, "modals.gallery.media_add", max=max_files)
        )
        self.add_item(Label(text=media_label, component=self.media_input))
        self.add_item(self.description_input)
        self.add_item(Label(text=t(session.language, "modals.spoiler.question"), component=self.spoiler_input))

    async def on_submit(self, interaction: Interaction) -> None:
        """Validate the uploads, add or update the gallery items and show the gallery screen."""
        from features.misc.builder.container.views.base import show
        from features.misc.builder.container.views.gallery import MediaGalleryItemsView

        session = self.session
        node = find_node(session, self.node_id)
        assert node is not None

        uploads: list[Attachment] = list(self.media_input.values)
        description = self.description_input.value.strip() or None
        spoiler = self.spoiler_input.value == "yes"

        async def back(active_index: int | None, error: str | None = None) -> None:
            """Show the gallery screen with `active_index` selected, optionally with the error `error`."""
            view = MediaGalleryItemsView(session, node_id=self.node_id, active_index=active_index, error=error)
            await show(interaction, view)

        # Validate everything up front so a single bad file doesn't leave a half-filled gallery.
        if not all(is_valid_media_attachment(upload) for upload in uploads):
            await back(self.item_index, t(session.language, "errors.gallery_invalid_media"))
            return

        if self.item_index is not None:
            existing = node.gallery_items[self.item_index]
            media_url = uploads[0].url if uploads else existing.media_url
            node.gallery_items[self.item_index] = GalleryItem(media_url=media_url, description=description, spoiler=spoiler)
            await back(self.item_index)
            return

        if not uploads:
            await back(None, t(session.language, "errors.gallery_no_file"))
            return

        if len(node.gallery_items) + len(uploads) > MAX_V2_MEDIA_GALLERY_ITEMS:
            error = t(session.language, "errors.gallery_max_items", max=MAX_V2_MEDIA_GALLERY_ITEMS)
            await back(None, error)
            return

        first_new_index = len(node.gallery_items)
        node.gallery_items.extend(
            GalleryItem(media_url=upload.url, description=description, spoiler=spoiler) for upload in uploads
        )
        await back(first_new_index)
