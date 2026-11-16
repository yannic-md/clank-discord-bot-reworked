from dataclasses import dataclass, field

from core.db.repositories.container_builder import container_template_repository
from core.db.repositories.embed_builder import embed_template_repository
from core.discord_api.limits import MAX_SELECT_ITEMS
from features.misc.builder.interactive.models import PayloadKind


@dataclass(frozen=True, slots=True)
class TemplateChoice:
    """One saved template a message action can take a snapshot of."""

    name: str
    icon: str
    content: str
    """The message text saved with an embed template (empty for container templates)."""
    data: list[dict[str, object]]
    """The template's stored payload: embed dicts, or component nodes."""


@dataclass(frozen=True, slots=True)
class TemplateChoices:
    """The templates of a user that a message action can pick from, per builder."""

    embed: list[TemplateChoice] = field(default_factory=list)
    container: list[TemplateChoice] = field(default_factory=list)


async def load_template_choices(user_id: int, kind: PayloadKind) -> TemplateChoices:
    """The templates `user_id` saved in the builder that makes templates of `kind` - as many as fit into one dropdown.

    A builder offers its own templates only: the embed builder those of embeds, the container builder those of
    containers. The templates of the other builder are not loaded at all."""
    if kind is PayloadKind.EMBED:
        embed_records = await embed_template_repository.list_user_templates(user_id)
        return TemplateChoices(
            embed=[
                TemplateChoice(record.name, record.icon, record.content, record.embeds_data)
                for record in embed_records[:MAX_SELECT_ITEMS]
                if record.embeds_data
            ]
        )
    if kind is PayloadKind.CONTAINER:
        container_records = await container_template_repository.list_user_templates(user_id)
        return TemplateChoices(
            container=[
                TemplateChoice(record.name, record.icon, "", record.components_data)
                for record in container_records[:MAX_SELECT_ITEMS]
                if record.components_data
            ]
        )
    return TemplateChoices()
