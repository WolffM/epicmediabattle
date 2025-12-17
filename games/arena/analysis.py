"""
Data analysis queries for Arena battle and deletion statistics.

This module re-exports all functions from the games.arena.analysis package
for backward compatibility. New code should import from games.arena.analysis directly.

Usage:
    python analysis.py              # Run all analyses
    python analysis.py winners      # Top winners only
    python analysis.py volume       # Top volume only
    python analysis.py deletions    # Top deleted only
"""

import sys
from pathlib import Path

# Add parent paths for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Re-export everything from the analysis package for backward compatibility
from games.arena.analysis import (
    # Formatters
    format_gen,
    get_best_images_per_variant,
    get_character_statistics,
    get_coverage_matrix,
    get_deprecation_candidates,
    # Admin functions
    get_variant_statistics,
    # Query functions
    get_volume_counts,
    print_table,
    run_all,
    run_deletions_analysis,
    run_volume_analysis,
    # Report runners
    run_winners_analysis,
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

__all__ = [
    # Queries
    'get_volume_counts',
    'top_winners_by_gen',
    'top_winners_by_character',
    'top_winners_by_source',
    'top_winners_by_variant',
    'top_volume_by_gen',
    'top_volume_by_character',
    'top_deleted_by_gen',
    'top_deleted_by_character',
    'top_deleted_by_source',
    'top_deleted_by_variant',

    # Formatters
    'format_gen',
    'print_table',

    # Report runners
    'run_winners_analysis',
    'run_volume_analysis',
    'run_deletions_analysis',
    'run_all',

    # Admin functions
    'get_variant_statistics',
    'get_character_statistics',
    'get_coverage_matrix',
    'get_deprecation_candidates',
    'get_best_images_per_variant',
]


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
            print("Usage: python analysis.py [winners|volume|deletions]")
            sys.exit(1)
    else:
        run_all()
