"""
Report runners and admin analysis functions for Arena.
"""

import datetime
import math
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Tuple

# Add parent paths for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from games.arena.analysis.formatters import print_table
from games.arena.analysis.queries import (
    get_volume_counts,
    top_deleted_by_character,
    top_deleted_by_gen,
    top_deleted_by_source,
    top_deleted_by_variant,
    top_volume_by_character,
    top_volume_by_gen,
    top_winners_by_character,
    top_winners_by_gen,
    top_winners_by_source,
    top_winners_by_variant,
)
from games.arena.db_utils import get_db_connection
from games.arena.image_index import get_index
from games.arena.path_utils import get_all_characters, group_by_character_variant

# =============================================================================
# Basic Report Runners
# =============================================================================

def run_winners_analysis():
    """Run all winner analyses."""
    print("\n" + "="*60)
    print(" TOP WINNERS BY WIN RATE")
    print("="*60)

    # By Gen
    data = top_winners_by_gen()
    print_table("Best Generations", data, [
        ("gen", "Gen", 8),
        ("wins", "Wins", 8),
        ("losses", "Losses", 8),
        ("total", "Total", 8),
        ("win_pct", "Win%", 10),
    ])

    # By Character
    data = top_winners_by_character(15)
    print_table("Best Characters (min 5 battles)", data, [
        ("name", "Character", 20),
        ("gen", "Gen", 8),
        ("wins", "W", 6),
        ("losses", "L", 6),
        ("win_pct", "Win%", 10),
    ])

    # By Source
    data = top_winners_by_source()
    print_table("Best Sources", data, [
        ("source", "Source", 20),
        ("wins", "Wins", 8),
        ("losses", "Losses", 8),
        ("win_pct", "Win%", 10),
    ])

    # By Variant
    data = top_winners_by_variant()
    print_table("Best Variants", data, [
        ("variant", "Variant", 20),
        ("wins", "Wins", 8),
        ("losses", "Losses", 8),
        ("win_pct", "Win%", 10),
    ])


def run_volume_analysis():
    """Run all volume analyses."""
    print("\n" + "="*60)
    print(" TOP VOLUME (MOST BATTLES)")
    print("="*60)

    # By Gen
    data = top_volume_by_gen()
    print_table("Generations by Battle Count", data, [
        ("gen", "Gen", 8),
        ("battles", "Battles", 10),
        ("characters", "Chars", 10),
    ])

    # By Character
    data = top_volume_by_character(15)
    print_table("Characters by Battle Count", data, [
        ("name", "Character", 20),
        ("gen", "Gen", 8),
        ("appearances", "Battles", 10),
        ("wins", "W", 6),
        ("losses", "L", 6),
    ])


def run_deletions_analysis():
    """Run all deletion analyses."""
    print("\n" + "="*60)
    print(" TOP DELETED")
    print("="*60)

    # By Gen
    data = top_deleted_by_gen()
    print_table("Deletions by Generation", data, [
        ("gen", "Gen", 8),
        ("deletions", "Del", 6),
        ("volume", "Vol", 6),
        ("del_pct", "Del%", 8),
    ])

    # By Character
    data = top_deleted_by_character(15)
    print_table("Deletions by Character", data, [
        ("name", "Character", 18),
        ("gen", "Gen", 6),
        ("deletions", "Del", 5),
        ("volume", "Vol", 5),
        ("del_pct", "Del%", 8),
    ])

    # By Source
    data = top_deleted_by_source()
    print_table("Deletions by Source", data, [
        ("source", "Source", 15),
        ("deletions", "Del", 6),
        ("volume", "Vol", 6),
        ("del_pct", "Del%", 8),
    ])

    # By Variant
    data = top_deleted_by_variant()
    print_table("Deletions by Variant", data, [
        ("variant", "Variant", 15),
        ("deletions", "Del", 6),
        ("volume", "Vol", 6),
        ("del_pct", "Del%", 8),
    ])


# =============================================================================
# Admin Analysis Functions
# =============================================================================

