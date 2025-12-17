"""
SQLite database functions for image stats and leaderboard queries.

This module handles all read operations for image statistics and deletion tracking.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from games.arena.database import get_connection


def get_image_stats(path: str) -> Dict:
    """
    Get win/loss stats for a specific image.

    Args:
        path: Image file path

    Returns:
        Dict with wins, losses, total_battles

    Note: Uses COLLATE NOCASE for Windows path case-insensitivity.
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            SUM(CASE WHEN result = 'win' THEN 1 ELSE 0 END) as wins,
            SUM(CASE WHEN result = 'loss' THEN 1 ELSE 0 END) as losses,
            COUNT(*) as total
        FROM battles
        WHERE path = ? COLLATE NOCASE
    """, (path,))

    row = cursor.fetchone()
    conn.close()

    if row and row['total']:
        return {
            'wins': row['wins'] or 0,
            'losses': row['losses'] or 0,
            'total_battles': row['total']
        }
    return {'wins': 0, 'losses': 0, 'total_battles': 0}


def get_all_image_battle_counts(paths: List[str] = None) -> Dict[str, int]:
    """
    Get total_battles count for multiple images efficiently.
    Used by matchmaker to prioritize images with fewer battles.

    Args:
        paths: Optional list of paths to filter. If None, returns all.

    Returns:
        Dict mapping path -> total_battles
    """
    conn = get_connection()
    cursor = conn.cursor()

    if paths:
        placeholders = ','.join(['?' for _ in paths])
        cursor.execute(f"""
            SELECT path, total_battles
            FROM image_stats
            WHERE path COLLATE NOCASE IN ({placeholders})
        """, paths)
    else:
        cursor.execute("SELECT path, total_battles FROM image_stats")

    rows = cursor.fetchall()
    conn.close()

    return {row['path']: row['total_battles'] for row in rows}


def get_all_image_stats(paths: List[str]) -> Dict[str, Dict]:
    """
    Get full stats (wins, losses, total_battles) for multiple images efficiently.
    Used by matchmaker for rating-based matching.

    Args:
        paths: List of paths to get stats for.

    Returns:
        Dict mapping path -> {wins, losses, total_battles}
    """
    conn = get_connection()
    cursor = conn.cursor()

    placeholders = ','.join(['?' for _ in paths])
    cursor.execute(f"""
        SELECT path,
               ip_wins + group_wins + character_wins + source_wins + variant_wins as wins,
               ip_losses + group_losses + character_losses + source_losses + variant_losses as losses,
               total_battles
        FROM image_stats
        WHERE path COLLATE NOCASE IN ({placeholders})
    """, paths)

    rows = cursor.fetchall()
    conn.close()

    result = {}
    for row in rows:
        result[row['path']] = {
            'wins': row['wins'],
            'losses': row['losses'],
            'total_battles': row['total_battles']
        }

    # Ensure all paths have stats (default 0 for new images)
    for path in paths:
        if path not in result:
            result[path] = {'wins': 0, 'losses': 0, 'total_battles': 0}

    return result


def get_character_stats(name: str, group: Optional[str] = None) -> Dict:
    """
    Get aggregated stats for a character (all their images combined).

    Args:
        name: Character name
        group: Optional group/gen filter

    Returns:
        Dict with total wins, losses, battles, win_rate, and image count
    """
    conn = get_connection()
    cursor = conn.cursor()

    query = """
        SELECT
            COUNT(DISTINCT path) as image_count,
            SUM(CASE WHEN result = 'win' THEN 1 ELSE 0 END) as wins,
            SUM(CASE WHEN result = 'loss' THEN 1 ELSE 0 END) as losses,
            COUNT(*) as total_battles
        FROM battles
        WHERE name = ?
    """
    params = [name]

    if group:
        query += " AND group_name = ?"
        params.append(group)

    cursor.execute(query, params)
    row = cursor.fetchone()
    conn.close()

    if row and row['total_battles'] > 0:
        return {
            'name': name,
            'group': group,
            'image_count': row['image_count'],
            'wins': row['wins'],
            'losses': row['losses'],
            'total_battles': row['total_battles'],
            'win_rate': row['wins'] / row['total_battles'] if row['total_battles'] > 0 else 0
        }

    return {
        'name': name,
        'group': group,
        'image_count': 0,
        'wins': 0,
        'losses': 0,
        'total_battles': 0,
        'win_rate': 0
    }


def get_leaderboard(
    scope_level: str = None,
    scope_universe: str = None,
    scope_ip: str = None,
    scope_group: str = None,
    limit: int = 20
) -> List[Dict]:
    """
    Get leaderboard of images by win rate.

    Args:
        scope_level: Filter by scope level
        scope_universe: Filter by universe
        scope_ip: Filter by IP
        scope_group: Filter by group
        limit: Max entries to return

    Returns:
        List of image stats sorted by win rate
    """
    conn = get_connection()
    cursor = conn.cursor()

    query = """
        SELECT
            path, name, group_name, source, variant, universe,
            SUM(CASE WHEN result = 'win' THEN 1 ELSE 0 END) as wins,
            SUM(CASE WHEN result = 'loss' THEN 1 ELSE 0 END) as losses,
            COUNT(*) as total,
            CAST(SUM(CASE WHEN result = 'win' THEN 1 ELSE 0 END) AS FLOAT) / COUNT(*) as win_rate
        FROM battles
        WHERE 1=1
    """
    params: List[Any] = []

    if scope_universe:
        query += " AND scope_universe = ?"
        params.append(scope_universe)
    if scope_ip:
        query += " AND scope_ip = ?"
        params.append(scope_ip)
    if scope_group:
        query += " AND scope_group = ?"
        params.append(scope_group)

    query += """
        GROUP BY path
        HAVING total >= 3
        ORDER BY win_rate DESC, total DESC
        LIMIT ?
    """
    params.append(limit)

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    return [dict(row) for row in rows]


def log_deletion(image: Dict) -> Optional[int]:
    """
    Log a deleted image for analysis.

    Args:
        image: Dict with path, name, group_name, source, variant, ip, universe

    Returns:
        Deletion record id, or None if insert fails
    """
    conn = get_connection()
    cursor = conn.cursor()

    timestamp = datetime.now().isoformat()

    cursor.execute("""
        INSERT INTO deletions (
            timestamp, path, name, group_name, source, variant, ip, universe
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        timestamp,
        image['path'],
        image['name'],
        image['group_name'],
        image['source'],
        image.get('variant'),
        image.get('ip'),
        image.get('universe')
    ))

    deletion_id = cursor.lastrowid
    conn.commit()
    conn.close()

    return deletion_id


def get_deletion_stats(group_by: str = 'variant') -> List[Dict]:
    """
    Get deletion statistics grouped by source, variant, character, or universe.

    Args:
        group_by: 'variant', 'source', 'name' (character), 'ip', or 'universe'

    Returns:
        List of dicts with group key and count, sorted by count desc
    """
    conn = get_connection()
    cursor = conn.cursor()

    valid_columns = ['variant', 'source', 'name', 'group_name', 'ip', 'universe']
    if group_by not in valid_columns:
        group_by = 'variant'

    cursor.execute(f"""
        SELECT {group_by}, COUNT(*) as count
        FROM deletions
        WHERE {group_by} IS NOT NULL
        GROUP BY {group_by}
        ORDER BY count DESC
    """)

    rows = cursor.fetchall()
    conn.close()

    return [{'key': row[group_by], 'count': row['count']} for row in rows]


def get_deletion_details(limit: int = 100) -> List[Dict]:
    """
    Get detailed deletion records.

    Args:
        limit: Max records to return

    Returns:
        List of deletion records
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT * FROM deletions
        ORDER BY timestamp DESC
        LIMIT ?
    """, (limit,))

    rows = cursor.fetchall()
    conn.close()

    return [dict(row) for row in rows]
