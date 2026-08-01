"""Validate that `locales/*/commands.json` satisfy Discord's slash-command limits.

Convention: any dict with a "name" and/or "description" string key is treated
as a command/group/parameter node and checked against the limits from
`core/discord_api/limits.py`. A dict directly nested under a "parameter" key
counts as one parameter; a dict directly nested under a "parameters" key is
treated as {parameter_id: {name, description}, ...} and counted by its length.
Everything below either key is checked against the parameter-specific limits.

Run as: python -m scripts.locales.check_command_locales
"""

import re
import sys
from dataclasses import dataclass
from pathlib import Path

from core.discord_api.limits import (
    MAX_SLASH_DESCRIPTION,
    MAX_SLASH_NAME,
    MAX_SLASH_PARAMETER_DESCRIPTION,
    MAX_SLASH_PARAMETER_LIMIT,
    MAX_SLASH_PARAMETER_NAME,
)
from scripts.locales._locale_json import load_locale_json

LOCALES_DIR = Path("locales")

# Mirrors Discord's actual slash-command name rule: 1-32 word characters
# (Unicode-aware, so German umlauts are fine), hyphens or underscores.
NAME_PATTERN = re.compile(r"^[-_\w]{1," + str(MAX_SLASH_NAME) + r"}$")


@dataclass(frozen=True)
class Violation:
    """A single limit violation found in a locale file."""

    file: Path
    path: str
    message: str


def _check_name(value: str, *, is_parameter: bool, file: Path, path: str) -> list[Violation]:
    """Validate a command/group/parameter name against length and character-set limits."""
    limit: int = MAX_SLASH_PARAMETER_NAME if is_parameter else MAX_SLASH_NAME
    violations: list[Violation] = []

    if not 1 <= len(value) <= limit:
        violations.append(Violation(file, path, f"name {value!r} must be 1-{limit} characters, got {len(value)}"))
        return violations
    if not NAME_PATTERN.match(value):
        violations.append(
            Violation(file, path, f"name {value!r} contains characters Discord disallows (only letters, digits, '-', '_')")
        )
    elif value != value.lower():
        violations.append(Violation(file, path, f"name {value!r} must be all lower-case"))

    return violations


def _check_description(value: str, *, is_parameter: bool, file: Path, path: str) -> list[Violation]:
    """Validate a command/group/parameter description against its length limit."""
    limit: int = MAX_SLASH_PARAMETER_DESCRIPTION if is_parameter else MAX_SLASH_DESCRIPTION

    if not 1 <= len(value) <= limit:
        return [Violation(file, path, f"description must be 1-{limit} characters, got {len(value)}")]
    return []


def _count_parameters(value: dict[str, object]) -> int:
    """Count the parameters held by a "parameter"/"parameters" node's value.

    The value is either a single {name, description} pair (one parameter,
    detected by it having its own "name" or "description" key) or a dict of
    {parameter_id: {name, description}, ...} (one parameter per entry).
    """
    if "name" in value or "description" in value:
        return 1
    return len(value)


def _check_parameter_count(node: dict[str, object], *, file: Path, path: str) -> list[Violation]:
    """Validate the number of parameters declared directly on a command node."""
    count: int = 0
    for key in ("parameter", "parameters"):
        value = node.get(key)
        if isinstance(value, dict):
            count += _count_parameters(value)

    if count > MAX_SLASH_PARAMETER_LIMIT:
        return [Violation(file, path, f"{count} parameters declared, Discord allows at most {MAX_SLASH_PARAMETER_LIMIT}")]
    return []


def _walk(node: object, *, file: Path, path: str, is_parameter: bool) -> list[Violation]:
    """Recursively check every name/description/parameter-count in a locale JSON tree."""
    if not isinstance(node, dict):
        return []

    violations: list[Violation] = []

    name: str | None = node.get("name")
    if isinstance(name, str):
        violations += _check_name(name, is_parameter=is_parameter, file=file, path=path)

    description: str | None = node.get("description")
    if isinstance(description, str):
        violations += _check_description(description, is_parameter=is_parameter, file=file, path=path)

    violations += _check_parameter_count(node, file=file, path=path)

    for key, value in node.items():
        nested_is_parameter = is_parameter or key in ("parameter", "parameters")
        violations += _walk(value, file=file, path=f"{path}.{key}", is_parameter=nested_is_parameter)

    return violations


def check_file(file: Path) -> list[Violation]:
    """Load and validate a single `commands.json` locale file.

    Args:
        file (Path): Path to the `commands.json` file to check.

    Returns:
        list[Violation]: Every limit violation found, empty if the file is clean.
    """
    data, duplicate_keys = load_locale_json(file)
    violations: list[Violation] = [Violation(file, "(duplicate key)", message) for message in duplicate_keys]
    violations += _walk(data, file=file, path=file.parent.name, is_parameter=False)
    return violations


def main() -> int:
    """Check every `locales/*/commands.json` file and report violations.

    Returns:
        int: 0 if every file satisfies the limits, 1 otherwise (suitable as a CI exit code).
    """
    files: list[Path] = sorted(LOCALES_DIR.glob("*/commands.json"))
    violations: list[Violation] = [violation for file in files for violation in check_file(file)]

    if not violations:
        print(f"OK - checked {len(files)} commands.json file(s), no slash-command limit violations.")
        return 0

    print(f"Found {len(violations)} slash-command translation limit violation(s):\n")
    for violation in violations:
        print(f"  {violation.file}: {violation.path} - {violation.message}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
