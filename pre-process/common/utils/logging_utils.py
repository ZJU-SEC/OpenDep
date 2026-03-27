from __future__ import annotations

import logging
import os


_DEFAULT_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
_CONFIGURED_LOGGERS: set[str] = set()


def _resolve_level(default: str = "WARNING") -> int:
    configured = (os.getenv("PREPROCESS_LOG_LEVEL", default) or default).strip().upper()
    return getattr(logging, configured, logging.WARNING)


def get_logger(name: str, *, default_level: str = "WARNING") -> logging.Logger:
    logger = logging.getLogger(name)
    if name in _CONFIGURED_LOGGERS:
        return logger

    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(_DEFAULT_FORMAT, datefmt=_DATE_FORMAT))
    logger.addHandler(handler)
    logger.setLevel(_resolve_level(default_level))
    logger.propagate = False
    _CONFIGURED_LOGGERS.add(name)
    return logger
