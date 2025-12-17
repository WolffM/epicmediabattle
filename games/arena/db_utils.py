"""
SQL query helpers and fragments for the Arena database.

This module provides reusable SQL patterns to ensure consistency
and reduce duplication across the codebase.
"""

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Dict

# ============================================================
# DATABASE CONNECTION MANAGEMENT
# ============================================================

def _get_db_path() -> Path:
    """Get the database path (same logic as database.py)."""
    return Path(__file__).parent / "arena.db"


@contextmanager
def get_db_connection():
    """
    Context manager for database connections.

    Ensures connections are properly closed even if an exception occurs.

    Usage:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT ...")
            # Multiple operations on same connection
    """
    conn = sqlite3.connect(str(_get_db_path()))
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


# ============================================================
# SQL FRAGMENTS FOR BATTLES TABLE
# ============================================================

def wins_losses_sql() -> str:
    """
    SQL fragment for calculating wins and losses from result column.

    Returns columns: wins, losses
    """
    return """
        SUM(CASE WHEN result='win' THEN 1 ELSE 0 END) as wins,
        SUM(CASE WHEN result='loss' THEN 1 ELSE 0 END) as losses
    """


def wins_losses_total_sql() -> str:
    """
    SQL fragment for wins, losses, and total count.

    Returns columns: wins, losses, total
    """
    return """
        SUM(CASE WHEN result='win' THEN 1 ELSE 0 END) as wins,
        SUM(CASE WHEN result='loss' THEN 1 ELSE 0 END) as losses,
        COUNT(*) as total
    """


def win_pct_sql() -> str:
    """
    SQL fragment for calculating win percentage.

    Returns column: win_pct (rounded to 1 decimal)
    """
    return "ROUND(100.0 * SUM(CASE WHEN result='win' THEN 1 ELSE 0 END) / COUNT(*), 1) as win_pct"


# ============================================================
# STATS CALCULATION HELPERS
# ============================================================

def safe_percentage(numerator: int, denominator: int, decimals: int = 1) -> float:
    """
    Calculate percentage safely, returning 0 if denominator is 0.

    Args:
        numerator: Top part of fraction
        denominator: Bottom part of fraction
        decimals: Number of decimal places

    Returns:
        Percentage value or 0 if division not possible
    """
    if denominator <= 0:
        return 0.0
    return round(100.0 * numerator / denominator, decimals)


def calculate_stats_dict(wins: int, losses: int, total: int = None) -> Dict:
    """
    Build a stats dictionary from win/loss counts.

    Args:
        wins: Number of wins
        losses: Number of losses
        total: Total battles (calculated from wins+losses if not provided)

    Returns:
        Dict with wins, losses, total_battles, win_pct
    """
    if total is None:
        total = (wins or 0) + (losses or 0)

    return {
        'wins': wins or 0,
        'losses': losses or 0,
        'total_battles': total,
        'win_pct': safe_percentage(wins or 0, total)
    }


def calculate_deletion_stats(deletions: int, volume: int) -> Dict:
    """
    Build deletion stats including deletion rate.

    Args:
        deletions: Number of deleted images
        volume: Number of existing images

    Returns:
        Dict with deletions, volume, total, del_pct
    """
    total = deletions + volume
    return {
        'deletions': deletions,
        'volume': volume,
        'total': total,
        'del_pct': safe_percentage(deletions, total)
    }


# ============================================================
# SCOPE LEVEL CONSTANTS
# ============================================================

# Valid scope levels in hierarchical order
SCOPE_LEVELS = ['universe', 'ip', 'group', 'character', 'source', 'variant']


def validate_scope_level(level: str) -> bool:
    """Check if a scope level is valid."""
    return level in SCOPE_LEVELS


def get_scope_level_index(level: str) -> int:
    """Get the index of a scope level (for hierarchy comparisons)."""
    return SCOPE_LEVELS.index(level) if level in SCOPE_LEVELS else -1
