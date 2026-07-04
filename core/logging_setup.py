import logging
from logging import Formatter, handlers
from logging.handlers import RotatingFileHandler
from pathlib import Path


def setup_logging() -> logging.Logger:
    """
    Configure and initialize the Discord logger with file rotation.

    Sets up a rotating file handler for the Discord logger that writes to
    'logs/discord.log' with automatic rotation when the log file reaches
    500 MB in size. Up to 3 backup files are retained.

    Returns:
        logging.Logger: The configured Discord logger instance with INFO level
                       and rotating file handler applied.
    """
    logger: logging.Logger = logging.getLogger("discord")
    logger.setLevel(logging.INFO)

    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    handler: RotatingFileHandler = handlers.RotatingFileHandler(
        filename=log_dir / "discord.log",
        encoding="utf-8",
        maxBytes=500 * 1024 * 1024,  # 500 MB,
        backupCount=3,
    )

    dt_fmt: str = "%Y-%m-%d %H:%M:%S"
    formatter: Formatter = logging.Formatter(
        "[{asctime}] [{levelname:<8}] {name}: {message}", dt_fmt, style="{"
    )

    handler.setFormatter(formatter)
    logger.addHandler(handler)
    return logger
