from discord import ButtonStyle, Colour, Embed, Interaction, SelectOption
from discord.ui import Button, Select, button, select

from core.discord_api.limits import MAX_SELECT_ITEMS
from core.i18n.translator import translate
from features.misc.embed_builder.modals import SaveTemplateModal
from features.misc.embed_builder.session import BuilderSession
from features.misc.embed_builder.util.templates import TemplatePlaceholder, delete_guild_template
from features.misc.embed_builder.validation import append_error
from features.misc.embed_builder.views.base import BuilderScreenView, show


class TemplatesView(BuilderScreenView):
    def __init__(self, session: BuilderSession) -> None:
        super().__init__()
        self.session: BuilderSession = session

        self.info_embed: Embed = Embed(
            title=translate(session.language, "builder.info.templates.title"),
            description=translate(session.language, "builder.info.templates.description"),
            colour=Colour.blurple(),
        )
        self.content: str | None = None
        self.embeds: list[Embed] = [self.info_embed]

        self.back_button.label = translate(session.language, "builder.buttons.back")
        self.back_button.emoji = "◀️"
        self.save_template_button.label = translate(session.language, "builder.buttons.template_save")
        self.save_template_button.emoji = "✅"
        self.delete_template_button.label = translate(session.language, "builder.buttons.template_delete")
        self.delete_template_button.emoji = "🗑️"

        templates: list[TemplatePlaceholder] = session.templates
        if templates:
            self.template_select.disabled = False
            self.template_select.placeholder = translate(session.language, "builder.placeholders.templates_select")
            self.template_select.options = [
                SelectOption(
                    label=template.name[:100],
                    emoji=template.icon,
                    value=template.name,
                    default=template.name == session.active_template_name,
                )
                for template in templates[:MAX_SELECT_ITEMS]
            ]
            self.delete_template_button.disabled = session.active_template_name is None
        else:
            self.template_select.disabled = True
            self.template_select.placeholder = translate(session.language, "builder.placeholders.templates_empty")
            self.template_select.options = [SelectOption(label="—", value="__none__")]
            self.delete_template_button.disabled = True

    @button(label="Back", style=ButtonStyle.gray, row=0)
    async def back_button(self: TemplatesView, interaction: Interaction, _button: Button) -> None:
        from features.misc.embed_builder.views.gui import EmbedBuilderGUI

        await show(interaction, EmbedBuilderGUI(self.session))

    @button(label="Save", style=ButtonStyle.green, row=0)
    async def save_template_button(self: TemplatesView, interaction: Interaction, _button: Button) -> None:
        await interaction.response.send_modal(SaveTemplateModal(self.session))

    @button(label="Delete", style=ButtonStyle.red, row=0)
    async def delete_template_button(self: TemplatesView, interaction: Interaction, _button: Button) -> None:
        name: str | None = self.session.active_template_name
        if name is None:
            await append_error(
                interaction, self.embeds, self, translate(self.session.language, "builder.errors.no_template_selected")
            )
            return

        delete_guild_template(self.session.guild_id, name)
        self.session.active_template_name = None
        await show(interaction, TemplatesView(self.session))

    @select(cls=Select, placeholder="Select a template...", min_values=1, max_values=1, row=1)
    async def template_select(self: TemplatesView, interaction: Interaction, select_obj: Select) -> None:
        name: str = select_obj.values[0]
        template = next((existing for existing in self.session.templates if existing.name == name), None)
        if template is not None:
            self.session.content = template.content
            self.session.embeds = [embed.copy() for embed in template.embeds]
            self.session.active_embed_index = 0
            self.session.active_template_name = name

        await show(interaction, TemplatesView(self.session))
