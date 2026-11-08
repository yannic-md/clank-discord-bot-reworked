import logging

from discord import ButtonStyle, Colour, Interaction, SelectOption
from discord.ui import ActionRow, Container, TextDisplay

from core.discord_api.limits import MAX_SELECT_ITEMS
from core.enums.language import SupportedLanguage
from features.misc.builder.container.modals.templates import SaveTemplateModal
from features.misc.builder.container.session import ContainerBuilderSession
from features.misc.builder.container.translations import t, ts
from features.misc.builder.container.util.templates import delete_user_template, load_user_templates, nodes_from_data
from features.misc.builder.container.util.tree import component_media_urls, count_nodes
from features.misc.builder.container.views.base import (
    BuilderLayoutView,
    add_button,
    add_select,
    info_container,
    show,
    track_active_view,
)
from features.misc.builder.media_links import unreachable_image_urls
from features.misc.builder.tasks import run_in_background

logger: logging.Logger = logging.getLogger("discord")


def template_status_box(language: SupportedLanguage, name: str, *, count: int, dropped: int, broken_links: int) -> Container:
    """The box shown after loading a template: a green confirmation, or an orange warning if some
    components could not be rebuilt or `broken_links` media files are dead."""
    warnings: list[str] = []
    if dropped:
        warnings.append(t(language, "info.templates.broken_components", count=dropped))
    if broken_links:
        warnings.append(t(language, "info.templates.broken_links", count=broken_links))
    if warnings:
        return Container(TextDisplay("\n".join(warnings)), accent_colour=Colour.orange())

    text = t(language, "info.templates.loaded", count=count, name=name)
    return Container(TextDisplay(text), accent_colour=Colour.green())


class TemplatesView(BuilderLayoutView):
    """Screen to save, load and delete the user's container templates."""

    def __init__(
        self, session: ContainerBuilderSession, *, status: Container | None = None, error: str | None = None
    ) -> None:
        """`status` is an optional status box (e.g. after loading a template) and `error` an optional error box."""
        from features.misc.builder.container.views.gui import MainView

        super().__init__()
        self.session = session

        description = t(session.language, "info.templates.description")
        self.add_item(info_container(f"### {t(session.language, 'info.templates.title')}\n{description}"))

        nav_row: ActionRow = ActionRow()

        async def on_back(interaction: Interaction) -> None:
            """Go back to the main screen."""
            await show(interaction, MainView(session))

        async def on_save(interaction: Interaction) -> None:
            """Open the modal to save the current components as a template."""
            await interaction.response.send_modal(SaveTemplateModal(session))

        async def on_delete(interaction: Interaction) -> None:
            """Delete the selected template, or show an error if none is selected."""
            name = session.active_template_name
            if name is None:
                error = ts(session.language, "errors.no_template_selected")
                await show(interaction, TemplatesView(session, error=error))
                return

            await delete_user_template(session.slashcmd_author_id, name)
            session.templates = await load_user_templates(session.slashcmd_author_id)
            session.active_template_name = None
            await show(interaction, TemplatesView(session))

        templates = session.templates
        add_button(nav_row, on_back, label=ts(session.language, "buttons.back"), style=ButtonStyle.gray, emoji="◀️")
        add_button(
            nav_row, on_save, label=ts(session.language, "buttons.template_save"), style=ButtonStyle.green, emoji="✅"
        )
        add_button(
            nav_row,
            on_delete,
            label=ts(session.language, "buttons.template_delete"),
            style=ButtonStyle.red,
            emoji="🗑️",
            disabled=not templates or session.active_template_name is None,
        )
        self.add_item(nav_row)

        select_row: ActionRow = ActionRow()
        if templates:
            options = [
                SelectOption(
                    label=template.name[:100],
                    emoji=template.icon,
                    value=template.name,
                    default=template.name == session.active_template_name,
                )
                for template in templates[:MAX_SELECT_ITEMS]
            ]
            placeholder = ts(session.language, "placeholders.templates_select")
        else:
            options = [SelectOption(label="—", value="__none__")]
            placeholder = ts(session.language, "placeholders.templates_empty")

        async def on_select(interaction: Interaction) -> None:
            """Replace the current components with the chosen template and report skipped components."""
            name = template_select.values[0]
            template = next((existing for existing in session.templates if existing.name == name), None)
            if template is None:
                await show(interaction, TemplatesView(session))
                return

            nodes, dropped = nodes_from_data(session, template.components)
            session.components = nodes
            session.active_selection.clear()
            session.active_template_name = name

            count = count_nodes(nodes)
            status = template_status_box(session.language, name, count=count, dropped=dropped, broken_links=0)
            view = TemplatesView(session, status=status)
            track_active_view(view)
            await interaction.response.edit_message(view=view)
            view.message = await interaction.original_response()

            # check if uploaded media is still available - if not, warn the user
            media_urls = component_media_urls(nodes)
            if media_urls:
                run_in_background(
                    _flag_unreachable_media(interaction, view, name=name, count=count, dropped=dropped, urls=media_urls)
                )

        template_select = add_select(select_row, on_select, options=options, placeholder=placeholder, disabled=not templates)
        self.add_item(select_row)

        if status is not None:
            self.add_status(status)
        if error:
            self.add_error(error)


async def _flag_unreachable_media(
    interaction: Interaction, origin_view: TemplatesView, *, name: str, count: int, dropped: int, urls: list[str]
) -> None:
    """Background follow-up to loading a template: probe the restored media URLs and, if any no
    longer resolve, swap the status box for a warning - but only while this exact screen is still
    the one on display (the user may have navigated on)."""
    try:
        broken = await unreachable_image_urls(urls)
        session = origin_view.session
        if not broken or session.active_view is not origin_view:
            return

        status = template_status_box(session.language, name, count=count, dropped=dropped, broken_links=len(broken))
        refreshed = TemplatesView(session, status=status)
        track_active_view(refreshed)
        await interaction.edit_original_response(view=refreshed)
        refreshed.message = await interaction.original_response()
    except Exception:
        logger.warning("container-builder: background media-link check failed", exc_info=True)
