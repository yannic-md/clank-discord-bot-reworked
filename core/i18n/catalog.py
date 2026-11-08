import json
from pathlib import Path

from core.enums.language import SupportedLanguage

LOCALES_DIR = Path("locales")


def _load_catalog() -> dict[SupportedLanguage, dict[str, object]]:
    """Load every locale file into memory once at import time.

    Each language directory under `locales/` (e.g. `locales/de/`) holds any number of
    `<domain>.json` files. Subdirectories nest the domain: `builder/embed.json` is the
    domain `builder.embed`, and a file named like its folder (`builder/builder.json`)
    is that folder's shared part, with keys read as `builder.<key>`.

    Returns:
        dict[SupportedLanguage, dict[str, object]]: For each supported language,
            a dict mapping domain name (the JSON file's path without extension,
            e.g. "common", or nested for subdirectories) to that file's parsed contents.

    Raises:
        ValueError: If a file and a directory (or two files) claim the same domain name.
    """
    catalog: dict[SupportedLanguage, dict[str, object]] = {}

    for language in SupportedLanguage:
        domains: dict[str, object] = {}
        language_dir = LOCALES_DIR / language.value

        if language_dir.is_dir():
            for file_path in sorted(language_dir.rglob("*.json")):
                *folders, name = file_path.relative_to(language_dir).with_suffix("").parts

                node = domains
                for folder in folders:
                    child = node.setdefault(folder, {})
                    if not isinstance(child, dict):
                        raise ValueError(f"Locale domain '{folder}' is both a file and a directory in {language_dir}.")
                    node = child

                content = json.loads(file_path.read_text(encoding="utf-8"))
                if folders and name == folders[-1]:
                    # `builder/builder.json` holds what its sibling files share: its keys live directly
                    # in the folder's domain (`builder.<key>`) next to the siblings (`builder.<sibling>.<key>`).
                    if overlap := node.keys() & content.keys():
                        raise ValueError(f"Locale key(s) {sorted(overlap)} collide with sibling domains in {language_dir}.")
                    node.update(content)
                    continue

                if name in node:
                    raise ValueError(f"Locale domain '{'.'.join([*folders, name])}' is defined twice in {language_dir}.")
                node[name] = content

        catalog[language] = domains

    return catalog


# Loaded once per process; translation lookups are then pure in-memory dict traversals.
CATALOG: dict[SupportedLanguage, dict[str, object]] = _load_catalog()
