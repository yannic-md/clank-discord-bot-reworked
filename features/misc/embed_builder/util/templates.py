import asyncio
import logging
import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from logging import Logger
from urllib.parse import urlparse

import aiohttp
from discord import Embed

from core.db.repositories.embed_builder import embed_template_repository as repo
from core.db.repositories.embed_builder.embed_template_repository import EmbedTemplateRecord

logger: Logger = logging.getLogger("discord")

# Bound the reachability probe: a template holds at most 10 embeds, each with at
# most 4 image slots, and every URL is one HEAD request (all fired concurrently).
_MAX_URLS_TO_PROBE: int = 40

# The HTTP probe only runs for non-Discord URLs (see `unreachable_image_urls`), and
# it is advisory - a false "unreachable" only adds a warning, the template still
# loads fully - so the timeouts are tight. A live image answers a HEAD in well under
# a second; anything slower (dead host) is cut off fast. `sock_connect`/`sock_read`
# bound the two ways a single URL can hang; `total` is the ceiling for the whole DNS.
_PROBE_TIMEOUT: aiohttp.ClientTimeout = aiohttp.ClientTimeout(total=2.0, sock_connect=1.0, sock_read=1.0)

_DISCORD_CDN_HOSTS: frozenset[str] = frozenset({"cdn.discordapp.com", "media.discordapp.net"})

# Discord signs CDN URLs with `?ex=<hex unix seconds>&is=<hex>&hm=<hmac>` (expiry, issued, signature).
# Reading `ex` tells us an attachment URL's expiry with no request.
_SIGNED_URL_EXPIRY: re.Pattern[str] = re.compile(r"[?&]ex=([0-9a-fA-F]+)")

# `ex` is only trusted inside a sane window: Discord's URL signing did not exist
# before 2023 and its URLs live ~24h, so a value outside this range means the format
# is not what we assume - the caller should then probe instead of trusting it.
_EXPIRY_EPOCH_FLOOR: int = 1_672_531_200  # 2023-01-01 UTC
_EXPIRY_FUTURE_SLACK_SECONDS: int = 366 * 24 * 60 * 60


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


def _discord_signature_expired(url: str, *, now: datetime) -> bool | None:
    """Whether a signed Discord CDN URL has already expired, from its `ex` parameter
    alone - no network request.

    Every image the builder uploads is a signed Discord attachment URL, so this
    settles the common case instantly and exactly. Returns None when the URL cannot
    answer it - not a Discord CDN URL, unsigned, or an `ex` outside the plausible
    range - so the caller falls back to an HTTP probe.
    """
    if urlparse(url).hostname not in _DISCORD_CDN_HOSTS:
        return None

    match: re.Match[str] | None = _SIGNED_URL_EXPIRY.search(url)
    if match is None:
        return None

    expiry_seconds: int = int(match.group(1), 16)  # the pattern only captures valid hex
    now_seconds: float = now.timestamp()
    if not _EXPIRY_EPOCH_FLOOR <= expiry_seconds <= now_seconds + _EXPIRY_FUTURE_SLACK_SECONDS:
        return None

    return expiry_seconds <= now_seconds


async def _is_reachable(session: aiohttp.ClientSession, url: str) -> bool:
    try:
        async with session.head(url, allow_redirects=False) as response:
            return response.status < 400
    except aiohttp.ClientError, TimeoutError:
        return False


async def unreachable_image_urls(urls: list[str]) -> list[str]:
    """The subset of `urls` that no longer resolve.

    Signed Discord CDN URLs are judged from their embedded expiry alone (instant,
    exact) - only genuinely external image URLs get an HTTP probe. Never raises:
    any probe failure just marks that URL unreachable. Callers use this to warn
    about a template whose images have expired, without blocking the rest of the
    template from loading.
    """
    now: datetime = datetime.now(UTC)
    unreachable: list[str] = []
    needs_probe: list[str] = []

    for url in urls[:_MAX_URLS_TO_PROBE]:
        expired: bool | None = _discord_signature_expired(url, now=now)
        if expired:
            unreachable.append(url)
        elif expired is None:
            needs_probe.append(url)
        # expired is False -> signature still valid, assume the asset is there.

    if needs_probe:
        async with aiohttp.ClientSession(timeout=_PROBE_TIMEOUT) as session:
            results: list[bool] = await asyncio.gather(*(_is_reachable(session, url) for url in needs_probe))
        unreachable.extend(url for url, reachable in zip(needs_probe, results, strict=True) if not reachable)

    return unreachable
