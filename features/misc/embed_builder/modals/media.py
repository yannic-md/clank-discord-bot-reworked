from datetime import datetime

from discord import Attachment, Embed, Interaction, TextStyle
from discord.ui import FileUpload, Label, Modal, TextInput

from core.discord_api.limits import MAX_EMBED_AUTHOR_NAME, MAX_EMBED_FOOTER_TEXT, MAX_EMBED_URL
from core.i18n.translator import translate
from features.misc.embed_builder.session import BuilderSession
from features.misc.embed_builder.util.embed_ops import non_empty_embeds
from features.misc.embed_builder.validation import (
    append_error,
    convert_to_datetime,
    format_timestamp_for_input,
    is_valid_image_attachment,
    is_valid_url,
)


class EmbedImagesModal(Modal):
    def __init__(self, session: BuilderSession) -> None:
        super().__init__(title=translate(session.language, "builder.modals.images.title"))
        self.session: BuilderSession = session

        self.thumbnail_input: FileUpload = FileUpload(required=False, max_values=1)
        self.image_input: FileUpload = FileUpload(required=False, max_values=1)

        self.add_item(
            Label(text=translate(session.language, "builder.modals.images.thumbnail"), component=self.thumbnail_input)
        )
        self.add_item(Label(text=translate(session.language, "builder.modals.images.image"), component=self.image_input))

    async def on_submit(self, interaction: Interaction) -> None:
        from features.misc.embed_builder.views import EmbedBuilderGUI, show

        for attachment_list in (self.thumbnail_input.values, self.image_input.values):
            if attachment_list and not is_valid_image_attachment(attachment_list[0]):
                await append_error(
                    interaction,
                    non_empty_embeds(self.session.embeds),
                    EmbedBuilderGUI(self.session),
                    translate(self.session.language, "builder.errors.invalid_image"),
                )
                return

        embed: Embed = self.session.active_embed
        embed.set_thumbnail(url=self.thumbnail_input.values[0].url if self.thumbnail_input.values else None)
        embed.set_image(url=self.image_input.values[0].url if self.image_input.values else None)
        await show(interaction, EmbedBuilderGUI(self.session))


class EmbedAuthorModal(Modal):
    def __init__(self, session: BuilderSession) -> None:
        super().__init__(title=translate(session.language, "builder.modals.author.title"))
        self.session: BuilderSession = session
        embed: Embed = session.active_embed

        self.name_input: TextInput = TextInput(
            label=translate(session.language, "builder.modals.author.name.question"),
            placeholder=translate(session.language, "builder.modals.author.name.placeholder"),
            required=False,
            max_length=MAX_EMBED_AUTHOR_NAME,
            default=embed.author.name,
        )

        self.url_input: TextInput = TextInput(
            label=translate(session.language, "builder.modals.author.url.question"),
            placeholder=translate(session.language, "builder.modals.author.url.placeholder"),
            required=False,
            max_length=MAX_EMBED_URL,
            default=embed.author.url,
        )
        self.icon_input: FileUpload = FileUpload(required=False, max_values=1)

        self.add_item(self.name_input)
        self.add_item(self.url_input)
        self.add_item(Label(text=translate(session.language, "builder.modals.author.icon"), component=self.icon_input))

    async def on_submit(self, interaction: Interaction) -> None:
        from features.misc.embed_builder.views import EmbedBuilderGUI, show

        embed: Embed = self.session.active_embed
        name: str = self.name_input.value.strip()
        url: str = self.url_input.value.strip()
        icon: Attachment | None = self.icon_input.values[0] if self.icon_input.values else None

        if not name:
            if url or icon:
                await append_error(
                    interaction,
                    non_empty_embeds(self.session.embeds),
                    EmbedBuilderGUI(self.session),
                    translate(self.session.language, "builder.errors.author_fields_without_name"),
                )
                return

            embed.remove_author()
            await show(interaction, EmbedBuilderGUI(self.session))
            return

        if url and not is_valid_url(url):
            await append_error(
                interaction,
                non_empty_embeds(self.session.embeds),
                EmbedBuilderGUI(self.session),
                translate(self.session.language, "builder.errors.invalid_url"),
            )
            return

        if icon and not is_valid_image_attachment(icon):
            await append_error(
                interaction,
                non_empty_embeds(self.session.embeds),
                EmbedBuilderGUI(self.session),
                translate(self.session.language, "builder.errors.invalid_image"),
            )
            return

        embed.set_author(name=name, url=url or None, icon_url=icon.url if icon else None)
        await show(interaction, EmbedBuilderGUI(self.session))


