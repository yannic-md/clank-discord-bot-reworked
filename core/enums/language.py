from enum import StrEnum


class SupportedLanguage(StrEnum):
    """Languages the bot can be configured to use."""

    GERMAN = "de"
    ENGLISH = "en"


DEFAULT_LANGUAGE: SupportedLanguage = SupportedLanguage.ENGLISH
