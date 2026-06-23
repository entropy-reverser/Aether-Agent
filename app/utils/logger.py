"""app.utils.logger — structured logging facade over loguru.

Provides one ``get_logger()`` entry point. All modules use it instead of
``print`` or raw ``loguru.logger`` so we have a single place to shape output
format, levels, and sinks.

Design notes
------------
- In Stage 1 the log level defaults to WARNING to keep test output quiet.
  Callers can override per-call or via env (LOGURU_LEVEL) when debugging.
- No API keys / full user messages are ever logged (per §12.2); callers must
  truncate before passing sensitive payloads here.
"""

from __future__ import annotations

import os
import sys

from loguru import logger as _loguru_logger

# One-time configuration. Idempotent: removing the default handler first
# prevents duplicate lines if this module is re-imported.
_loguru_logger.remove()
_loguru_logger.add(
    sys.stderr,
    level=os.environ.get("LOGURU_LEVEL", "WARNING"),
    format=(
        "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> "
        "<level>{level: <8}</level> "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
        "<level>{message}</level>"
    ),
    backtrace=False,
    diagnose=False,
)


def get_logger():  # type: ignore[no-untyped-def]
    """Return the configured loguru logger.

    Returns:
        The shared logger instance. Call ``logger.info(...)`` etc.
    """
    return _loguru_logger


logger = get_logger()  # type: ignore[no-untyped-call]
