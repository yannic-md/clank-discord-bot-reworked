import re
from urllib.parse import ParseResult, urlparse

from discord import AllowedMentions, Attachment, Colour, Guild, Member, PartialEmoji, Thread
from discord.abc import GuildChannel

from core.enums.language import SupportedLanguage
from core.i18n.translator import lookup, translate

_RGBA_PATTERN: re.Pattern[str] = re.compile(
    r"^rgba\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*[\d.]+\s*\)$", re.IGNORECASE
)
_RAW_HEX_PATTERN: re.Pattern[str] = re.compile(r"^[0-9a-fA-F]{6}$")
EVERYONE_PATTERN: re.Pattern[str] = re.compile(r"@(everyone|here)")
USER_MENTION_PATTERN: re.Pattern[str] = re.compile(r"<@!?(\d+)>")
ROLE_MENTION_PATTERN: re.Pattern[str] = re.compile(r"<@&(\d+)>")

# Standard unicode emoji live entirely outside this range, which lets us reject plain
# text (e.g. "abc") as an icon without needing a full emoji-data dependency.
_MIN_EMOJI_CODEPOINT = 0x2000
_MAX_ICON_LENGTH = 8

IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp")


def convert_to_colour(text: str) -> Colour:
    """Parse a user-supplied colour string into a `Colour`.

    Accepts everything `Colour.from_str` supports (`#hex`, `0xhex`, `rgb(r, g, b)`)
    plus a bare 6-digit hex (`5865F2`) and `rgba(r, g, b, a)` (alpha is ignored,
    since embed and container colours have no transparency).

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
    return path.endswith(IMAGE_EXTENSIONS)


def is_valid_image_attachment(attachment: Attachment) -> bool:
    """Check whether an uploaded `Attachment` is an image."""
    content_type: str = (attachment.content_type or "").lower()
    if content_type.startswith("image/"):
        return True

    return attachment.filename.lower().endswith(IMAGE_EXTENSIONS)


def mentions_everyone_or_role(text: str) -> bool:
    """Check whether `text` would ping @everyone, @here, or any role.

    Discord's `mention_everyone` permission gates all three uniformly (it's the same
    permission flag for "ping @everyone/@here" and "ping a non-mentionable role"), so
    the authorization gate must catch role mentions too, not just @everyone/@here.
    """
    return bool(EVERYONE_PATTERN.search(text)) or bool(ROLE_MENTION_PATTERN.search(text))


def get_channel_placeholder(language: SupportedLanguage, channel: GuildChannel | Thread, invocation_channel_id: int) -> str:
    """ "this channel", or "the channel #foo" if `channel` isn't where the command was invoked."""
    if channel.id == invocation_channel_id:
        return translate(language, "builder.placeholders.this_channel")

    return translate(language, "builder.placeholders.other_channel", channel=channel.mention)


def format_missing_permissions(language: SupportedLanguage, permissions: list[str]) -> str:
    """Creates a commad separated list to show the user all missing permissions."""
    return ", ".join((lookup(language, f"errors.permissions.{perm}") or perm).upper() for perm in permissions)


def build_allowed_mentions(channel: GuildChannel | Thread, member: Member) -> AllowedMentions:
    """Build `AllowedMentions` reflecting whether `member` may ping @everyone/@here/roles in `channel`.

    Never blocks sending: a user without the `mention_everyone` permission can still
    send content containing those mentions, they just won't actually notify anyone -
    the confirm screen warns about this beforehand (see `SendConfirmView`).
    """
    has_permission: bool = channel.permissions_for(member).mention_everyone
    return AllowedMentions(everyone=has_permission, roles=has_permission, users=True, replied_user=False)
