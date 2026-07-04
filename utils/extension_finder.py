import pkgutil
from pathlib import Path

# Folders whose subfolders are loaded as packages (features.gift, features.security, ...)
PACKAGE_EXTENSION_DIRS = ["features"]

# Folders whose individual .py files are loaded as modules (system.audit, misc.commands, ...)
FLAT_EXTENSION_DIRS = ["system", "misc"]

def discover_extensions() -> list[str]:
    """ Discover available bot extensions.

    The function scans the directories listed in ``PACKAGE_EXTENSION_DIRS`` for
    package-based extensions and the directories listed in ``FLAT_EXTENSION_DIRS``
    for standalone Python modules. It returns fully qualified extension names
    that can be loaded by the bot.

    Returns:
        list[str]: A list of import paths for discovered extensions.
    """
    extensions: list[str] = []

    for base_dir in PACKAGE_EXTENSION_DIRS:
        base_path = Path(base_dir)
        if not base_path.exists():
            continue
        for entry in base_path.iterdir():
            if entry.is_dir() and (entry / "__init__.py").exists():
                extensions.append(f"{base_dir}.{entry.name}")

    for base_dir in FLAT_EXTENSION_DIRS:
        base_path = Path(base_dir)
        if not base_path.exists():
            continue

        for _, module_name, is_pkg in pkgutil.iter_modules([str(base_path)]):
            if not is_pkg:
                extensions.append(f"{base_dir}.{module_name}")

    return extensions