import re
from collections.abc import Sequence
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import dateparser
from discord import Colour, Embed, Guild, Interaction, Role
from discord.ui import View

from core.discord_api.limits import MAX_EMBED_COUNT
from core.enums.language import SupportedLanguage
from core.i18n.translator import translate
from features.misc.builder.formatting import format_number
from features.misc.builder.validation import (
    EVERYONE_PATTERN,
    ROLE_MENTION_PATTERN,
    USER_MENTION_PATTERN,
    mentions_everyone_or_role,
)

# Users type timestamps in their own (assumed German) local time; dateparser converts
# that to UTC for storage. DATE_ORDER=YMD is what makes both ISO dates ("2026-08-14")
# *and* ambiguous day-first German dates ("04.10.2003" -> Oct 4th) resolve correctly -
# DMY alone breaks ISO parsing, plain MDY (the implicit default) misreads German dates.
_INPUT_TIMEZONE = "Europe/Berlin"
_DATEPARSER_SETTINGS = {
    "TIMEZONE": _INPUT_TIMEZONE,
    "TO_TIMEZONE": "UTC",
    "RETURN_AS_TIMEZONE_AWARE": True,
    "PREFER_DATES_FROM": "future",
    "DATE_ORDER": "YMD",
}


def count_user_mentions(content: str) -> int | None:
    """Count the number of distinct users `content` would ping, or `None` if there are none."""
    count: int = len(set(USER_MENTION_PATTERN.findall(content)))
    return count or None


def convert_to_role_mentions(content: str, guild: Guild) -> str:
    """Turn plain-text `@RoleName` occurrences into real `<@&id>` mentions.

    Modal text inputs have no mention-autocomplete, so a role typed as "@RoleName"
    is otherwise just literal text and never actually pings. Longest role names are
    substituted first so a shorter name can't "steal" a match inside a longer one.
    """
    if "@" not in content:
        return content

    for role in sorted(guild.roles, key=lambda r: len(r.name), reverse=True):
        if not role.name or role.name == "@everyone" or role.name == "@here":
            continue

        pattern: re.Pattern[str] = re.compile(r"@" + re.escape(role.name), re.IGNORECASE)
        content = pattern.sub(role.mention, content)

    return content


def convert_to_datetime(text: str) -> datetime:
    """Parse a user-supplied timestamp: relative ("in 2h", "vor 5 Tagen"), absolute
    (English or German, e.g. "2026-08-14 20:00", "14.08.2026 20:00"), time-only
    (assumes the next occurrence of that time), or a UNIX timestamp (seconds or ms).

    Raises:
        ValueError: If `text` could not be parsed into a datetime.
    """
    value = text.strip()
    if not value:
        raise ValueError("empty timestamp")

    if value.isdigit() and len(value) in (10, 13):
        epoch_seconds = int(value) / (1000 if len(value) == 13 else 1)
        return datetime.fromtimestamp(epoch_seconds, UTC)

    parsed: datetime | None = dateparser.parse(value, languages=["de", "en"], settings=_DATEPARSER_SETTINGS)
    if parsed is None:
        raise ValueError(f"could not parse timestamp: {value!r}")

    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def format_timestamp_for_input(dt: datetime) -> str:
    """Human-readable (assumed German local time) representation of an embed timestamp,
    for prefilling its edit field - the inverse of `parse_timestamp`'s timezone handling."""
    local: datetime = dt.astimezone(ZoneInfo(_INPUT_TIMEZONE))
    return local.strftime("%Y-%m-%d %H:%M")


def _embed_text_fragments(embed: Embed) -> list[str]:
    """Collect every user-supplied text field of `embed` (title, description, footer,
    author name, and each field's name/value) into a flat list, missing ones as "".
    """
    fragments: list[str] = [embed.title or "", embed.description or "", embed.footer.text or "", embed.author.name or ""]
    for embed_field in embed.fields:
        fragments.append(embed_field.name or "")
        fragments.append(embed_field.value or "")
    return fragments


def _haystack(content: str, embeds: Sequence[Embed]) -> str:
    """Join `content` and every text fragment of `embeds` into one space-separated string,
    so mention patterns can be searched for once instead of per-field/per-embed.
    """
    parts: list[str] = [content]
    for embed in embeds:
        parts.extend(_embed_text_fragments(embed))
    return " ".join(parts)


def check_for_mention_perms(content: str, embeds: Sequence[Embed]) -> bool:
    """Check whether `content`/`embeds` would ping @everyone, @here, or any role.

    Discord's `mention_everyone` permission gates all three uniformly (it's the same
    permission flag for "ping @everyone/@here" and "ping a non-mentionable role"), so
    the authorization gate must catch role mentions too, not just @everyone/@here.
    """
    return mentions_everyone_or_role(_haystack(content, embeds))


def is_everyone_mentioned(content: str) -> bool:
    """Check whether `content` contains a literal @everyone or @here."""
    return bool(EVERYONE_PATTERN.search(content))


def get_role_mention_count(language: SupportedLanguage, content: str, guild: Guild | None) -> str:
    """User count to show for an @everyone/@here mention in `content`.

    @everyone pings every member, so the guild's member count is exact. @here only
    reaches online members, which isn't available without a presence fetch, so it
    falls back to a generic "many" translation - same as when the guild itself
    isn't resolvable.
    """
    member_count: int | None = guild.member_count if guild is not None else None

    if member_count is not None and "@everyone" in content:
        return format_number(language, member_count)

    return translate(language, "builder.embed.placeholders.many")


def describe_role_mentions(content: str, guild: Guild) -> list[Role]:
    """Resolve the distinct roles `content` would ping, in first-mentioned order."""
    seen: set[int] = set()
    roles: list[Role] = []

    for role_id in ROLE_MENTION_PATTERN.findall(content):
        if role_id in seen:
            continue

        seen.add(role_id)
        role: Role | None = guild.get_role(int(role_id))
        if role is not None:
            roles.append(role)

    return roles


async def append_error(interaction: Interaction, base_embeds: list[Embed], view: View, message: str) -> None:
    """Re-render the current screen with `message` appended as an extra error embed.

    Nothing from the failed submission is applied - the screen keeps showing
    `base_embeds` unchanged, with the error embed attached below it. If `base_embeds`
    is already at Discord's 10-embed-per-message cap, the error is sent as a separate
    ephemeral reply instead, since appending one more embed would itself be rejected.
    """
    if len(base_embeds) >= MAX_EMBED_COUNT:
        await interaction.response.send_message(message, ephemeral=True)
        return

    error_embed = Embed(description=message, colour=Colour.red())
    await interaction.response.edit_message(embeds=[*base_embeds, error_embed], view=view)
