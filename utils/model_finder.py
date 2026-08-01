import importlib
from pathlib import Path

MODELS_DIR = Path("core/db/models")


def import_all_models() -> None:
    """Import every model module so its class registers on `Base.metadata`.

    SQLAlchemy only creates a table for a model once its module has been
    imported at least once - this is what makes Alembic's autogenerate see
    it. Models can be organized into any number of subdirectories under
    `core/db/models/` without creating an init file.
    """
    if not MODELS_DIR.exists():
        return

    for file_path in sorted(MODELS_DIR.rglob("*.py")):
        importlib.import_module(".".join(file_path.with_suffix("").parts))
