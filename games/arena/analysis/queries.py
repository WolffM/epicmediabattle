"""
SQL queries for Arena battle and deletion statistics.
"""

import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List

# Add parent paths for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from games.arena.db_utils import get_db_connection
from games.arena.image_index import get_index


def get_volume_counts(group_by: str = 'gen') -> Dict:
    """
    Get volume counts (existing images on disk) grouped by a key.

    Args:
        group_by: 'gen', 'character', 'source', or 'variant'

    Returns:
        Dict mapping key -> count of images
    """
    index = get_index()
    counts: Dict[Any, int] = defaultdict(int)

    for img in index.images:
        if group_by == 'gen':
            counts[img.group_name] += 1
        elif group_by == 'character':
            # Key is (name, group_name) tuple
            counts[(img.name, img.group_name)] += 1
        elif group_by == 'source':
            counts[img.source] += 1
        elif group_by == 'variant' and img.variant:
            counts[img.variant] += 1

    return dict(counts)


# =============================================================================
# TOP WINNERS - Best win rates at each scope level
# =============================================================================

def top_winners_by_gen(limit: int = 10) -> List[Dict]:
    """Best generations by win rate."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                group_name as gen,
                SUM(CASE WHEN result='win' THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN result='loss' THEN 1 ELSE 0 END) as losses,
                COUNT(*) as total,
                ROUND(100.0 * SUM(CASE WHEN result='win' THEN 1 ELSE 0 END) / COUNT(*), 1) as win_pct
            FROM battles
            GROUP BY group_name
            HAVING total >= 10
            ORDER BY win_pct DESC
            LIMIT ?
        """, (limit,))
        return [dict(row) for row in cursor.fetchall()]


def top_winners_by_character(limit: int = 20) -> List[Dict]:
    """Best characters by win rate (minimum 5 battles)."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                name,
                group_name as gen,
                SUM(CASE WHEN result='win' THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN result='loss' THEN 1 ELSE 0 END) as losses,
                COUNT(*) as total,
                ROUND(100.0 * SUM(CASE WHEN result='win' THEN 1 ELSE 0 END) / COUNT(*), 1) as win_pct
            FROM battles
            GROUP BY name, group_name
            HAVING total >= 5
            ORDER BY win_pct DESC, total DESC
            LIMIT ?
        """, (limit,))
        return [dict(row) for row in cursor.fetchall()]


def top_winners_by_source(limit: int = 10) -> List[Dict]:
    """Best sources by win rate."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                source,
                SUM(CASE WHEN result='win' THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN result='loss' THEN 1 ELSE 0 END) as losses,
                COUNT(*) as total,
                ROUND(100.0 * SUM(CASE WHEN result='win' THEN 1 ELSE 0 END) / COUNT(*), 1) as win_pct
            FROM battles
            GROUP BY source
            HAVING total >= 5
            ORDER BY win_pct DESC
            LIMIT ?
        """, (limit,))
        return [dict(row) for row in cursor.fetchall()]


def top_winners_by_variant(limit: int = 10) -> List[Dict]:
    """Best variants by win rate."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                variant,
                SUM(CASE WHEN result='win' THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN result='loss' THEN 1 ELSE 0 END) as losses,
                COUNT(*) as total,
                ROUND(100.0 * SUM(CASE WHEN result='win' THEN 1 ELSE 0 END) / COUNT(*), 1) as win_pct
            FROM battles
            WHERE variant IS NOT NULL
            GROUP BY variant
            HAVING total >= 5
            ORDER BY win_pct DESC
            LIMIT ?
        """, (limit,))
        return [dict(row) for row in cursor.fetchall()]


# =============================================================================
# TOP VOLUME - Most battles at each scope level
# =============================================================================

def top_volume_by_gen(limit: int = 10) -> List[Dict]:
    """Generations with most battles."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                group_name as gen,
                COUNT(*) / 2 as battles,
                COUNT(DISTINCT name) as characters
            FROM battles
            GROUP BY group_name
            ORDER BY battles DESC
            LIMIT ?
        """, (limit,))
        return [dict(row) for row in cursor.fetchall()]


