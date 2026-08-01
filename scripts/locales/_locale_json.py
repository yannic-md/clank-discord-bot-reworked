"""Shared JSON loading for the locale-checking scripts, with duplicate-key detection."""

import json
from pathlib import Path


def load_locale_json(file: Path) -> tuple[object, list[str]]:
    """Parse a locale JSON file, flagging any object with a repeated key.

    Args:
        file (Path): The JSON file to parse.

    Returns:
        tuple[object, list[str]]: The parsed data, and a description
            of every duplicate key found, empty if there were none.
    """
    problems: list[str] = []

    def hook(pairs: list[tuple[str, object]]) -> dict[str, object]:
        counts: dict[str, int] = {}
        for key, _ in pairs:
            counts[key] = counts.get(key, 0) + 1

        for key, count in counts.items():
            if count > 1:
                problems.append(f"key {key!r} appears {count} times in the same object - only the last value is kept")

        return dict(pairs)

    data = json.loads(file.read_text(encoding="utf-8"), object_pairs_hook=hook)
    return data, problems
