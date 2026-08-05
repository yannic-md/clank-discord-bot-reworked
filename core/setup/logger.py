import logging
from io import TextIOWrapper
from logging import FileHandler, Filter, Formatter, LogRecord
from pathlib import Path

LOG_DIR: Path = Path("logs")
DT_FMT: str = "%Y-%m-%d %H:%M:%S"
LOG_FORMAT: str = "[{asctime}] [{levelname:<8}] {name}: {message}"
MAX_LOG_BYTES: int = 500 * 1024 * 1024  # 500 MB


class _ExceptionFilter(Filter):
    """Splits log records by whether they carry exception info."""

    def __init__(self, *, keep_exceptions: bool) -> None:
        super().__init__()
        self._keep_exceptions: bool = keep_exceptions

    def filter(self, record: LogRecord) -> bool:
        has_exception: bool = record.exc_info is not None
        return has_exception == self._keep_exceptions


class TrimmingFileHandler(FileHandler):
    """A file handler that caps a log file at `max_bytes` by dropping its oldest lines."""

    def __init__(self, filename: Path, *, max_bytes: int, encoding: str | None = None) -> None:
        super().__init__(filename, mode="a", encoding=encoding)
        self.max_bytes: int = max_bytes

    def emit(self, record: LogRecord) -> None:
        try:
            if self.stream is None:
                self.stream: TextIOWrapper | None = self._open()
            if self._current_size() >= self.max_bytes:
                self._trim()
            super().emit(record)
        except Exception:
            self.handleError(record)

    def _current_size(self) -> int:
        assert self.stream is not None
        self.stream.seek(0, 2)
        return self.stream.tell()

    def _trim(self) -> None:
        """Drop the oldest lines, keeping roughly the newest half of `max_bytes`."""
        target_size: int = self.max_bytes // 2

        if self.stream is not None:
            self.stream.close()
            self.stream = None

        with open(self.baseFilename, "rb") as file:
            file.seek(0, 2)
            size: int = file.tell()
            if size > target_size:
                file.seek(size - target_size)
                file.readline()  # discard the partial line we just cut into
                remainder: bytes = file.read()
            else:
                remainder = b""

        with open(self.baseFilename, "wb") as file:
            file.write(remainder)

        self.stream = self._open()


def _make_handler(filename: str, *, max_bytes: int = MAX_LOG_BYTES) -> TrimmingFileHandler:
    handler: TrimmingFileHandler = TrimmingFileHandler(LOG_DIR / filename, max_bytes=max_bytes, encoding="utf-8")
    handler.setFormatter(Formatter(LOG_FORMAT, DT_FMT, style="{"))
    return handler


def setup_logging() -> logging.Logger:
    """
    Configure and initialize the Discord logger with size-capped log files.

    Returns:
        logging.Logger: The configured Discord logger instance with INFO level
                       and both handlers applied.
    """
    logger: logging.Logger = logging.getLogger("discord")
    logger.setLevel(logging.INFO)

    LOG_DIR.mkdir(exist_ok=True)

    discord_handler = _make_handler("discord.log")
    discord_handler.addFilter(_ExceptionFilter(keep_exceptions=False))
    logger.addHandler(discord_handler)

    error_handler = _make_handler("errors.log")
    error_handler.addFilter(_ExceptionFilter(keep_exceptions=True))
    logger.addHandler(error_handler)

    return logger


def setup_db_logging() -> logging.Logger:
    """
    Configure a dedicated, size-capped logger for SQLAlchemy's executed queries.

    Returns:
        logging.Logger: The configured "sqlalchemy.engine" logger instance.
    """
    logger: logging.Logger = logging.getLogger("sqlalchemy.engine")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    LOG_DIR.mkdir(exist_ok=True)

    handler = _make_handler("db_queries.log")
    logger.addHandler(handler)

    return logger
