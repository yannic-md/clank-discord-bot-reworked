from discord import ButtonStyle, Embed, Interaction, SelectOption
from discord.ui import Button, Select, button, select

from core.i18n.translator import translate
from features.misc.embed_builder.modals import (
    ChannelModal,
    EmbedAuthorModal,
    EmbedColourModal,
    EmbedFooterModal,
    EmbedImagesModal,
    EmbedTimestampModal,
    EmbedTitleDescModal,
    MessageContentModal,
)
from features.misc.embed_builder.session import BuilderSession
from features.misc.embed_builder.util.embed_ops import move_active_embed, non_empty_embeds
from features.misc.embed_builder.views.base import (
    BuilderScreenView,
    create_embed_label,
    show,
)
from features.misc.embed_builder.views.embed_list import EmbedListView
from features.misc.embed_builder.views.fields import EmbedFieldsView
from features.misc.embed_builder.views.send import SendConfirmView, save_message_changes
from features.misc.embed_builder.views.templates import TemplatesView
from features.misc.embed_builder.views.webhook import WebhookView

_SELECT_OPTION_VALUES: list[tuple[str, str]] = [
    ("embed_list", "🗂️"),
    ("embed_content", "💬"),
    ("embed_colors", "🎨"),
    ("embed_title", "✏️"),
    ("embed_images", "🖼️"),
    ("embed_author", "👤"),
    ("embed_fields", "🧩"),
    ("embed_footer", "🦶"),
    ("embed_timestamp", "⏰"),
]


