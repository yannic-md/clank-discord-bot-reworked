import logging
from collections.abc import Callable
from logging import Logger
from typing import Literal

from core.enums.language import DEFAULT_LANGUAGE, SupportedLanguage
from core.i18n.catalog import CATALOG

logger: Logger = logging.getLogger("discord")
PluralCategory = Literal["zero", "one", "two", "few", "many", "other"]


def _default_plural_rule(count: int) -> PluralCategory:
    """CLDR two-category plural rule: "one" for exactly 1, "other" otherwise.

    This is the correct rule for both currently supported languages (German,
    English). Languages with more plural categories (e.g. Polish, Russian,
    Arabic) can override it via `_PLURAL_RULES` without changing call sites.

    Args:
        count (int): The quantity being pluralized for.

    Returns:
        PluralCategory: "one" or "other".
    """
    return "one" if count == 1 else "other"


_PLURAL_RULES: dict[SupportedLanguage, Callable[[int], PluralCategory]] = {}


def _plural_category(language: SupportedLanguage, count: int) -> PluralCategory:
    """Resolve which plural category a count maps to for a given language."""
    rule = _PLURAL_RULES.get(language, _default_plural_rule)
    return rule(count)


def _resolve(domains: dict[str, object], key: str) -> object | None:
    """Walk a dotted key path (e.g. "settings.language.show.current") through a language's domains.

    Args:
        domains (dict[str, object]): A language's loaded domains, as returned by `CATALOG[language]`.
        key (str): Dot-separated path; its first segment selects the domain.

    Returns:
        object | None: The value found at that path, or None if any segment is missing.
    """
    node: object = domains
    for part in key.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def lookup(language: SupportedLanguage, key: str) -> str | None:
    """Look up a single, non-pluralized string for one language, with no cross-language fallback.

    Unlike `translate`, this never falls back to `DEFAULT_LANGUAGE` and never
    returns the raw key - it exists for callers with their own "not available"
    semantics, namely discord.py's `app_commands.Translator`, which expects
    `None` when no translation exists so it can fall back to the command's
    own default string itself.

    Args:
        language (SupportedLanguage): The language to look up.
        key (str): Dotted path into the locale catalog.

    Returns:
        str | None: The raw catalog string, or None if missing or not a plain string.
    """
    entry = _resolve(CATALOG.get(language, {}), key)
    return entry if isinstance(entry, str) else None


def translate(language: SupportedLanguage, key: str, /, count: int | None = None, **variables: object) -> str:
    """Translate a dotted catalog key into the given language.

    Args:
        language (SupportedLanguage): The language to translate into.
        key (str): Dotted path into the locale catalog, e.g. "settings.language.show.current".
            The first segment selects the domain (a JSON file's name without extension).
        count (int | None, optional): If given, the entry is treated as pluralized (a
            dict of plural category -> string in the catalog) and the form matching
            `count` for `language` is selected. It is also made available to the string
            as the `{count}` variable unless explicitly overridden.
        **variables (object): Values substituted into the resolved string via `str.format`.

    Returns:
        str: The formatted, translated string. Falls back to `DEFAULT_LANGUAGE` if the key
            is missing for `language`, and to the raw key itself if it is missing entirely.
    """
    entry: object = _resolve(CATALOG.get(language, {}), key)

    if entry is None and language is not DEFAULT_LANGUAGE:
        logger.warning("Missing translation '%s' for language '%s', falling back to '%s'.", key, language, DEFAULT_LANGUAGE)
        entry = _resolve(CATALOG.get(DEFAULT_LANGUAGE, {}), key)

    if entry is None:
        logger.error("Missing translation '%s' for default language '%s'.", key, DEFAULT_LANGUAGE)
        return key

    if isinstance(entry, dict):
        if count is None:
            logger.error("Translation '%s' is pluralized but no `count` was given.", key)
            entry = next(iter(entry.values()), None)
        else:
            entry = entry.get(_plural_category(language, count), entry.get("other"))
            variables.setdefault("count", count)

    if not isinstance(entry, str):
        logger.error("Translation '%s' does not resolve to a string.", key)
        return key

    return entry.format(**variables)
