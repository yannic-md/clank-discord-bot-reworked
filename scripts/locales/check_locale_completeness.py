"""Verify every locale file has exactly the same keys as the default-language file.

Run as: python -m scripts.check_locale_completeness
"""

import sys
from pathlib import Path

from core.enums.language import DEFAULT_LANGUAGE, SupportedLanguage
from scripts.locales._locale_json import load_locale_json

LOCALES_DIR = Path("locales")


def _collect_paths(node: object, prefix: str = "") -> set[str]:
    """Collect every dotted leaf-path in a JSON tree.

    Args:
        node (object): The (sub-)tree to walk; a plain JSON value once recursion bottoms out.
        prefix (str): The dotted path accumulated so far.

    Returns:
        set[str]: Every leaf path, e.g. {"show.name", "set.parameter.description"}.
    """
    if not isinstance(node, dict):
        return {prefix} if prefix else set()

    paths: set[str] = set()
    for key, value in node.items():
        paths |= _collect_paths(value, f"{prefix}.{key}" if prefix else key)
    return paths


def check_domain(domain_file_name: str) -> list[str]:
    """Compare one domain file's key set for every non-default language against the default language.

    Args:
        domain_file_name (str): The JSON file name to compare, e.g. "commands.json".

    Returns:
        list[str]: Human-readable descriptions of missing/extra keys, missing files, or
            duplicate JSON keys, empty if every language matches the default exactly.
    """
    default_file: Path = LOCALES_DIR / DEFAULT_LANGUAGE.value / domain_file_name
    default_data, default_duplicates = load_locale_json(default_file)
    default_paths: set[str] = _collect_paths(default_data)

    problems: list[str] = [f"{default_file}: {message}" for message in default_duplicates]
    for language in SupportedLanguage:
        if language is DEFAULT_LANGUAGE:
            continue

        other_file: Path = LOCALES_DIR / language.value / domain_file_name
        if not other_file.exists():
            problems.append(f"{other_file}: file is missing entirely")
            continue

        other_data, other_duplicates = load_locale_json(other_file)
        problems.extend(f"{other_file}: {message}" for message in other_duplicates)

        other_paths: set[str] = _collect_paths(other_data)
        problems.extend(f"{other_file}: missing key '{path}'" for path in sorted(default_paths - other_paths))
        problems.extend(
            f"{other_file}: extra key '{path}' not present in {default_file}" for path in sorted(other_paths - default_paths)
        )

    return problems


def main() -> int:
    """Check every domain found under `locales/<DEFAULT_LANGUAGE>/` for completeness in all other languages.

    Returns:
        int: 0 if every language has every key the default language has, 1 otherwise.
    """
    default_dir: Path = LOCALES_DIR / DEFAULT_LANGUAGE.value
    domain_files: list[str] = sorted(f.name for f in default_dir.glob("*.json"))
    problems: list[str] = [problem for domain in domain_files for problem in check_domain(domain)]

    if not problems:
        print(f"OK - {len(domain_files)} domain(s) fully translated for every supported language.")
        return 0

    print(f"Found {len(problems)} incomplete translation(s):\n")
    for problem in problems:
        print(f"  {problem}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
