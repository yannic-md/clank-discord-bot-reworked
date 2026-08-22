from discord import Guild, Interaction
from discord.ui import Modal, TextInput

from core.discord_api.limits import MAX_SELECT_OPTION_LABEL
from core.i18n.translator import translate
from features.misc.embed_builder.session import BuilderSession
from features.misc.embed_builder.util.templates import TemplatePlaceholder, save_guild_template
from features.misc.embed_builder.validation import append_error, convert_to_emoji

MAX_TEMPLATE_NAME_LENGTH: int = MAX_SELECT_OPTION_LABEL
MAX_TEMPLATE_ICON_LENGTH: int = MAX_SELECT_OPTION_LABEL
_DEFAULT_TEMPLATE_ICON: str = "📂"


class SaveTemplateModal(Modal):
    def __init__(self, session: BuilderSession) -> None:
        super().__init__(title=translate(session.language, "builder.modals.template.title"))
        self.session: BuilderSession = session

        self.name_input: TextInput = TextInput(
            label=translate(session.language, "builder.modals.template.name.question"),
            placeholder=translate(session.language, "builder.modals.template.name.placeholder"),
            min_length=1,
            max_length=MAX_TEMPLATE_NAME_LENGTH,
        )

        self.icon_input: TextInput = TextInput(
            label=translate(session.language, "builder.modals.template.icon.question"),
            placeholder=translate(session.language, "builder.modals.template.icon.placeholder"),
            required=False,
            max_length=MAX_TEMPLATE_ICON_LENGTH,
        )

        self.add_item(self.name_input)
        self.add_item(self.icon_input)

    async def on_submit(self, interaction: Interaction) -> None:
        from features.misc.embed_builder.views import TemplatesView, show

        guild: Guild | None = interaction.guild
        assert guild is not None

        icon_text: str = self.icon_input.value.strip()
        icon: str | None = _DEFAULT_TEMPLATE_ICON if not icon_text else convert_to_emoji(icon_text, guild)
        if icon is None:
            await append_error(
                interaction,
                [TemplatesView(self.session).info_embed],
                TemplatesView(self.session),
                translate(self.session.language, "builder.errors.invalid_icon"),
            )
            return

        template: TemplatePlaceholder = TemplatePlaceholder(
            name=self.name_input.value.strip(),
            icon=icon,
            content=self.session.content,
            embeds=[embed.copy() for embed in self.session.embeds],
        )

        save_guild_template(self.session.guild_id, template)
        await show(interaction, TemplatesView(self.session))
