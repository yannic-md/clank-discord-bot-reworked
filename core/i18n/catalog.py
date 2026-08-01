import json
from pathlib import Path

from core.enums.language import SupportedLanguage

LOCALES_DIR = Path("locales")


def _load_catalog() -> dict[SupportedLanguage, dict[str, object]]:
    """Load every locale file into memory once at import time.

    Each supported language has its own directory under `locales/` (e.g.
    `locales/de/`), containing any number of domain files such as
    `common.json` or `settings.json`. New domains can be added freely by
    dropping another `<domain>.json` file into each language directory.

    Returns:
        dict[SupportedLanguage, dict[str, object]]: For each supported language,
            a dict mapping domain name (the JSON file's stem, e.g. "common") to
            that file's parsed contents.
    """
    catalog: dict[SupportedLanguage, dict[str, object]] = {}

    for language in SupportedLanguage:
        domains: dict[str, object] = {}
        language_dir = LOCALES_DIR / language.value

        if language_dir.is_dir():
            for file_path in sorted(language_dir.glob("*.json")):
                domains[file_path.stem] = json.loads(file_path.read_text(encoding="utf-8"))

        catalog[language] = domains

    return catalog


# Loaded once per process; translation lookups are then pure in-memory dict traversals.
CATALOG: dict[SupportedLanguage, dict[str, object]] = _load_catalog()
