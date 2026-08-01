from discord import Locale
from discord.app_commands import TranslationContextTypes, locale_str
from discord.app_commands import Translator as BaseTranslator

from core.enums.language import DEFAULT_LANGUAGE, SupportedLanguage
from core.i18n.translator import lookup

# Discord locales
_DISCORD_LOCALE_TO_LANGUAGE: dict[Locale, SupportedLanguage] = {
    Locale.german: SupportedLanguage.GERMAN,
    Locale.american_english: SupportedLanguage.ENGLISH,
    Locale.british_english: SupportedLanguage.ENGLISH,
}


def cmd(key: str) -> locale_str:
    """Build a `locale_str` for slash command metadata (names, descriptions, parameters, choices) from a catalog key.

    Args:
        key (str): Dotted path into the locale catalog, e.g. "commands.guild_language.show.name".

    Returns:
        locale_str: Wraps the default-language text, tagged with `key` for translation.

    Raises:
        KeyError: If `key` has no entry for `DEFAULT_LANGUAGE`. Command metadata must
            always have a default value to register with Discord in the first place,
            so a missing entry here is a bot-author mistake, not a runtime condition.
    """
    default: str | None = lookup(DEFAULT_LANGUAGE, key)
    if default is None:
        raise KeyError(f"No '{DEFAULT_LANGUAGE}' command-metadata translation found for '{key}'.")
    return locale_str(default, key=key)


class CatalogTranslator(BaseTranslator):
    """Localizes slash command names, descriptions and parameters via the JSON locale catalog."""

    async def translate(self, string: locale_str, locale: Locale, context: TranslationContextTypes) -> str | None:
        """Resolve the catalog entry referenced by `string`'s `key` extra for the given locale.

        Args:
            string (locale_str): The source string, built via `_T`, carrying a `key` extra
                pointing into the catalog.
            locale (Locale): The Discord client locale being translated for.
            context (TranslationContextTypes): Where this string is used (command name,
                description, parameter, ...). Unused since `key` already fully identifies
                the catalog entry.

        Returns:
            str | None: The localized string, or None if `locale` is unsupported or no
                translation exists - Discord then falls back to the command's default string.
        """
        language: SupportedLanguage | None = _DISCORD_LOCALE_TO_LANGUAGE.get(locale)
        key: str | None = string.extras.get("key")

        if language is None or not isinstance(key, str):
            return None

        return lookup(language, key)
