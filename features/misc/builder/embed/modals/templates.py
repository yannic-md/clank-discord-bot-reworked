from discord import Guild, Interaction
from discord.ui import Modal, TextInput

from core.discord_api.limits import MAX_SELECT_ITEMS
from core.i18n.translator import translate
from features.misc.builder.embed.session import BuilderSession
from features.misc.builder.embed.util.embed_ops import non_empty_embeds
from features.misc.builder.embed.util.templates import EmbedTemplate, load_user_templates, save_user_template
from features.misc.builder.embed.validation import append_error
from features.misc.builder.templates import DEFAULT_TEMPLATE_ICON, MAX_TEMPLATE_ICON_LENGTH, MAX_TEMPLATE_NAME_LENGTH
from features.misc.builder.validation import convert_to_emoji


class SaveTemplateModal(Modal):
    """Modal asking for a name and icon to save the current embeds as a template."""

    def __init__(self, session: BuilderSession) -> None:
        """Pre-fill the fields with the currently loaded template, so saving without changes overwrites it."""
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
        """Validate the icon, save the template (overwriting one of the same name) and show the template list."""
        from features.misc.builder.embed.views import TemplatesView, show

        guild: Guild | None = interaction.guild
        assert guild is not None

        icon_text: str = self.icon_input.value.strip()
        icon: str | None = DEFAULT_TEMPLATE_ICON if not icon_text else convert_to_emoji(icon_text, guild)
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
