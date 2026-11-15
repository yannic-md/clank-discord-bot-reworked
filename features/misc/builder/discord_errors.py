import re

from discord import HTTPException

from core.enums.language import SupportedLanguage
from core.i18n.translator import lookup, translate

INVALID_FORM_BODY: int = 50035
"""Discord's error code for a message with a part it refuses (an emoji, a link, a text that is too long)."""
UNKNOWN_CHANNEL: int = 10003
"""Discord's error code for a channel that no longer exists."""
MAX_PROBLEMS_SHOWN: int = 3

_PROBLEM: re.Pattern[str] = re.compile(r"^In (?P<path>\S+): (?P<message>.+)$", re.MULTILINE)
_ENTRY: re.Pattern[str] = re.compile(r"\.(\d+)\.")


def _subject(language: SupportedLanguage, path: str) -> str:
    """What part of the message a problem is about, from the path Discord gives ("components.0.components.2.emoji.name")."""
    parts = [part for part in path.split(".") if not part.isdecimal()]
    for part in reversed(parts):
        known = lookup(language, f"builder.errors.rejected_subject.{part}")
        if known:
            return known
    return parts[-1] if parts else path


def rejection_problems(language: SupportedLanguage, error: HTTPException) -> list[str]:
    """The parts of a message Discord refused as short lines: "Emoji: Invalid emoji" (at most a few)."""
    lines: list[str] = []
    for found in _PROBLEM.finditer(error.text or ""):
        line = f"{_subject(language, found['path'])}: {found['message'].strip()}"
        if line not in lines:
            lines.append(line)
    return lines[:MAX_PROBLEMS_SHOWN]


def send_problem_text(language: SupportedLanguage, error: HTTPException) -> str | None:
    """An explanation for an error that sending (or saving) a message ran into - or `None` if it is one nobody could have
    seen coming, which is left to the error handler."""
    if error.code == UNKNOWN_CHANNEL:
        return translate(language, "builder.errors.channel_deleted")

    if error.status == 400 and error.code == INVALID_FORM_BODY:
        problems = rejection_problems(language, error)
        listed = (
            "\n".join(f"> {problem}" for problem in problems)
            or f"> {translate(language, 'builder.errors.rejected_unknown')}"
        )
        return translate(language, "builder.errors.discord_rejected", problems=listed)
    return None