def get_variant_statistics(ip: str = "pokemon") -> List[Dict]:
    """
    Get comprehensive variant statistics for admin analysis.

    Returns list of dicts with:
        variant, variant_group, total_images, characters_covered,
        win_pct, del_pct, avg_battles_per_image, quality_score,
        total_battles, deletions
    """
    from core.utils import get_sources, get_tag_variants

    with get_db_connection() as conn:
        cursor = conn.cursor()

        # Get battle stats per variant
        cursor.execute("""
            SELECT
                variant,
                COUNT(DISTINCT path) as total_images,
                COUNT(DISTINCT name) as characters_covered,
                SUM(CASE WHEN result='win' THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN result='loss' THEN 1 ELSE 0 END) as losses,
                COUNT(*) as total_battles
            FROM battles
            WHERE variant IS NOT NULL
            GROUP BY variant
        """)
        battle_stats = {row['variant']: dict(row) for row in cursor.fetchall()}

        # Get deletion stats per variant
        cursor.execute("""
            SELECT variant, COUNT(*) as deletions
            FROM deletions
            WHERE variant IS NOT NULL
            GROUP BY variant
        """)
        deletion_stats = {row['variant']: row['deletions'] for row in cursor.fetchall()}

    # Get volume (current images on disk)
    volume_counts = get_volume_counts('variant')

    # Get total number of characters using utility function
    index = get_index()
    total_characters = len(get_all_characters(index))

    # Get variant groups
    variant_to_group = {}
    for source in get_sources(ip):
        for tv in get_tag_variants(source):
            variant_to_group[tv['variant_name']] = tv.get('variant_group', 'other')

    # Combine all stats
    results = []
    for variant, stats in battle_stats.items():
        deletions = deletion_stats.get(variant, 0)
        volume = volume_counts.get(variant, 0)
        total = deletions + volume
        del_pct = round(100.0 * deletions / total, 1) if total > 0 else 0

        # Calculate metrics
        win_pct = round(100.0 * stats['wins'] / stats['total_battles'], 1) if stats['total_battles'] > 0 else 0
        win_rate = win_pct / 100.0
        delete_rate = del_pct / 100.0
        coverage = stats['characters_covered'] / total_characters if total_characters > 0 else 0
        avg_battles_per_image = round(stats['total_battles'] / stats['total_images'], 1) if stats['total_images'] > 0 else 0

        # Quality score: (win_rate * 0.5) + ((1 - deletion_rate) * 0.3) + (coverage * 0.2)
        quality_score = (win_rate * 0.5) + ((1 - delete_rate) * 0.3) + (coverage * 0.2)

        results.append({
            'variant': variant,
            'variant_group': variant_to_group.get(variant, 'other'),
            'total_images': volume,
            'characters_covered': stats['characters_covered'],
            'win_pct': win_pct,
            'del_pct': del_pct,
            'avg_battles_per_image': avg_battles_per_image,
            'quality_score': round(quality_score * 100, 1),
            'total_battles': stats['total_battles'],
            'deletions': deletions
        })

    return sorted(results, key=lambda x: x['quality_score'], reverse=True)


def get_character_statistics(ip: str = "pokemon", gen: str = None) -> List[Dict]:
    """
    Get character statistics including missing variants.

    Returns list of dicts with:
        name, group, total_images, win_pct, del_pct, missing_variants
    """
    from core.utils import get_sources, get_tag_variants

    with get_db_connection() as conn:
        cursor = conn.cursor()

        # Build query with optional gen filter
        query = """
            SELECT
                name,
                group_name,
                COUNT(DISTINCT path) as total_images,
                SUM(CASE WHEN result='win' THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN result='loss' THEN 1 ELSE 0 END) as losses,
                COUNT(*) as total_battles
            FROM battles
            WHERE name IS NOT NULL
        """
        params = []
        if gen:
            query += " AND group_name = ?"
            params.append(gen)
        query += " GROUP BY name, group_name"

        cursor.execute(query, params)
        battle_stats = {(row['name'], row['group_name']): dict(row) for row in cursor.fetchall()}

        # Get deletion stats
        query = "SELECT name, group_name, COUNT(*) as deletions FROM deletions WHERE name IS NOT NULL"
        params = []
        if gen:
            query += " AND group_name = ?"
            params.append(gen)
        query += " GROUP BY name, group_name"

        cursor.execute(query, params)
        deletion_stats = {(row['name'], row['group_name']): row['deletions'] for row in cursor.fetchall()}

    # Get volume (current images on disk)
    volume_counts = get_volume_counts('character')

    # Get all variants for this IP
    all_variants = set()
    for source in get_sources(ip):
        for tv in get_tag_variants(source):
            all_variants.add(tv['variant_name'])

    # Get character variants from index using utility function
    index = get_index()
    character_variants = group_by_character_variant(index)

    # Combine results
    results = []
    for (name, group), stats in battle_stats.items():
        deletions = deletion_stats.get((name, group), 0)
        volume = volume_counts.get((name, group), 0)
        total = deletions + volume
        del_pct = round(100.0 * deletions / total, 1) if total > 0 else 0

        win_pct = round(100.0 * stats['wins'] / stats['total_battles'], 1) if stats['total_battles'] > 0 else 0

        # Get missing variants
        has_variants = character_variants.get((name, group), set())
        missing_variants = sorted(all_variants - has_variants)

        results.append({
            'name': name,
            'group': group,
            'total_images': volume,
            'win_pct': win_pct,
            'del_pct': del_pct,
            'total_battles': stats['total_battles'],
            'deletions': deletions,
            'missing_variants': missing_variants,
            'missing_count': len(missing_variants)
        })

    return sorted(results, key=lambda x: x['win_pct'], reverse=True)


