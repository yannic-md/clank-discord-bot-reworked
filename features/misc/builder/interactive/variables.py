import re
from collections.abc import Callable, Iterable, Sequence
from datetime import UTC, datetime

from discord import Guild, Member
from discord.abc import GuildChannel, Messageable
from discord.utils import format_dt

VARIABLES: tuple[str, ...] = (
    "user",
    "user.name",
    "user.username",
    "user.id",
    "user.created",
    "user.joined",
    "server",
    "server.members",
    "channel",
    "date",
    "time",
)
"""The placeholders every message action knows, in the order the editor lists them."""
FORM_VARIABLES: tuple[str, ...] = ("answers", "answer.1")
"""The placeholders that only mean something once a form was submitted (`answer.1` stands for `answer.1` to `answer.9`
and further - one per question)."""

_VARIABLE: re.Pattern[str] = re.compile(
    r"\{(" + "|".join(re.escape(name) for name in VARIABLES) + r"|answers|answer\.[1-9]\d?)}"
)
_PLACEHOLDER_LIKE: re.Pattern[str] = re.compile(r"\{([A-Za-z][\w.]*)}")
"""Anything that looks like a placeholder: a name in curly braces. Braces around something that is no name (`{}`,
`{1,2}`, `{two words}`) are ordinary text."""
NO_ANSWER: str = "—"
"""What stands in for a question that was left unanswered, and for a date that is not known."""


def find_variables(texts: Iterable[str]) -> tuple[list[str], list[str]]:
    """The placeholders the texts use, as the names without braces: `(known, unknown)`, each name once, in the order they
    first appear. The known ones are replaced when a message is sent by an action (see `render_variables`); the
    unknown ones - mostly typos - are never replaced and stay as typed."""
    known: dict[str, None] = {}
    unknown: dict[str, None] = {}
    for text in texts:
        for match in _PLACEHOLDER_LIKE.finditer(text):
            name = match.group(1)
            (known if _VARIABLE.fullmatch(match.group(0)) else unknown)[name] = None
    return list(known), list(unknown)


def render_variables(
    text: str,
    *,
    member: Member,
    guild: Guild,
    channel: Messageable | GuildChannel | None,
    answers: Sequence[tuple[str, str]] = (),
    now: datetime | None = None,
) -> str:
    """Fill the placeholders of a message the person who used a button or dropdown receives.

    Only the known placeholders are replaced - everything else, including other curly braces, stays as typed:

    * `{user}` (mention), `{user.name}` (display name), `{user.username}` (account name) and `{user.id}`;
    * `{user.created}` and `{user.joined}` - the day the account was created and the person joined the server;
    * `{server}` (name) and `{server.members}` (how many people are on it);
    * `{channel}` (mention);
    * `{date}` and `{time}` - today and the time of day, shown in the time zone of whoever reads the message.

    After a form was submitted there are also `{answers}` (every question with its answer) and `{answer.1}`,
    `{answer.2}`, ... (the answer to one question).
    """
    moment = now or datetime.now(UTC)

    def replace(match: re.Match[str]) -> str:
        """The text that replaces one matched `{placeholder}`."""
        name = match.group(1)
        if name == "answers":
            return "\n\n".join(f"**{label}**\n{value or NO_ANSWER}" for label, value in answers) or NO_ANSWER
        if name.startswith("answer."):
            index = int(name.removeprefix("answer.")) - 1
            return (answers[index][1] or NO_ANSWER) if index < len(answers) else NO_ANSWER
        # Only the one that was asked for is worked out - a missing value of another one must not matter.
        values: dict[str, Callable[[], str]] = {
            "user": lambda: member.mention,
            "user.name": lambda: member.display_name,
            "user.username": lambda: member.name,
            "user.id": lambda: str(member.id),
            "user.created": lambda: format_dt(member.created_at, "D"),
            "user.joined": lambda: format_dt(member.joined_at, "D") if member.joined_at is not None else NO_ANSWER,
            "server": lambda: guild.name,
            "server.members": lambda: str(guild.member_count or len(guild.members)),
            "channel": lambda: getattr(channel, "mention", ""),
            "date": lambda: format_dt(moment, "D"),
            "time": lambda: format_dt(moment, "t"),
        }
        return values[name]()

    return _VARIABLE.sub(replace, text)
