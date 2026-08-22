from dataclasses import dataclass

from discord import Embed

# TODO: Replace this in-memory, per-process store with a real SQLAlchemy model +
# repository once template persistence is implemented (see core/db/models/).
# Templates are keyed by guild ID and are lost on every bot restart.
_TEMPLATE_STORE: dict[int, list[TemplatePlaceholder]] = {}


@dataclass
class TemplatePlaceholder:
    """In-memory placeholder for a saved embed template.
    TODO: Replace with a real database model once template persistence is implemented.
    """

    name: str
    icon: str
    content: str
    embeds: list[Embed]


def get_guild_templates(guild_id: int) -> list[TemplatePlaceholder]:
    """Return the templates currently saved for a guild (TODO: load from DB)."""
    return _TEMPLATE_STORE.setdefault(guild_id, [])


def save_guild_template(guild_id: int, template: TemplatePlaceholder) -> None:
    """Persist a template for a guild (TODO: write to DB), replacing one of the same name."""
    templates: list[TemplatePlaceholder] = get_guild_templates(guild_id)
    templates[:] = [existing for existing in templates if existing.name != template.name]
    templates.append(template)


def delete_guild_template(guild_id: int, name: str) -> None:
    """Remove a template for a guild by name (TODO: delete from DB)."""
    templates: list[TemplatePlaceholder] = get_guild_templates(guild_id)
    templates[:] = [existing for existing in templates if existing.name != name]
