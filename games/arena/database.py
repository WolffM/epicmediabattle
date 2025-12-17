"""
SQLite database for arena battle logging.

Core module with schema, connection management, and battle logging.
Additional functions are in database_stats.py and database_merge.py.
"""

import os
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

# Database path - can be overridden for testing
_db_path: Optional[Path] = None


def _get_db_path() -> Path:
    """Get the current database path."""
    global _db_path
    if _db_path is None:
        # Check environment variable first, then use default
        env_path = os.environ.get("ARENA_DB_PATH")
        _db_path = Path(env_path) if env_path else Path(__file__).parent / "arena.db"
    return _db_path


def set_db_path(path: Optional[Path]) -> None:
    """Set the database path (for testing)."""
    global _db_path
    _db_path = Path(path) if path else None


def get_connection() -> sqlite3.Connection:
    """Get a database connection with row factory."""
    conn = sqlite3.connect(str(_get_db_path()))
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Initialize the database schema."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS battles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            battle_id TEXT NOT NULL,
            timestamp TEXT NOT NULL,

            -- Scope constraints used for this battle
            scope_level TEXT NOT NULL,
            scope_universe TEXT,
            scope_ip TEXT,
            scope_group TEXT,
            scope_character TEXT,
            scope_source TEXT,
            scope_variant TEXT,
            match_source INTEGER DEFAULT 0,
            match_variant INTEGER DEFAULT 0,

            -- Image metadata
            path TEXT NOT NULL,
            name TEXT NOT NULL,
            group_name TEXT NOT NULL,
            source TEXT NOT NULL,
            variant TEXT,
            universe TEXT,

            -- Result: 'win' or 'loss'
            result TEXT NOT NULL
        )
    """)

    # Create indexes for common queries
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_battle_id ON battles(battle_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_path ON battles(path)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_name ON battles(name)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_result ON battles(result)")

    # Deletions table - tracks deleted images for analysis
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS deletions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            path TEXT NOT NULL,
            name TEXT NOT NULL,
            group_name TEXT NOT NULL,
            source TEXT NOT NULL,
            variant TEXT,
            ip TEXT,
            universe TEXT
        )
    """)

    # Create indexes for deletion queries
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_del_source ON deletions(source)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_del_variant ON deletions(variant)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_del_name ON deletions(name)")

    # Image stats table - aggregated per-image battle stats for fast matchmaker lookups
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS image_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            path TEXT NOT NULL UNIQUE,
            total_battles INTEGER DEFAULT 0,
            ip_wins INTEGER DEFAULT 0,
            ip_losses INTEGER DEFAULT 0,
            group_wins INTEGER DEFAULT 0,
            group_losses INTEGER DEFAULT 0,
            character_wins INTEGER DEFAULT 0,
            character_losses INTEGER DEFAULT 0,
            source_wins INTEGER DEFAULT 0,
            source_losses INTEGER DEFAULT 0,
            variant_wins INTEGER DEFAULT 0,
            variant_losses INTEGER DEFAULT 0
        )
    """)

    # Create index for fast path lookups
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_stats_path ON image_stats(path)")

    conn.commit()
    conn.close()


def update_image_stats(cursor, path: str, scope_level: str, is_win: bool, increment: int = 1):
    """
    Update aggregated image stats for a battle result.

    Args:
        cursor: Database cursor (must be within a transaction)
        path: Image file path
        scope_level: The scope level of the battle ('ip', 'group', 'character', 'source', 'variant')
        is_win: True if this image won, False if it lost
        increment: 1 to add, -1 to subtract (for undo)
    """
    # Ensure the image has a stats row
    cursor.execute("""
        INSERT OR IGNORE INTO image_stats (path, total_battles)
        VALUES (?, 0)
    """, (path,))

    # Determine which column to update based on scope level
    column = f"{scope_level}_wins" if is_win else f"{scope_level}_losses"

    # Update the appropriate column and total_battles
    cursor.execute(f"""
        UPDATE image_stats
        SET {column} = {column} + ?,
            total_battles = total_battles + ?
        WHERE path = ?
    """, (increment, increment, path))


def log_battle(
    scope: Dict,
    winner: Dict,
    loser: Dict
) -> str:
    """
    Log a battle result.

    Args:
        scope: Dict with scope_level, scope_universe, scope_ip, scope_group, scope_character,
               scope_source, scope_variant, match_source, match_variant
        winner: Dict with path, name, group_name, source, variant, universe
        loser: Dict with path, name, group_name, source, variant, universe

    Returns:
        battle_id for this battle
    """
    conn = get_connection()
    cursor = conn.cursor()

    battle_id = str(uuid.uuid4())
    timestamp = datetime.now().isoformat()

    # Insert winner row
    cursor.execute("""
        INSERT INTO battles (
            battle_id, timestamp,
            scope_level, scope_universe, scope_ip, scope_group, scope_character,
            scope_source, scope_variant, match_source, match_variant,
            path, name, group_name, source, variant, universe, result
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        battle_id, timestamp,
        scope.get('scope_level'), scope.get('scope_universe'), scope.get('scope_ip'), scope.get('scope_group'),
        scope.get('scope_character'), scope.get('scope_source'), scope.get('scope_variant'),
        1 if scope.get('match_source') else 0,
        1 if scope.get('match_variant') else 0,
        winner['path'], winner['name'], winner['group_name'],
        winner['source'], winner.get('variant'), winner.get('universe'),
        'win'
    ))

    # Insert loser row
    cursor.execute("""
        INSERT INTO battles (
            battle_id, timestamp,
            scope_level, scope_universe, scope_ip, scope_group, scope_character,
            scope_source, scope_variant, match_source, match_variant,
            path, name, group_name, source, variant, universe, result
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        battle_id, timestamp,
        scope.get('scope_level'), scope.get('scope_universe'), scope.get('scope_ip'), scope.get('scope_group'),
        scope.get('scope_character'), scope.get('scope_source'), scope.get('scope_variant'),
        1 if scope.get('match_source') else 0,
        1 if scope.get('match_variant') else 0,
        loser['path'], loser['name'], loser['group_name'],
        loser['source'], loser.get('variant'), loser.get('universe'),
        'loss'
    ))

    # Update aggregated image stats
    scope_level = scope.get('scope_level', 'ip')
    update_image_stats(cursor, winner['path'], scope_level, is_win=True)
    update_image_stats(cursor, loser['path'], scope_level, is_win=False)

    conn.commit()
    conn.close()

    return battle_id


def undo_battle(battle_id: str) -> Optional[Dict]:
    """
    Undo a battle by deleting its records.

    Args:
        battle_id: The battle_id to undo

    Returns:
        Dict with winner and loser paths if successful, None if not found
    """
    conn = get_connection()
    cursor = conn.cursor()

    # First, get the battle data before deleting (include scope_level for stats update)
    cursor.execute("""
        SELECT path, name, group_name, source, variant, result, scope_level
        FROM battles
        WHERE battle_id = ?
    """, (battle_id,))

    rows = cursor.fetchall()

    if not rows:
        conn.close()
        return None

    # Extract winner and loser info
    winner_data = None
    loser_data = None
    scope_level = 'ip'  # Default
    for row in rows:
        data = dict(row)
        scope_level = data.get('scope_level', 'ip')
        if data['result'] == 'win':
            winner_data = data
        else:
            loser_data = data

    # Decrement aggregated image stats
    if winner_data:
        update_image_stats(cursor, winner_data['path'], scope_level, is_win=True, increment=-1)
    if loser_data:
        update_image_stats(cursor, loser_data['path'], scope_level, is_win=False, increment=-1)

    # Delete the battle records
    cursor.execute("DELETE FROM battles WHERE battle_id = ?", (battle_id,))
    conn.commit()
    conn.close()

    return {
        'winner': winner_data,
        'loser': loser_data
    }


def get_recent_battles(limit: int = 50) -> List[Dict]:
    """
    Get recent battle history.

    Args:
        limit: Max number of battles to return

    Returns:
        List of battle records (grouped by battle_id)
    """
    conn = get_connection()
    cursor = conn.cursor()

    # Get unique battle_ids ordered by timestamp
    cursor.execute("""
        SELECT DISTINCT battle_id, timestamp
        FROM battles
        ORDER BY timestamp DESC
        LIMIT ?
    """, (limit,))

    battle_ids = [row['battle_id'] for row in cursor.fetchall()]

    battles = []
    for bid in battle_ids:
        cursor.execute("""
            SELECT * FROM battles WHERE battle_id = ?
        """, (bid,))
        rows = cursor.fetchall()

        winner = None
        loser = None
        for row in rows:
            data = dict(row)
            if data['result'] == 'win':
                winner = data
            else:
                loser = data

        if winner and loser:
            battles.append({
                'battle_id': bid,
                'timestamp': winner['timestamp'],
                'scope_level': winner['scope_level'],
                'winner': winner,
                'loser': loser
            })

    conn.close()
    return battles


# Initialize database on import
init_db()

# Re-export functions from submodules for backward compatibility
# This allows existing code using `from games.arena.database import get_image_stats` to continue working
from games.arena.database_merge import (
    backfill_deletions,
    backfill_image_stats,
    merge_images,
)
from games.arena.database_stats import (
    get_all_image_battle_counts,
    get_all_image_stats,
    get_character_stats,
    get_deletion_details,
    get_deletion_stats,
    get_image_stats,
    get_leaderboard,
    log_deletion,
)
