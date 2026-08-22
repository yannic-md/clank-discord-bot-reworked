from discord import ButtonStyle, Colour, Embed, Interaction, SelectOption
from discord.ui import Button, Select, button, select

from core.discord_api.limits import MAX_EMBED_FIELDS
from core.i18n.translator import translate
from features.misc.embed_builder.modals import EmbedFieldModal
from features.misc.embed_builder.session import BuilderSession
from features.misc.embed_builder.util.embed_ops import move_embed_field
from features.misc.embed_builder.validation import append_error
from features.misc.embed_builder.views.base import BuilderScreenView, show


class EmbedFieldsView(BuilderScreenView):
    def __init__(self, session: BuilderSession) -> None:
        super().__init__()
        self.session: BuilderSession = session
        fields = list(session.active_embed.fields)

        if session.active_field is None and fields:
            session.active_field = 0
        elif session.active_field is not None and session.active_field >= len(fields):
            session.active_field = len(fields) - 1 if fields else None

        self.info_embed: Embed = Embed(
            title=translate(session.language, "builder.info.fields.title"),
            description=translate(session.language, "builder.info.fields.description"),
            colour=Colour.blurple(),
        )
        self.content: str | None = None
        self.embeds: list[Embed] = [self.info_embed]

        self.back_button.label = translate(session.language, "builder.buttons.back")
        self.back_button.emoji = "◀️"
        self.add_button.label = translate(session.language, "builder.buttons.field_add")
        self.add_button.emoji = "➕"
        self.add_button.disabled = len(fields) >= MAX_EMBED_FIELDS
        self.edit_button.label = translate(session.language, "builder.buttons.field_edit")
        self.edit_button.emoji = "✏️"
        self.delete_button.label = translate(session.language, "builder.buttons.field_delete")
        self.delete_button.emoji = "🗑️"
        self.up_button.label = translate(session.language, "builder.buttons.up")
        self.up_button.emoji = "⬆️"
        self.down_button.label = translate(session.language, "builder.buttons.down")
        self.down_button.emoji = "⬇️"

        if session.active_field is None:
            self.remove_item(self.edit_button)
            self.remove_item(self.delete_button)
            self.remove_item(self.up_button)
            self.remove_item(self.down_button)
        else:
            self.up_button.disabled = session.active_field == 0
            self.down_button.disabled = session.active_field == len(fields) - 1

        if fields:
            empty_name: str = translate(session.language, "builder.placeholders.field_option_empty_name")
            self.field_select.disabled = False
            self.field_select.placeholder = translate(session.language, "builder.placeholders.fields_select")
            self.field_select.options = [
                SelectOption(
                    label=(embed_field.name or empty_name)[:100],
                    value=str(index),
                    default=index == session.active_field,
                )
                for index, embed_field in enumerate(fields)
            ]
        else:
            self.field_select.disabled = True
            self.field_select.placeholder = translate(session.language, "builder.placeholders.fields_empty")
            self.field_select.options = [SelectOption(label="—", value="__none__")]

    @button(label="Back", style=ButtonStyle.gray, row=0)
    async def back_button(self: EmbedFieldsView, interaction: Interaction, _button: Button) -> None:
        from features.misc.embed_builder.views.gui import EmbedBuilderGUI

        await show(interaction, EmbedBuilderGUI(self.session))

    @button(label="Add", style=ButtonStyle.green, row=0)
    async def add_button(self: EmbedFieldsView, interaction: Interaction, _button: Button) -> None:
        if len(self.session.active_embed.fields) >= MAX_EMBED_FIELDS:
            message = translate(self.session.language, "builder.errors.field_limit", limit=MAX_EMBED_FIELDS)
            await append_error(interaction, self.embeds, self, message)
            return

        await interaction.response.send_modal(EmbedFieldModal(self.session, None))

    @button(label="Edit", style=ButtonStyle.blurple, row=0)
    async def edit_button(self: EmbedFieldsView, interaction: Interaction, _button: Button) -> None:
        assert self.session.active_field is not None
        await interaction.response.send_modal(EmbedFieldModal(self.session, self.session.active_field))

    @button(label="Delete", style=ButtonStyle.red, row=0)
    async def delete_button(self: EmbedFieldsView, interaction: Interaction, _button: Button) -> None:
        assert self.session.active_field is not None
        self.session.active_embed.remove_field(self.session.active_field)
        fields_left: int = len(self.session.active_embed.fields)

        self.session.active_field = None if fields_left == 0 else min(self.session.active_field, fields_left - 1)
        await show(interaction, EmbedFieldsView(self.session))

    @select(cls=Select, placeholder="Select a field...", min_values=1, max_values=1, row=1)
    async def field_select(self: EmbedFieldsView, interaction: Interaction, select_obj: Select) -> None:
        self.session.active_field = int(select_obj.values[0])
        await show(interaction, EmbedFieldsView(self.session))

    @button(label="Up", style=ButtonStyle.gray, row=2)
    async def up_button(self: EmbedFieldsView, interaction: Interaction, _button: Button) -> None:
        assert self.session.active_field is not None
        move_embed_field(self.session.active_embed, self.session.active_field, -1)
        self.session.active_field -= 1
        await show(interaction, EmbedFieldsView(self.session))

    @button(label="Down", style=ButtonStyle.gray, row=2)
    async def down_button(self: EmbedFieldsView, interaction: Interaction, _button: Button) -> None:
        assert self.session.active_field is not None
        move_embed_field(self.session.active_embed, self.session.active_field, 1)
        self.session.active_field += 1
        await show(interaction, EmbedFieldsView(self.session))