def get_coverage_matrix(ip: str = "pokemon") -> Dict:
    """
    Get character × variant coverage matrix for heatmap.

    Returns dict with:
        characters: List of (name, group) tuples
        variants: List of variant names
        matrix: 2D list where matrix[char_idx][variant_idx] = {
            'has_images': bool,
            'win_rate': float,
            'deletion_rate': float,
            'status': 'good'|'poor'|'missing'|'deprecated'
        }
    """
    from core.utils import get_sources, get_tag_variants

    with get_db_connection() as conn:
        cursor = conn.cursor()

        # Get all character×variant battle stats
        cursor.execute("""
            SELECT
                name,
                group_name,
                variant,
                SUM(CASE WHEN result='win' THEN 1 ELSE 0 END) as wins,
                COUNT(*) as total_battles
            FROM battles
            WHERE name IS NOT NULL AND variant IS NOT NULL
            GROUP BY name, group_name, variant
        """)

        battle_data = {}
        for row in cursor.fetchall():
            key = (row['name'], row['group_name'], row['variant'])
            win_rate = round(100.0 * row['wins'] / row['total_battles'], 1) if row['total_battles'] > 0 else 0
            battle_data[key] = {'win_rate': win_rate, 'battles': row['total_battles']}

        # Get deletion data
        cursor.execute("""
            SELECT
                name,
                group_name,
                variant,
                COUNT(*) as deletions
            FROM deletions
            WHERE name IS NOT NULL AND variant IS NOT NULL
            GROUP BY name, group_name, variant
        """)
        deletion_data = {(row['name'], row['group_name'], row['variant']): row['deletions'] for row in cursor.fetchall()}

    # Get index data
    index = get_index()
    character_variant_images: Dict[Tuple[str, str, str], int] = defaultdict(int)
    for img in index.images:
        if img.variant:
            character_variant_images[(img.name, img.group_name, img.variant)] += 1

    # Get all characters using utility function
    characters = sorted(get_all_characters(index))
    all_variants = set()
    deprecated_variants = set()
    for source in get_sources(ip):
        for tv in get_tag_variants(source):
            all_variants.add(tv['variant_name'])
        # Check for deprecated
        for dtv in source.get('deprecated_tag_variants', []):
            deprecated_variants.add(dtv['variant_name'])

    variants = sorted(all_variants)

    # Build matrix
    matrix = []
    for char_name, char_group in characters:
        char_row = []
        for variant in variants:
            key = (char_name, char_group, variant)
            image_count = character_variant_images.get(key, 0)
            deletions = deletion_data.get(key, 0)
            total = image_count + deletions

            if variant in deprecated_variants:
                status = 'deprecated'
                win_rate = 0
                del_rate = 0
            elif image_count == 0:
                status = 'missing'
                win_rate = 0
                del_rate = 0
            else:
                battle_info = battle_data.get(key, {})
                win_rate = battle_info.get('win_rate', 0)
                del_rate = round(100.0 * deletions / total, 1) if total > 0 else 0

                # Determine status based on metrics
                status = 'poor' if del_rate > 50 or win_rate < 30 else 'good'

            char_row.append({
                'has_images': image_count > 0,
                'image_count': image_count,
                'win_rate': win_rate,
                'deletion_rate': del_rate,
                'status': status
            })
        matrix.append(char_row)

    return {
        'characters': characters,
        'variants': variants,
        'matrix': matrix
    }


