from discord import Interaction
from discord.ui import Modal, TextInput

from core.discord_api.limits import MAX_SELECT_ITEMS
from features.misc.builder.container.models import ContainerTemplate
from features.misc.builder.container.session import ContainerBuilderSession
from features.misc.builder.container.translations import t, ts
from features.misc.builder.container.util.templates import load_user_templates, node_to_data, save_user_template
from features.misc.builder.container.util.tree import non_empty_nodes
from features.misc.builder.templates import DEFAULT_TEMPLATE_ICON, MAX_TEMPLATE_ICON_LENGTH, MAX_TEMPLATE_NAME_LENGTH
from features.misc.builder.validation import convert_to_emoji


class SaveTemplateModal(Modal):
    """Modal asking for a name and icon to save the current components as a template."""

    def __init__(self, session: ContainerBuilderSession) -> None:
        """Pre-fill the fields with the currently loaded template, so saving without changes overwrites it."""
        super().__init__(title=ts(session.language, "modals.template.title"))
        self.session = session

        # Pre-fill with the template that is currently loaded, so submitting without
        # changing the name overwrites that same template (upsert on `(user_id, name)`).
        active = next((template for template in session.templates if template.name == session.active_template_name), None)

        self.name_input: TextInput = TextInput(
            label=ts(session.language, "modals.template.name.question"),
            placeholder=ts(session.language, "modals.template.name.placeholder"),
            min_length=1,
            max_length=MAX_TEMPLATE_NAME_LENGTH,
            default=session.active_template_name or None,
        )
        self.icon_input: TextInput = TextInput(
            label=ts(session.language, "modals.template.icon.question"),
            placeholder=ts(session.language, "modals.template.icon.placeholder"),
            required=False,
            max_length=MAX_TEMPLATE_ICON_LENGTH,
            default=active.icon if active else None,
        )
        self.add_item(self.name_input)
        self.add_item(self.icon_input)

    async def on_submit(self, interaction: Interaction) -> None:
        """Validate the input, save the template (overwriting one of the same name) and show the template list."""
        from features.misc.builder.container.views.base import show
        from features.misc.builder.container.views.templates import TemplatesView

        session = self.session
        guild = interaction.guild
        assert guild is not None

        icon_text = self.icon_input.value.strip()
        icon = DEFAULT_TEMPLATE_ICON if not icon_text else convert_to_emoji(icon_text, guild)
        if icon is None:
            error = ts(session.language, "errors.invalid_icon")
            await show(interaction, TemplatesView(session, error=error))
            return

        nodes = non_empty_nodes(session.components)
        if not nodes:
            error = t(session.language, "errors.nothing_to_save")
            await show(interaction, TemplatesView(session, error=error))
            return

        name = self.name_input.value.strip()
        owner_id = session.slashcmd_author_id
        existing = await load_user_templates(owner_id)
        is_new = not any(template.name.casefold() == name.casefold() for template in existing)
        if is_new and len(existing) >= MAX_SELECT_ITEMS:
            session.templates = existing
            error = ts(session.language, "errors.template_limit", limit=MAX_SELECT_ITEMS)
            await show(interaction, TemplatesView(session, error=error))
            return

        template = ContainerTemplate(name=name, icon=icon, components=[node_to_data(node) for node in nodes])
        await save_user_template(owner_id, template)

        session.templates = await load_user_templates(owner_id)
        session.active_template_name = name
        await show(interaction, TemplatesView(session))
