from discord import Embed

from features.misc.embed_builder.session import BuilderSession


def move_embed_field(embed: Embed, index: int, offset: int) -> None:
    """Swap the field at `index` with the one that is `offset` positions away, in place.

    `discord.Embed` only exposes read-only `EmbedProxy` field views, so reordering
    requires rebuilding the field list from scratch via `clear_fields`/`add_field`.
    """
    fields: list = list(embed.fields)
    target: int = index + offset
    fields[index], fields[target] = fields[target], fields[index]

    embed.clear_fields()
    for embed_field in fields:
        embed.add_field(name=embed_field.name, value=embed_field.value, inline=embed_field.inline)


def is_empty_embed(embed: Embed) -> bool:
    """Check whether `embed` has no visible content at all (Discord would reject/blank-render it)."""
    return not any(
        [
            embed.title,
            embed.description,
            embed.url,
            embed.colour,
            embed.timestamp,
            embed.author.name,
            embed.footer.text,
            embed.image.url,
            embed.thumbnail.url,
            embed.fields,
        ]
    )


def non_empty_embeds(embeds: list[Embed]) -> list[Embed]:
    """Filter out embeds with no visible content, for the payload actually sent/saved."""
    return [embed for embed in embeds if not is_empty_embed(embed)]


def move_active_embed(session: BuilderSession, offset: int) -> None:
    """Swap the active embed with the one that is `offset` positions away, and follow it."""
    current: int = session.active_embed_index
    target: int = current + offset
    session.embeds[current], session.embeds[target] = session.embeds[target], session.embeds[current]
    session.active_embed_index = target


def embed_snippet(embed: Embed, max_length: int = 40) -> str | None:
    """A short preview of an embed's content, that will be used to show the user the current active embed."""
    text: str = (embed.title or embed.description or "").strip()
    if not text:
        return None
    return text if len(text) <= max_length else f"{text[: max_length - 1]}…"