def get_deprecation_candidates(ip: str = "pokemon") -> Dict:
    """
    Get variants and characters that are candidates for deprecation/retirement.

    Returns dict with:
        variants: List of variant dicts with deprecation reasons
        characters: List of character dicts with retirement reasons
    """

    variant_stats = get_variant_statistics(ip)
    character_stats = get_character_statistics(ip)

    # Define thresholds
    HIGH_DELETION_RATE = 60.0
    LOW_COVERAGE = 30.0
    LOW_BATTLES_PER_IMAGE = 2.0
    STALE_DAYS = 30

    # Get last battle date per variant
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT variant, MAX(timestamp) as last_battle
            FROM battles
            WHERE variant IS NOT NULL
            GROUP BY variant
        """)
        last_battle_dates = {row['variant']: row['last_battle'] for row in cursor.fetchall()}

    # Find variant candidates
    variant_candidates = []
    for v in variant_stats:
        reasons = []

        if v['del_pct'] > HIGH_DELETION_RATE:
            reasons.append(f"High deletion rate ({v['del_pct']}%)")

        coverage_pct = (v['characters_covered'] / len(character_stats)) * 100 if character_stats else 0
        if coverage_pct < LOW_COVERAGE:
            reasons.append(f"Low coverage ({round(coverage_pct, 1)}%)")

        if v['avg_battles_per_image'] < LOW_BATTLES_PER_IMAGE:
            reasons.append(f"Low battles/image ({v['avg_battles_per_image']})")

        # Check staleness
        last_battle = last_battle_dates.get(v['variant'])
        if last_battle:
            last_date = datetime.datetime.fromisoformat(last_battle)
            days_since = (datetime.datetime.now() - last_date).days
            if days_since > STALE_DAYS:
                reasons.append(f"No battles in {days_since} days")

        if reasons:
            variant_candidates.append({
                **v,
                'reasons': reasons
            })

    # Find character candidates (low performance across all variants)
    character_candidates = []
    for c in character_stats:
        reasons = []

        if c['del_pct'] > HIGH_DELETION_RATE:
            reasons.append(f"High deletion rate ({c['del_pct']}%)")

        if c['win_pct'] < 30:
            reasons.append(f"Low win rate ({c['win_pct']}%)")

        if c['missing_count'] > len(variant_stats) * 0.7:  # Missing >70% of variants
            reasons.append(f"Missing {c['missing_count']} variants")

        if reasons:
            character_candidates.append({
                **c,
                'reasons': reasons
            })

    return {
        'variants': sorted(variant_candidates, key=lambda x: len(x['reasons']), reverse=True),
        'characters': sorted(character_candidates, key=lambda x: len(x['reasons']), reverse=True)
    }


def get_best_images_per_variant(ip: str = "pokemon", limit: int = 5) -> Dict[str, List[Dict]]:
    """
    Get top performing images for each variant.
    Score = win_rate × sqrt(battle_count) to dampen volume bias.

    Returns dict mapping variant → list of top image dicts
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                variant,
                path,
                name,
                group_name,
                source,
                SUM(CASE WHEN result='win' THEN 1 ELSE 0 END) as wins,
                COUNT(*) as battles
            FROM battles
            WHERE variant IS NOT NULL
            GROUP BY variant, path
            HAVING battles >= 3
        """)

        variant_images = defaultdict(list)
        for row in cursor.fetchall():
            win_rate = row['wins'] / row['battles'] if row['battles'] > 0 else 0
            score = win_rate * math.sqrt(row['battles'])

            variant_images[row['variant']].append({
                'path': row['path'],
                'name': row['name'],
                'group': row['group_name'],
                'source': row['source'],
                'wins': row['wins'],
                'battles': row['battles'],
                'win_rate': round(win_rate * 100, 1),
                'score': round(score, 2)
            })

    # Sort and limit each variant's images
    result = {}
    for variant, images in variant_images.items():
        result[variant] = sorted(images, key=lambda x: x['score'], reverse=True)[:limit]

    return result


def run_all():
    """Run all analyses."""
    # Summary
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(DISTINCT battle_id) FROM battles")
        total_battles = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM deletions")
        total_deletions = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM image_stats")
        total_images = cursor.fetchone()[0]

    print("\n" + "="*60)
    print(" ARENA DATA ANALYSIS")
    print("="*60)
    print(f"  Total Battles: {total_battles}")
    print(f"  Total Deletions: {total_deletions}")
    print(f"  Images with Stats: {total_images}")

    run_winners_analysis()
    run_volume_analysis()
    run_deletions_analysis()


if __name__ == "__main__":
    if len(sys.argv) > 1:
        cmd = sys.argv[1].lower()
        if cmd == "winners":
            run_winners_analysis()
        elif cmd == "volume":
            run_volume_analysis()
        elif cmd == "deletions":
            run_deletions_analysis()
        else:
            print(f"Unknown command: {cmd}")
            print("Usage: python reports.py [winners|volume|deletions]")
            sys.exit(1)
    else:
        run_all()
