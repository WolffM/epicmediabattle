"""
Arena analysis module - SQL queries, formatters, and report runners.

This module provides comprehensive analysis of Arena battle data:
- Winner statistics (by gen, character, source, variant)
- Volume statistics (battle counts)
- Deletion statistics
- Admin analysis tools (variant quality, coverage matrix, deprecation candidates)

Usage:
    from games.arena.analysis import run_all, get_variant_statistics

    # Run all standard reports
    run_all()

    # Get variant stats for admin dashboard
    stats = get_variant_statistics("pokemon")
"""

# Query functions
# Formatting functions
from games.arena.analysis.formatters import (
    format_gen,
    print_table,
)
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

# Report runners
# Admin analysis functions
from games.arena.analysis.reports import (
    get_best_images_per_variant,
    get_character_statistics,
    get_coverage_matrix,
    get_deprecation_candidates,
    get_variant_statistics,
    run_all,
    run_deletions_analysis,
    run_volume_analysis,
    run_winners_analysis,
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
