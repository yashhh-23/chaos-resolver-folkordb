from typing import Optional
import logging
import sys
from src.config import settings


def setup_logger(name: str = "orgbridge", level: Optional[str] = None) -> logging.Logger:
    """Configures and returns a consistent logger respecting configured LOG_LEVEL."""
    log_level_str = level or getattr(settings, "log_level", "INFO") or "INFO"
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(
            fmt="[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    logger.setLevel(getattr(logging, log_level_str.upper(), logging.INFO))
    return logger


logger = setup_logger()
