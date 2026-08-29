import re
from collections.abc import Sequence
from datetime import UTC, datetime
from urllib.parse import ParseResult, urlparse
from zoneinfo import ZoneInfo

import dateparser
from discord import Attachment, Colour, Embed, Guild, Interaction, PartialEmoji, Role, Thread
from discord.abc import GuildChannel
from discord.ui import View

from core.discord_api.limits import MAX_EMBED_COUNT
from core.enums.language import SupportedLanguage
from core.i18n.translator import translate

_RGBA_PATTERN: re.Pattern[str] = re.compile(
    r"^rgba\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*[\d.]+\s*\)$", re.IGNORECASE
)
_RAW_HEX_PATTERN: re.Pattern[str] = re.compile(r"^[0-9a-fA-F]{6}$")
EVERYONE_PATTERN: re.Pattern[str] = re.compile(r"@(everyone|here)")
_USER_MENTION_PATTERN: re.Pattern[str] = re.compile(r"<@!?(\d+)>")
_ROLE_MENTION_PATTERN: re.Pattern[str] = re.compile(r"<@&(\d+)>")

# Standard unicode emoji live entirely outside this range, which lets us reject plain
# text (e.g. "abc") as an icon without needing a full emoji-data dependency.
_MIN_EMOJI_CODEPOINT = 0x2000
_MAX_ICON_LENGTH = 8

_IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp")

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


def convert_to_colour(text: str) -> Colour:
    """Parse a user-supplied colour string into a `Colour`.

    Accepts everything `Colour.from_str` supports (`#hex`, `0xhex`, `rgb(r, g, b)`)
    plus a bare 6-digit hex (`5865F2`) and `rgba(r, g, b, a)` (alpha is ignored,
    since embed colours have no transparency).

    Raises:
        ValueError: If `text` does not match any supported colour format.
    """
    value: str = text.strip()
    if not value:
        raise ValueError("empty colour")

    rgba_match: re.Match[str] | None = _RGBA_PATTERN.match(value)
    if rgba_match:
        r, g, b = (int(part) for part in rgba_match.groups())
        if any(component > 255 for component in (r, g, b)):
            raise ValueError("rgba component out of range")

        return Colour.from_rgb(r, g, b)

    if _RAW_HEX_PATTERN.match(value):
        value = f"#{value}"

    return Colour.from_str(value)


def convert_to_emoji(text: str, guild: Guild) -> str | None:
    """Validate a template icon: either a standard emoji or a custom emoji of `guild`.

    Returns:
        str | None: The emoji to store, or None if `text` is not a valid emoji.
    """
    value: str = text.strip()
    if not value:
        return None

    if value.startswith("<") and value.endswith(">"):
        try:
            partial: PartialEmoji = PartialEmoji.from_str(value)
        except ValueError:
            return None

        if partial.id is None or not any(emoji.id == partial.id for emoji in guild.emojis):
            return None

        return str(partial)

    if len(value) > _MAX_ICON_LENGTH or all(ord(char) < _MIN_EMOJI_CODEPOINT for char in value):
        return None

    return value


def is_valid_url(text: str) -> bool:
    """Check whether `text` is a well-formed `http(s)://` URL with a real (dotted) host.

    Rejects things like "https://bl4cklist" that pass a naive scheme-only check but
    are not "well formed" per Discord's own URL validation.
    """
    value: str = text.strip()
    if not value or any(char.isspace() for char in value):
        return False

    parsed: ParseResult = urlparse(value)
    return parsed.scheme in ("http", "https") and "." in parsed.netloc and len(parsed.netloc) > 3


def is_valid_image_url(text: str) -> bool:
    """Check whether `text` is a URL that plausibly points at an image (by extension)."""
    if not is_valid_url(text):
        return False

    path = urlparse(text.strip()).path.lower()
    return path.endswith(_IMAGE_EXTENSIONS)


def is_valid_image_attachment(attachment: Attachment) -> bool:
    """Check whether an uploaded `Attachment` is an image."""
    content_type: str = (attachment.content_type or "").lower()
    if content_type.startswith("image/"):
        return True

    return attachment.filename.lower().endswith(_IMAGE_EXTENSIONS)


def count_user_mentions(language: SupportedLanguage, content: str) -> str | None:
    """Count the number of distinct users `content` would ping."""
    count: int = len(set(_USER_MENTION_PATTERN.findall(content)))
    if count == 0:
        return None

    formatted_count: str = f"{count:,}"
    if language == SupportedLanguage.GERMAN:
        formatted_count = formatted_count.replace(",", ".")

    return formatted_count


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
    haystack: str = _haystack(content, embeds)
    return bool(EVERYONE_PATTERN.search(haystack)) or bool(_ROLE_MENTION_PATTERN.search(haystack))


def get_channel_placeholder(language: SupportedLanguage, channel: GuildChannel | Thread, invocation_channel_id: int) -> str:
    """ "this channel", or "the channel #foo" if `channel` isn't where the command was invoked."""
    if channel.id == invocation_channel_id:
        return translate(language, "builder.placeholders.this_channel")

    return translate(language, "builder.placeholders.other_channel", channel=channel.mention)


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
        users: str = f"{member_count:,}"
        if language == SupportedLanguage.GERMAN:
            users = users.replace(",", ".")

        return users

    return translate(language, "builder.placeholders.many")


def describe_role_mentions(content: str, guild: Guild) -> list[Role]:
    """Resolve the distinct roles `content` would ping, in first-mentioned order."""
    seen: set[int] = set()
    roles: list[Role] = []

    for role_id in _ROLE_MENTION_PATTERN.findall(content):
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
