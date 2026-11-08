import logging
from collections.abc import Iterable
from dataclasses import dataclass
from logging import Logger

from discord import Embed

from core.db.repositories.embed_builder import embed_template_repository as repo
from core.db.repositories.embed_builder.embed_template_repository import EmbedTemplateRecord

logger: Logger = logging.getLogger("discord")


@dataclass(frozen=True, slots=True)
class EmbedTemplate:
    """A saved embed-builder draft, as the builder screens consume it.

    Persisted per user in the `embed_builder_templates` table; the embeds round-trip
    through `Embed.to_dict()` / `Embed.from_dict()`.
    """

    name: str
    icon: str
    content: str
    embeds: list[Embed]
    dropped_embeds: int = 0
    """How many stored embed payloads could not be rebuilt into a usable `Embed`
    (corrupted JSON structure, hand-edited row, incompatible discord.py change).
    The template still loads with whatever survived; the screen warns about it."""


def _assert_readable(embed: Embed) -> None:
    """Touch every accessor the builder relies on.

    `Embed.from_dict` is lenient - it stores e.g. a non-dict `author` or a
    non-list `fields` verbatim and only blows up when that part is later read
    (`EmbedProxy` doing `dict.update` on a string). Forcing those reads here means
    a structurally broken payload fails in `_to_template`, where it is caught and
    skipped, instead of mid-render on the next screen.
    """
    _ = (
        embed.title,
        embed.description,
        embed.url,
        embed.colour,
        embed.timestamp,
        embed.author.name,
        embed.author.icon_url,
        embed.footer.text,
        embed.footer.icon_url,
        embed.image.url,
        embed.thumbnail.url,
        [(field.name, field.value, field.inline) for field in embed.fields],
    )


def _rebuild_embed(data: object) -> Embed:
    embed = Embed.from_dict(data)  # type: ignore[arg-type]
    _assert_readable(embed)
    return embed


def _to_template(record: EmbedTemplateRecord) -> EmbedTemplate:
    embeds: list[Embed] = []
    dropped: int = 0

    for data in record.embeds_data:
        try:
            embeds.append(_rebuild_embed(data))
        except Exception:
            dropped += 1
            logger.warning("embed-builder: skipping unrebuildable embed in template %r", record.name, exc_info=True)

    return EmbedTemplate(
        name=record.name,
        icon=record.icon,
        content=record.content,
        embeds=embeds,
        dropped_embeds=dropped,
    )


async def load_user_templates(user_id: int) -> list[EmbedTemplate]:
    """Every template owned by a user, ordered by name."""
    return [_to_template(record) for record in await repo.list_user_templates(user_id)]


async def save_user_template(user_id: int, template: EmbedTemplate) -> None:
    """Persist a template for a user, replacing an existing one of the same name."""
    await repo.upsert_user_template(
        user_id=user_id,
        name=template.name,
        icon=template.icon,
        content=template.content,
        embeds_data=[dict(embed.to_dict()) for embed in template.embeds],
    )


async def delete_user_template(user_id: int, name: str) -> None:
    """Remove a template owned by a user, by name."""
    await repo.delete_user_template(user_id, name)


def embed_image_urls(embeds: Iterable[Embed]) -> list[str]:
    """Every distinct `http(s)` image/icon URL referenced across `embeds`, in first-seen order.

    These are the uploaded attachments a template restores. Discord serves uploads
    behind signed, expiring URLs, so a URL stored in a template weeks ago may no
    longer resolve - `unreachable_image_urls` checks which.
    """
    seen: set[str] = set()
    urls: list[str] = []

    for embed in embeds:
        candidates = (embed.image.url, embed.thumbnail.url, embed.author.icon_url, embed.footer.icon_url)
        for url in candidates:
            if url and url.startswith(("http://", "https://")) and url not in seen:
                seen.add(url)
                urls.append(url)

    return urls
