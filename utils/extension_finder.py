import ast
from pathlib import Path

PACKAGE_EXTENSION_DIR = Path("features")


def _has_setup_function(file_path: Path) -> bool:
    """Checks whether a Python file defines a top-level `setup` function.

    Uses AST parsing instead of actual import so that files with broken
    dependencies or side effects are not executed during scanning.

    Args:
        file_path (Path): Path to the .py file to check.

    Returns:
        bool: True if the file contains `def setup` or `async def setup`.
    """
    try:
        source = file_path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(file_path))
    except SyntaxError, UnicodeDecodeError:
        return False

    return any(isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "setup" for node in tree.body)


def discover_extensions() -> list[str]:
    """Recursively scans 'PACKAGE_EXTENSION_DIR/' for loadable extensions.

    Every .py file with a top-level `setup` function (discord.py
    extension entry point) is returned as an import path.

    Returns:
        list[str]: Dotted import paths of all found extensions,
            e.g., ["features.misc.commands", "features.gift.commands"].
    """
    extensions: list[str] = []

    if not PACKAGE_EXTENSION_DIR.exists():
        return extensions

    for file_path in sorted(PACKAGE_EXTENSION_DIR.rglob("*.py")):
        if not _has_setup_function(file_path):
            continue

        relative_path = file_path.relative_to(PACKAGE_EXTENSION_DIR.parent).with_suffix("")
        extensions.append(".".join(relative_path.parts))

    return extensions