class EmbedFooterModal(Modal):
    def __init__(self, session: BuilderSession) -> None:
        super().__init__(title=translate(session.language, "builder.modals.footer.title"))
        self.session: BuilderSession = session
        embed: Embed = session.active_embed

        self.text_input: TextInput = TextInput(
            label=translate(session.language, "builder.modals.footer.text.question"),
            placeholder=translate(session.language, "builder.modals.footer.text.placeholder"),
            style=TextStyle.paragraph,
            required=False,
            max_length=MAX_EMBED_FOOTER_TEXT,
            default=embed.footer.text,
        )
        self.icon_input: FileUpload = FileUpload(required=False, max_values=1)

        self.add_item(self.text_input)
        self.add_item(Label(text=translate(session.language, "builder.modals.footer.icon"), component=self.icon_input))

    async def on_submit(self, interaction: Interaction) -> None:
        from features.misc.embed_builder.views import EmbedBuilderGUI, show

        embed: Embed = self.session.active_embed
        text: str = self.text_input.value.strip()
        icon: Attachment | None = self.icon_input.values[0] if self.icon_input.values else None

        if not text:
            if icon:
                await append_error(
                    interaction,
                    non_empty_embeds(self.session.embeds),
                    EmbedBuilderGUI(self.session),
                    translate(self.session.language, "builder.errors.footer_icon_without_text"),
                )
                return

            embed.remove_footer()
            await show(interaction, EmbedBuilderGUI(self.session))
            return

        if icon and not is_valid_image_attachment(icon):
            await append_error(
                interaction,
                non_empty_embeds(self.session.embeds),
                EmbedBuilderGUI(self.session),
                translate(self.session.language, "builder.errors.invalid_image"),
            )
            return

        embed.set_footer(text=text, icon_url=icon.url if icon else None)
        await show(interaction, EmbedBuilderGUI(self.session))


class EmbedTimestampModal(Modal):
    def __init__(self, session: BuilderSession) -> None:
        super().__init__(title=translate(session.language, "builder.modals.timestamp.title"))
        self.session: BuilderSession = session
        embed: Embed = session.active_embed
        timestamp: datetime | None = embed.timestamp

        self.timestamp_input: TextInput = TextInput(
            label=translate(session.language, "builder.modals.timestamp.timestamp"),
            required=False,
            max_length=100,
            placeholder=translate(session.language, "builder.modals.timestamp.placeholder"),
            default=format_timestamp_for_input(timestamp) if timestamp is not None else None,
        )
        self.add_item(self.timestamp_input)

    async def on_submit(self, interaction: Interaction) -> None:
        from features.misc.embed_builder.views import EmbedBuilderGUI, show

        embed: Embed = self.session.active_embed
        text: str = self.timestamp_input.value.strip()

        if not text:
            embed.timestamp = None

        else:
            try:
                embed.timestamp = convert_to_datetime(text)
            except ValueError:
                await append_error(
                    interaction,
                    non_empty_embeds(self.session.embeds),
                    EmbedBuilderGUI(self.session),
                    translate(self.session.language, "builder.errors.invalid_timestamp"),
                )
                return

        await show(interaction, EmbedBuilderGUI(self.session))
