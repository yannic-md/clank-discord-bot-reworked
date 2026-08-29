import asyncio
import logging
from collections.abc import Coroutine
from logging import Logger
from typing import Any

from discord import ButtonStyle, Colour, Embed, Interaction, SelectOption
from discord.ui import Button, Select, button, select

from core.discord_api.limits import MAX_SELECT_ITEMS
from core.i18n.translator import translate
from features.misc.embed_builder.modals import SaveTemplateModal
from features.misc.embed_builder.session import BuilderSession
from features.misc.embed_builder.util.templates import (
    EmbedTemplate,
    delete_user_template,
    embed_image_urls,
    load_user_templates,
    unreachable_image_urls,
)
from features.misc.embed_builder.validation import append_error
from features.misc.embed_builder.views.base import BuilderScreenView, show, track_active_view

logger: Logger = logging.getLogger("discord")
_background_tasks: set[asyncio.Task[None]] = set()


def _run_in_background(coro: Coroutine[Any, Any, None]) -> None:
    """Fire-and-forget `coro`, holding a strong reference until it finishes so the
    event loop does not garbage-collect the task mid-flight."""
    task: asyncio.Task[None] = asyncio.create_task(coro)

    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


class TemplatesView(BuilderScreenView):
    def __init__(self, session: BuilderSession, *, status_embed: Embed | None = None) -> None:
        super().__init__()
        self.session: BuilderSession = session

        self.info_embed: Embed = Embed(
            title=translate(session.language, "builder.info.templates.title"),
            description=translate(session.language, "builder.info.templates.description"),
            colour=Colour.blurple(),
        )
        self.content: str | None = None
        self.embeds: list[Embed] = [self.info_embed]
        if status_embed is not None:
            self.embeds.append(status_embed)

        self.back_button.label = translate(session.language, "builder.buttons.back")
        self.back_button.emoji = "◀️"
        self.save_template_button.label = translate(session.language, "builder.buttons.template_save")
        self.save_template_button.emoji = "✅"
        self.delete_template_button.label = translate(session.language, "builder.buttons.template_delete")
        self.delete_template_button.emoji = "🗑️"

        templates: list[EmbedTemplate] = session.templates
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

    @button(label="Back", style=ButtonStyle.gray, row=0, custom_id="embed_builder:templates:back")
    async def back_button(self: TemplatesView, interaction: Interaction, _button: Button) -> None:
        from features.misc.embed_builder.views.gui import EmbedBuilderGUI

        await show(interaction, EmbedBuilderGUI(self.session))

    @button(label="Save", style=ButtonStyle.green, row=0, custom_id="embed_builder:templates:save")
    async def save_template_button(self: TemplatesView, interaction: Interaction, _button: Button) -> None:
        await interaction.response.send_modal(SaveTemplateModal(self.session))

    @button(label="Delete", style=ButtonStyle.red, row=0, custom_id="embed_builder:templates:delete")
    async def delete_template_button(self: TemplatesView, interaction: Interaction, _button: Button) -> None:
        name: str | None = self.session.active_template_name
        if name is None:
            await append_error(
                interaction, self.embeds, self, translate(self.session.language, "builder.errors.no_template_selected")
            )
            return

        await delete_user_template(self.session.slashcmd_author_id, name)
        self.session.templates = await load_user_templates(self.session.slashcmd_author_id)
        self.session.active_template_name = None
        await show(interaction, TemplatesView(self.session))

    def _load_status_embed(self, template: EmbedTemplate, *, broken_links: int) -> Embed:
        """The embed shown after loading `template`: a green confirmation, or an orange
        warning if some embeds could not be rebuilt or `broken_links` images are dead."""
        warnings: list[str] = []
        if template.dropped_embeds:
            warnings.append(
                translate(self.session.language, "builder.info.templates.broken_embeds", count=template.dropped_embeds)
            )

        if broken_links:
            warnings.append(translate(self.session.language, "builder.info.templates.broken_links", count=broken_links))

        if warnings:
            return Embed(description="\n".join(warnings), colour=Colour.orange())

        return Embed(
            description=translate(
                self.session.language,
                "builder.info.templates.loaded",
                count=len(self.session.embeds),
                name=template.name,
            ),
            colour=Colour.green(),
        )

    @select(
        cls=Select,
        placeholder="Select a template..",
        min_values=1,
        max_values=1,
        row=1,
        custom_id="embed_builder:templates:select",
    )
    async def template_select(self: TemplatesView, interaction: Interaction, select_obj: Select) -> None:
        name: str = select_obj.values[0]
        template: EmbedTemplate | None = next(
            (existing for existing in self.session.templates if existing.name == name), None
        )
        if template is None:
            await show(interaction, TemplatesView(self.session))
            return

        self.session.content = template.content
        self.session.embeds = [embed.copy() for embed in template.embeds]
        self.session.active_embed_index = 0
        self.session.active_template_name = name

        view: TemplatesView = TemplatesView(self.session, status_embed=self._load_status_embed(template, broken_links=0))
        track_active_view(view)
        await interaction.response.edit_message(content=view.content, embeds=view.embeds, view=view)
        view.message = await interaction.original_response()

        # check if embed images are valid - if not, warn user
        image_urls: list[str] = embed_image_urls(self.session.embeds)
        if image_urls:
            _run_in_background(self._flag_unreachable_images(interaction, view, template, image_urls))

    async def _flag_unreachable_images(
        self, interaction: Interaction, origin_view: TemplatesView, template: EmbedTemplate, image_urls: list[str]
    ) -> None:
        """Background follow-up to `template_select`: probe the restored image URLs and,
        if any no longer resolve, swap the status embed for a warning - but only while
        this exact screen is still the one on display (the user may have navigated on)."""
        try:
            broken: list[str] = await unreachable_image_urls(image_urls)
            if not broken or self.session.active_view is not origin_view:
                return

            refreshed: TemplatesView = TemplatesView(
                self.session, status_embed=self._load_status_embed(template, broken_links=len(broken))
            )

            track_active_view(refreshed)
            await interaction.edit_original_response(content=refreshed.content, embeds=refreshed.embeds, view=refreshed)
            refreshed.message = await interaction.original_response()
        except Exception:
            logger.warning("embed-builder: background image-link check failed", exc_info=True)
