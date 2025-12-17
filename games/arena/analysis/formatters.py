"""
Display and formatting utilities for Arena analysis.
"""

from typing import Dict, List, Tuple

from core.utils import normalize_gen


def format_gen(gen_value, compact: bool = True) -> str:
    """Format generation value for display (uses centralized normalize_gen)."""
    return normalize_gen(gen_value, compact=compact)


def print_table(title: str, data: List[Dict], columns: List[Tuple[str, str, int]], gen_keys: List[str] = None):
    """
    Print a formatted table.

    Args:
        title: Table title
        data: List of row dicts
        columns: List of (key, header, width) tuples
        gen_keys: List of column keys that should be formatted as generations
    """
    if gen_keys is None:
        gen_keys = ['gen']  # Default: 'gen' columns get formatted

    print(f"\n{'='*60}")
    print(f" {title}")
    print('='*60)

    if not data:
        print("  No data")
        return

    # Header
    header = "  "
    for _key, label, width in columns:
        header += f"{label:<{width}}"
    print(header)
    print("  " + "-" * (sum(w for _, _, w in columns)))

    # Rows
    for row in data:
        line = "  "
        for key, _, width in columns:
            val = row.get(key, "")
            # Apply generation formatting for gen columns
            if key in gen_keys:
                val = format_gen(val)
            elif isinstance(val, float):
                val = f"{val:.1f}%"
            line += f"{val!s:<{width}}"
        print(line)
