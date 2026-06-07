import logging
import sys

from app.core.config import config


class CompactFormatter(logging.Formatter):
    LEVEL_NAMES = {
        "DEBUG": "DBG",
        "INFO": "INF",
        "WARNING": "WRN",
        "ERROR": "ERR",
        "CRITICAL": "CRT",
    }

    def format(self, record: logging.LogRecord) -> str:
        record.level_short = self.LEVEL_NAMES.get(record.levelname, record.levelname[:3])
        return super().format(record)


def configure_logging() -> None:
    level_name = config.LOG_LEVEL.upper()
    level = getattr(logging, level_name, logging.INFO)

    formatter = CompactFormatter(
        fmt="%(asctime)s %(level_short)s %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(level)

    for noisy_logger in ("aiohttp.access", "httpx", "telegram", "httpcore"):
        logging.getLogger(noisy_logger).setLevel(logging.WARNING)
