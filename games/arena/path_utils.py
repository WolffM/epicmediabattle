"""
Shared utility functions for the arena application.

This module provides centralized utilities for:
- Path normalization and comparison (Windows case-insensitivity)
- Image lookup in the index
- Stats addition to image dicts
- Request/scope dictionary building
"""

import json
import os
from collections import defaultdict
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Dict, List, Optional, Set, Tuple

if TYPE_CHECKING:
    from image_index import ImageIndex

# ============================================================
# PATH UTILITIES
# ============================================================


def normalize_path(path: str) -> str:
    """
    Normalize path for case-insensitive comparison on Windows.

    On Windows, file paths are case-insensitive, but Python string
    comparison is case-sensitive. This function normalizes paths
    for safe in-memory comparisons.

    Note: For database queries, use COLLATE NOCASE instead.

    Args:
        path: File path string

    Returns:
        Normalized path (lowercase on Windows, unchanged on Unix)
    """
    if os.name == 'nt':  # Windows
        return path.lower()
    return path


def paths_equal(path1: str, path2: str) -> bool:
    """
    Compare two paths in a platform-safe way.

    Args:
        path1: First path
        path2: Second path

    Returns:
        True if paths refer to the same file (case-insensitive on Windows)
    """
    return normalize_path(path1) == normalize_path(path2)


def normalize_path_set(paths: List[str]) -> set:
    """
    Create a normalized set of paths for efficient membership testing.

    Use this instead of direct `path in set` checks to ensure
    case-insensitive matching on Windows.

    Args:
        paths: List of paths to normalize

    Returns:
        Set of normalized paths
    """
    return {normalize_path(p) for p in paths}


def path_in_set(path: str, normalized_set: set) -> bool:
    """
    Check if a path is in a normalized path set.

    Args:
        path: Path to check
        normalized_set: Set created by normalize_path_set()

    Returns:
        True if path is in the set (case-insensitive on Windows)
    """
    return normalize_path(path) in normalized_set


def validate_path_in_output(path: Path, output_dir: Path) -> bool:
    """
    Validate that a path is within the allowed output directory.

    Used for security checks before file operations.

    Args:
        path: Path to validate
        output_dir: Allowed output directory

    Returns:
        True if path is within output_dir, False otherwise
    """
    try:
        path.resolve().relative_to(output_dir.resolve())
        return True
    except ValueError:
        return False


# ============================================================
# IMAGE INDEX UTILITIES
# ============================================================


def find_image_by_path(index: 'ImageIndex', path: str) -> Optional[Dict]:
    """
    Find a single image in the index by path.

    Uses case-insensitive comparison on Windows.

    Args:
        index: ImageIndex instance
        path: Path to search for

    Returns:
        Image dict if found, None otherwise
    """
    normalized = normalize_path(path)
    for img in index.images:
        if normalize_path(img.path) == normalized:
            return img.to_dict()
    return None


def find_images_by_paths(index: 'ImageIndex', paths: List[str]) -> Dict[str, Optional[Dict]]:
    """
    Find multiple images by paths in a single pass through the index.

    More efficient than calling find_image_by_path multiple times.

    Args:
        index: ImageIndex instance
        paths: List of paths to search for

    Returns:
        Dict mapping original path -> image dict (or None if not found)
    """
    # Build a normalized path -> original path mapping
    normalized_map = {normalize_path(p): p for p in paths}
    result = dict.fromkeys(paths)

    for img in index.images:
        norm_img_path = normalize_path(img.path)
        if norm_img_path in normalized_map:
            original_path = normalized_map[norm_img_path]
            result[original_path] = img.to_dict()

    return result


# ============================================================
# STATS UTILITIES
# ============================================================


def add_stats_to_matchup(
    img1: Dict,
    img2: Dict,
    get_stats_fn: Callable[[str], Dict]
) -> Tuple[Dict, Dict]:
    """
    Add battle stats to both images in a matchup.

    Args:
        img1: First image dictionary
        img2: Second image dictionary
        get_stats_fn: Function that takes a path and returns stats dict

    Returns:
        Tuple of (img1, img2) with 'stats' keys added
    """
    img1['stats'] = get_stats_fn(img1['path'])
    img2['stats'] = get_stats_fn(img2['path'])
    return img1, img2


# ============================================================
# JSON CONFIG UTILITIES
# ============================================================


def get_ip_sources_path() -> Path:
    """Get the path to ip_sources.json."""
    return Path(__file__).parent.parent.parent / "Input" / "ip_sources.json"


def update_ip_sources_json(modifier_fn: Callable[[Dict], None], *cache_clear_fns: Callable[[], None]) -> None:
    """
    Load ip_sources.json, apply modifications, save, and clear caches.

    This helper centralizes the load/modify/save pattern used by admin
    endpoints, ensuring consistent handling and proper cache invalidation.

    Args:
        modifier_fn: Function that takes ip_sources dict and modifies it in-place
        cache_clear_fns: Functions to call after save (e.g., reload_ip_sources, clear_caches)

    Example:
        def add_deprecated(ip_sources):
            ip_sources['pokemon']['deprecated_variants'].append('new_variant')

        update_ip_sources_json(add_deprecated, reload_ip_sources, clear_deprecated_cache)
    """
    ip_sources_path = get_ip_sources_path()

    with open(ip_sources_path, encoding='utf-8') as f:
        ip_sources = json.load(f)

    modifier_fn(ip_sources)

    with open(ip_sources_path, 'w', encoding='utf-8') as f:
        json.dump(ip_sources, f, indent=4, ensure_ascii=False)

    for clear_fn in cache_clear_fns:
        clear_fn()


# ============================================================
# IMAGE INDEX GROUPING UTILITIES
# ============================================================


def get_all_characters(index: 'ImageIndex') -> Set[Tuple[str, str]]:
    """
    Get set of all unique (name, group_name) tuples from index.

    Useful for iterating over all characters without duplicates.

    Args:
        index: ImageIndex instance

    Returns:
        Set of (name, group_name) tuples
    """
    return {(img.name, img.group_name) for img in index.images}


def group_by_character_variant(index: 'ImageIndex') -> Dict[Tuple[str, str], Set[str]]:
    """
    Group variants by character (name, group_name).

    Creates a mapping from character identity to all their variants.

    Args:
        index: ImageIndex instance

    Returns:
        Dict mapping (name, group_name) -> set of variant names
    """
    result = defaultdict(set)
    for img in index.images:
        if img.variant:
            result[(img.name, img.group_name)].add(img.variant)
    return dict(result)


# ============================================================
# MATCHUP REQUEST UTILITIES
# ============================================================


def extract_matchup_kwargs(req) -> Dict:
    """
    Extract matchup-related kwargs from a request object.

    Consolidates the common pattern of extracting scope/match fields
    for matcher.get_matchup() calls.

    Args:
        req: Request object with scope attributes (BattleResult, DeleteRequest, etc.)

    Returns:
        Dict suitable for passing as **kwargs to matcher.get_matchup()
    """
    kwargs = {
        'scope_level': req.scope_level,
        'scope_ip': req.scope_ip,
        'scope_group': req.scope_group,
        'scope_character': req.scope_character,
        'scope_source': req.scope_source,
        'scope_variant': req.scope_variant,
        'match_source': req.match_source,
        'match_variant': req.match_variant,
        'match_variant_group': req.match_variant_group,
        'scope_universe': getattr(req, 'scope_universe', None),
    }
    # Add exclude_recent if present
    if hasattr(req, 'exclude_recent'):
        kwargs['exclude_recent'] = req.exclude_recent
    return kwargs
