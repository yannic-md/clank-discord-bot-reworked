import asyncio
import re
from datetime import UTC, datetime
from urllib.parse import urlparse

import aiohttp

# Bound the reachability probe: a template holds a limited number of media slots,
# and every URL is one HEAD request (all fired concurrently).
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


def _discord_signature_expired(url: str, *, now: datetime) -> bool | None:
    """Whether a signed Discord CDN URL has already expired, from its `ex` parameter
    alone - no network request.

    Every image the builders upload is a signed Discord attachment URL, so this
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
    """Whether a HEAD request to `url` succeeds (status below 400) without following redirects."""
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
