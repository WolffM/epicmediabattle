"""
Centralized logging configuration for the Arena application.

Provides:
- arena.log: Raw detailed log with rotation (DEBUG level)
- arena_summary.log: High-level actions only (INFO level)
"""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import ClassVar, List

LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

# Track if logging has been set up to avoid duplicate handlers
_logging_initialized = False


class SummaryFilter(logging.Filter):
    """Filter to only allow high-level action messages through to summary log."""

    # Keywords that indicate high-level actions worth logging to summary
    SUMMARY_KEYWORDS: ClassVar[List[str]] = [
        'Server',       # Server start/stop
        'MATCHUP',      # Matchup selections
        'FINAL MATCHUP',
        'Battle',       # Battle outcomes
        'battle_id',    # Battle logged
        'delete',       # Deletions
        'Delete',
        'merge',        # Merges
        'Merge',
        'ERROR',        # Errors
        'Error',
        'error',
        'WARNING',      # Warnings
        'Warning',
    ]

    def filter(self, record):
        msg = record.getMessage()
        return any(kw in msg for kw in self.SUMMARY_KEYWORDS)


def setup_logging():
    """
    Configure all arena loggers with consistent handlers.

    Call this once at application startup (e.g., in app.py).
    Safe to call multiple times - will only initialize once.
    """
    global _logging_initialized

    if _logging_initialized:
        return

    # Raw detailed log with rotation (10MB max, keep 3 backups)
    raw_handler = RotatingFileHandler(
        LOG_DIR / "arena.log",
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=3,
        encoding='utf-8'
    )
    raw_handler.setLevel(logging.DEBUG)
    raw_handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    ))

    # Summary log - high-level actions only
    summary_handler = RotatingFileHandler(
        LOG_DIR / "arena_summary.log",
        maxBytes=5 * 1024 * 1024,  # 5MB
        backupCount=2,
        encoding='utf-8'
    )
    summary_handler.setLevel(logging.INFO)
    summary_handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(message)s'
    ))
    summary_handler.addFilter(SummaryFilter())

    # Console handler (INFO only, less noise)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter(
        '%(name)s - %(levelname)s - %(message)s'
    ))

    # Configure root arena logger
    arena_logger = logging.getLogger('arena')
    arena_logger.setLevel(logging.DEBUG)
    arena_logger.addHandler(raw_handler)
    arena_logger.addHandler(summary_handler)
    arena_logger.addHandler(console_handler)

    # Prevent propagation to root logger (avoid duplicate output)
    arena_logger.propagate = False

    # Suppress asyncio DEBUG spam
    logging.getLogger('asyncio').setLevel(logging.WARNING)

    _logging_initialized = True

    # Log that we're initialized
    arena_logger.info(f"Server logging initialized - logs at {LOG_DIR}")


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger for an arena submodule.

    Usage:
        from games.arena.logging_config import get_logger
        logger = get_logger(__name__)  # e.g., 'arena.matcher'

    Args:
        name: Module name, typically __name__

    Returns:
        Logger configured as child of arena logger
    """
    # Ensure logging is set up
    setup_logging()

    # Convert module path to arena namespace
    # e.g., 'games.arena.matcher' -> 'arena.matcher'
    if name.startswith('games.arena.'):
        name = 'arena.' + name[len('games.arena.'):]
    elif not name.startswith('arena'):
        name = 'arena.' + name

    return logging.getLogger(name)
