from discord import Guild, Interaction
from discord.ui import Modal, TextInput

from core.discord_api.limits import MAX_SELECT_ITEMS, MAX_SELECT_OPTION_LABEL
from core.i18n.translator import translate
from features.misc.embed_builder.session import BuilderSession
from features.misc.embed_builder.util.embed_ops import non_empty_embeds
from features.misc.embed_builder.util.templates import EmbedTemplate, load_user_templates, save_user_template
from features.misc.embed_builder.validation import append_error, convert_to_emoji

MAX_TEMPLATE_NAME_LENGTH: int = MAX_SELECT_OPTION_LABEL
MAX_TEMPLATE_ICON_LENGTH: int = MAX_SELECT_OPTION_LABEL
_DEFAULT_TEMPLATE_ICON: str = "📂"


class SaveTemplateModal(Modal):
    def __init__(self, session: BuilderSession) -> None:
        super().__init__(title=translate(session.language, "builder.modals.template.title"))
        self.session: BuilderSession = session

        # Pre-fill with the template that is currently loaded, so submitting without
        # changing the name overwrites that same template (upsert on `(user_id, name)`).
        active: EmbedTemplate | None = next(
            (template for template in session.templates if template.name == session.active_template_name), None
        )

        self.name_input: TextInput = TextInput(
            label=translate(session.language, "builder.modals.template.name.question"),
            placeholder=translate(session.language, "builder.modals.template.name.placeholder"),
            min_length=1,
            max_length=MAX_TEMPLATE_NAME_LENGTH,
            default=session.active_template_name or None,
        )

        self.icon_input: TextInput = TextInput(
            label=translate(session.language, "builder.modals.template.icon.question"),
            placeholder=translate(session.language, "builder.modals.template.icon.placeholder"),
            required=False,
            max_length=MAX_TEMPLATE_ICON_LENGTH,
            default=active.icon if active else None,
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

        name: str = self.name_input.value.strip()
        owner_id: int = self.session.slashcmd_author_id
        existing: list[EmbedTemplate] = await load_user_templates(owner_id)
        is_new: bool = not any(template.name.casefold() == name.casefold() for template in existing)
        if is_new and len(existing) >= MAX_SELECT_ITEMS:
            self.session.templates = existing
            await append_error(
                interaction,
                [TemplatesView(self.session).info_embed],
                TemplatesView(self.session),
                translate(self.session.language, "builder.errors.template_limit", limit=MAX_SELECT_ITEMS),
            )
            return

        template: EmbedTemplate = EmbedTemplate(
            name=name,
            icon=icon,
            content=self.session.content,
            embeds=[embed.copy() for embed in non_empty_embeds(self.session.embeds)],
        )
        await save_user_template(owner_id, template)

        self.session.templates = await load_user_templates(owner_id)
        self.session.active_template_name = name
        await show(interaction, TemplatesView(self.session))
