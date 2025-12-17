"""
SQLite database functions for merge and backfill operations.

This module handles data migration and consolidation operations.
"""

import json
import os
from datetime import datetime
from typing import Dict, List

from games.arena.database import get_connection


def backfill_image_stats() -> int:
    """
    Backfill the image_stats table from existing battles.
    Clears and rebuilds the stats from scratch.

    Returns:
        Number of images with stats
    """
    conn = get_connection()
    cursor = conn.cursor()

    # Clear existing stats
    cursor.execute("DELETE FROM image_stats")

    # Get all battles grouped by path, scope_level, and result
    cursor.execute("""
        SELECT path, scope_level, result, COUNT(*) as count
        FROM battles
        GROUP BY path, scope_level, result
    """)

    rows = cursor.fetchall()

    # Build stats for each image
    stats = {}  # path -> {total_battles, ip_wins, ip_losses, ...}

    for row in rows:
        path = row['path']
        scope_level = row['scope_level'] or 'ip'
        result = row['result']
        count = row['count']

        if path not in stats:
            stats[path] = {
                'total_battles': 0,
                'ip_wins': 0, 'ip_losses': 0,
                'group_wins': 0, 'group_losses': 0,
                'character_wins': 0, 'character_losses': 0,
                'source_wins': 0, 'source_losses': 0,
                'variant_wins': 0, 'variant_losses': 0
            }

        stats[path]['total_battles'] += count

        if result == 'win':
            stats[path][f'{scope_level}_wins'] += count
        else:
            stats[path][f'{scope_level}_losses'] += count

    # Insert all stats
    for path, s in stats.items():
        cursor.execute("""
            INSERT INTO image_stats (
                path, total_battles,
                ip_wins, ip_losses,
                group_wins, group_losses,
                character_wins, character_losses,
                source_wins, source_losses,
                variant_wins, variant_losses
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            path, s['total_battles'],
            s['ip_wins'], s['ip_losses'],
            s['group_wins'], s['group_losses'],
            s['character_wins'], s['character_losses'],
            s['source_wins'], s['source_losses'],
            s['variant_wins'], s['variant_losses']
        ))

    conn.commit()
    conn.close()

    return len(stats)


def backfill_deletions(output_json_path: str, ip: str = "pokemon", universe: str = "nintendo") -> int:
    """
    Backfill the deletions table from output.json.
    Finds images logged in output.json that no longer exist on disk.
    Clears existing deletions and rebuilds from scratch.

    Args:
        output_json_path: Path to the output.json file
        ip: Intellectual property name
        universe: Universe name

    Returns:
        Number of deletions found
    """
    # Load output.json
    with open(output_json_path) as f:
        data = json.load(f)

    conn = get_connection()
    cursor = conn.cursor()

    # Clear existing deletions
    cursor.execute("DELETE FROM deletions")

    deletion_count = 0
    timestamp_prefix = "BACKFILL-"

    for entry in data.get('results', []):
        name = entry.get('name', '')
        # Support both old 'generation' and new 'group' format
        group_name = str(entry.get('group', entry.get('generation', '')))

        for img in entry.get('images', []):
            path = img.get('path', '')
            source = img.get('source', '')
            variant = img.get('variant')

            # Check if file exists on disk
            if path and not os.path.exists(path):
                # File was deleted - log it
                cursor.execute("""
                    INSERT INTO deletions (
                        timestamp, path, name, group_name, source, variant, ip, universe
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    f"{timestamp_prefix}{datetime.now().isoformat()}",
                    path,
                    name,
                    group_name,
                    source,
                    variant,
                    ip,
                    universe
                ))
                deletion_count += 1

    conn.commit()
    conn.close()

    return deletion_count


def merge_images(surviving_path: str, duplicate_paths: List[str]) -> Dict:
    """
    Merge battle records from duplicate images into one surviving image.

    All battle records from duplicates are updated to reference the surviving image.
    The image_stats table is rebuilt for the surviving image.
    Duplicate stats rows are deleted.

    Args:
        surviving_path: Path to the image that will remain
        duplicate_paths: List of paths to duplicate images to merge

    Returns:
        Dict with surviving_path and number of battles_merged
    """
    conn = get_connection()
    cursor = conn.cursor()

    battles_merged = 0

    for dup_path in duplicate_paths:
        if dup_path == surviving_path:
            continue  # Don't process the survivor as a duplicate

        # Count battles being merged
        cursor.execute("SELECT COUNT(*) as count FROM battles WHERE path = ? COLLATE NOCASE", (dup_path,))
        count = cursor.fetchone()['count']
        battles_merged += count

        # Update all battle records to point to surviving image
        # Note: We only update the path, not the metadata (name, source, etc.)
        # This preserves the original battle context
        cursor.execute("""
            UPDATE battles
            SET path = ?
            WHERE path = ? COLLATE NOCASE
        """, (surviving_path, dup_path))

        # Delete duplicate's stats row
        cursor.execute("DELETE FROM image_stats WHERE path = ? COLLATE NOCASE", (dup_path,))

    # Rebuild stats for the surviving image from its battles
    cursor.execute("DELETE FROM image_stats WHERE path = ? COLLATE NOCASE", (surviving_path,))

    cursor.execute("""
        SELECT scope_level, result, COUNT(*) as count
        FROM battles
        WHERE path = ? COLLATE NOCASE
        GROUP BY scope_level, result
    """, (surviving_path,))

    rows = cursor.fetchall()

    if rows:
        stats = {
            'total_battles': 0,
            'ip_wins': 0, 'ip_losses': 0,
            'group_wins': 0, 'group_losses': 0,
            'character_wins': 0, 'character_losses': 0,
            'source_wins': 0, 'source_losses': 0,
            'variant_wins': 0, 'variant_losses': 0
        }

        for row in rows:
            scope_level = row['scope_level'] or 'ip'
            result = row['result']
            count = row['count']

            stats['total_battles'] += count

            if result == 'win':
                stats[f'{scope_level}_wins'] += count
            else:
                stats[f'{scope_level}_losses'] += count

        cursor.execute("""
            INSERT INTO image_stats (
                path, total_battles,
                ip_wins, ip_losses,
                group_wins, group_losses,
                character_wins, character_losses,
                source_wins, source_losses,
                variant_wins, variant_losses
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            surviving_path, stats['total_battles'],
            stats['ip_wins'], stats['ip_losses'],
            stats['group_wins'], stats['group_losses'],
            stats['character_wins'], stats['character_losses'],
            stats['source_wins'], stats['source_losses'],
            stats['variant_wins'], stats['variant_losses']
        ))

    conn.commit()
    conn.close()

    return {
        'surviving_path': surviving_path,
        'battles_merged': battles_merged
    }