def top_volume_by_character(limit: int = 20) -> List[Dict]:
    """Characters with most battles."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                name,
                group_name as gen,
                COUNT(*) as appearances,
                SUM(CASE WHEN result='win' THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN result='loss' THEN 1 ELSE 0 END) as losses
            FROM battles
            GROUP BY name, group_name
            ORDER BY appearances DESC
            LIMIT ?
        """, (limit,))
        return [dict(row) for row in cursor.fetchall()]


# =============================================================================
# TOP DELETED - Most deletions at each scope level
# =============================================================================

def top_deleted_by_gen(limit: int = 10) -> List[Dict]:
    """Generations with most deletions, including volume (existing images) and deletion rate."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT group_name as gen, COUNT(*) as deletions
            FROM deletions
            GROUP BY group_name
            ORDER BY deletions DESC
            LIMIT ?
        """, (limit,))
        rows = cursor.fetchall()

    # Get volume from image index (existing files on disk)
    volume_counts = get_volume_counts('gen')

    # Combine results
    results = []
    for row in rows:
        gen = row['gen']
        deletions = row['deletions']
        volume = volume_counts.get(gen, 0)
        total = deletions + volume
        del_pct = round(100.0 * deletions / total, 1) if total > 0 else 0
        results.append({
            'gen': gen,
            'deletions': deletions,
            'volume': volume,
            'del_pct': del_pct
        })

    return results


def top_deleted_by_character(limit: int = 20) -> List[Dict]:
    """Characters with most deletions, including volume (existing images) and deletion rate."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT name, group_name as gen, COUNT(*) as deletions
            FROM deletions
            GROUP BY name, group_name
            ORDER BY deletions DESC
            LIMIT ?
        """, (limit,))
        rows = cursor.fetchall()

    # Get volume from image index (existing files on disk)
    volume_counts = get_volume_counts('character')

    # Combine results
    results = []
    for row in rows:
        name = row['name']
        gen = row['gen']
        deletions = row['deletions']
        volume = volume_counts.get((name, gen), 0)
        total = deletions + volume
        del_pct = round(100.0 * deletions / total, 1) if total > 0 else 0
        results.append({
            'name': name,
            'gen': gen,
            'deletions': deletions,
            'volume': volume,
            'del_pct': del_pct
        })

    return results


def top_deleted_by_source(limit: int = 10) -> List[Dict]:
    """Sources with most deletions, including volume (existing images) and deletion rate."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT source, COUNT(*) as deletions
            FROM deletions
            GROUP BY source
            ORDER BY deletions DESC
            LIMIT ?
        """, (limit,))
        rows = cursor.fetchall()

    # Get volume from image index (existing files on disk)
    volume_counts = get_volume_counts('source')

    # Combine results
    results = []
    for row in rows:
        source = row['source']
        deletions = row['deletions']
        volume = volume_counts.get(source, 0)
        total = deletions + volume
        del_pct = round(100.0 * deletions / total, 1) if total > 0 else 0
        results.append({
            'source': source,
            'deletions': deletions,
            'volume': volume,
            'del_pct': del_pct
        })

    return results


def top_deleted_by_variant(limit: int = 10) -> List[Dict]:
    """Variants with most deletions, including volume (existing images) and deletion rate."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT variant, COUNT(*) as deletions
            FROM deletions
            WHERE variant IS NOT NULL
            GROUP BY variant
            ORDER BY deletions DESC
            LIMIT ?
        """, (limit,))
        rows = cursor.fetchall()

    # Get volume from image index (existing files on disk)
    volume_counts = get_volume_counts('variant')

    # Combine results
    results = []
    for row in rows:
        variant = row['variant']
        deletions = row['deletions']
        volume = volume_counts.get(variant, 0)
        total = deletions + volume
        del_pct = round(100.0 * deletions / total, 1) if total > 0 else 0
        results.append({
            'variant': variant,
            'deletions': deletions,
            'volume': volume,
            'del_pct': del_pct
        })

    return results
