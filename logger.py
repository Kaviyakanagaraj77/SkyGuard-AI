"""
SkyGuard AI v2 - Structured Logging & Observability (Phase 5)
--------------------------------------------------------------
Provides structured logging with configurable log levels, audit trail support,
and automatic secret masking (passwords, JWT tokens, hashes).
"""

import logging
import re
import sys
from config import settings


class SecretMaskingFormatter(logging.Formatter):
    """Filters out sensitive authentication parameters, JWT secrets, and bearer tokens from logs."""

    SECRET_PATTERNS = [
        (re.compile(r'(Bearer\s+)[A-Za-z0-9\-_=\.]+', re.IGNORECASE), r'\1[MASKED_TOKEN]'),
        (re.compile(r'("password"\s*:\s*")[^"]+(")', re.IGNORECASE), r'\1[MASKED_PASSWORD]\2'),
        (re.compile(r'("password_hash"\s*:\s*")[^"]+(")', re.IGNORECASE), r'\1[MASKED_HASH]\2'),
        (re.compile(r'(secret=)[^\s&]+', re.IGNORECASE), r'\1[MASKED_SECRET]'),
    ]

    def format(self, record: logging.LogRecord) -> str:
        msg = super().format(record)
        for pattern, replacement in self.SECRET_PATTERNS:
            msg = pattern.sub(replacement, msg)
        return msg


def setup_logger(name: str = "skyguard") -> logging.Logger:
    logger = logging.getLogger(name)

    log_level = getattr(logging, settings.LOG_LEVEL, logging.INFO)
    logger.setLevel(log_level)

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(log_level)

        formatter = SecretMaskingFormatter(
            "[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger


logger = setup_logger()