class EmbedBuilderGUI(BuilderScreenView):
    _MODALS: dict[str, type] = {
        "embed_content": MessageContentModal,
        "embed_colors": EmbedColourModal,
        "embed_title": EmbedTitleDescModal,
        "embed_images": EmbedImagesModal,
        "embed_author": EmbedAuthorModal,
        "embed_footer": EmbedFooterModal,
        "embed_timestamp": EmbedTimestampModal,
    }

    def __init__(self, session: BuilderSession) -> None:
        super().__init__()
        self.session: BuilderSession = session
        self.content: str | None = session.message_content

        # Discord rejects a completely empty embed outright, so the live preview only ever
        # shows embeds that actually have some content - `session.embeds` itself keeps every
        # embed (including blank ones being edited) for the editing screens to index into.
        self.embeds: list[Embed] = non_empty_embeds(session.embeds)

        if session.edit_mode:
            self.remove_item(self.send_button)
            self.remove_item(self.webhook_button)
            self.remove_item(self.channel_button)
            self.save_button.label = translate(session.language, "builder.buttons.edit_save")
            self.save_button.emoji = "💾"
        else:
            self.remove_item(self.save_button)
            self.send_button.label = translate(session.language, "builder.buttons.send")
            self.send_button.emoji = "📨"
            self.webhook_button.label = translate(session.language, "builder.buttons.webhook")
            self.webhook_button.emoji = "📢"
            self.webhook_button.disabled = not session.target_channel.permissions_for(
                session.slashcmd_author
            ).manage_webhooks

            if session.channel is not None:
                self.channel_button.label = f"#{session.channel.name}"  # show channel name
            else:
                self.channel_button.label = translate(session.language, "builder.buttons.channel")
                self.channel_button.emoji = "🔗"

        self.manage_template.label = translate(session.language, "builder.buttons.templates")
        self.manage_template.emoji = "📂"

        self.edit_options.placeholder = translate(session.language, "builder.select.placeholder")
        self.edit_options.options = [
            SelectOption(
                emoji=emoji,
                label=translate(session.language, f"builder.select.{value}.label"),
                description=translate(session.language, f"builder.select.{value}.description"),
                value=value,
            )
            for value, emoji in _SELECT_OPTION_VALUES
        ]

        # Show which embed is currently active - and let it be reordered right here -
        # only when there's more than one embed to confuse it with.
        if len(session.embeds) > 1:
            self.active_embed_label.label = create_embed_label(session, session.active_embed, session.active_embed_index + 1)
            self.main_up_button.label = translate(session.language, "builder.buttons.up")
            self.main_up_button.emoji = "⬆️"
            self.main_down_button.label = translate(session.language, "builder.buttons.down")
            self.main_down_button.emoji = "⬇️"
            self.main_up_button.disabled = session.active_embed_index <= 0
            self.main_down_button.disabled = session.active_embed_index >= len(session.embeds) - 1
        else:
            self.remove_item(self.active_embed_label)
            self.remove_item(self.main_up_button)
            self.remove_item(self.main_down_button)

    @select(
        cls=Select,
        placeholder="Was möchtest du bearbeiten?",
        min_values=1,
        max_values=1,
        row=1,
        custom_id="embed_builder:gui:edit_options",
    )
    async def edit_options(self: EmbedBuilderGUI, interaction: Interaction, select_obj: Select) -> None:
        value: str = select_obj.values[0]
        if value == "embed_list":
            await show(interaction, EmbedListView(self.session))
            return

        if value != "embed_content" and not self.session.embeds:
            # Mirrors how e.g. the colour editor already conjures up a placeholder title:
            # picking any per-embed editor with nothing to edit yet creates a blank embed.
            # `embed_content` is excluded since it edits `session.content`, not an embed.
            self.session.embeds.append(Embed())
            self.session.active_embed_index = 0

        if value == "embed_fields":
            await show(interaction, EmbedFieldsView(self.session))
            return

        await interaction.response.send_modal(self._MODALS[value](self.session))

    @button(label="Senden", style=ButtonStyle.green, row=0, custom_id="embed_builder:gui:send")
    async def send_button(self: EmbedBuilderGUI, interaction: Interaction, _button: Button) -> None:
        await show(interaction, SendConfirmView(self.session))

    @button(label="Änderung speichern", style=ButtonStyle.green, row=0, custom_id="embed_builder:gui:save")
    async def save_button(self: EmbedBuilderGUI, interaction: Interaction, _button: Button) -> None:
        await save_message_changes(interaction, self.session, self)

    @button(label="Webhook", style=ButtonStyle.blurple, row=0, custom_id="embed_builder:gui:webhook")
    async def webhook_button(self: EmbedBuilderGUI, interaction: Interaction, _button: Button) -> None:
        await show(interaction, WebhookView(self.session))

    @button(label="Kanal", style=ButtonStyle.gray, row=0, custom_id="embed_builder:gui:channel")
    async def channel_button(self: EmbedBuilderGUI, interaction: Interaction, _button: Button) -> None:
        await interaction.response.send_modal(ChannelModal(self.session))

    @button(label="Embed-Vorlagen", style=ButtonStyle.red, row=0, custom_id="embed_builder:gui:manage_template")
    async def manage_template(self: EmbedBuilderGUI, interaction: Interaction, _button: Button) -> None:
        await show(interaction, TemplatesView(self.session))

    @button(label="Active embed", style=ButtonStyle.gray, row=2, disabled=True)
    async def active_embed_label(self: EmbedBuilderGUI, interaction: Interaction, _button: Button) -> None:
        pass

    @button(label="Up", style=ButtonStyle.blurple, row=2, custom_id="embed_builder:gui:main_up")
    async def main_up_button(self: EmbedBuilderGUI, interaction: Interaction, _button: Button) -> None:
        move_active_embed(self.session, -1)
        await show(interaction, EmbedBuilderGUI(self.session))

    @button(label="Down", style=ButtonStyle.blurple, row=2, custom_id="embed_builder:gui:main_down")
    async def main_down_button(self: EmbedBuilderGUI, interaction: Interaction, _button: Button) -> None:
        move_active_embed(self.session, 1)
        await show(interaction, EmbedBuilderGUI(self.session))
