"""
Matchup selection logic for arena battles.
Handles scope filtering and match constraints (match_source, match_variant).

Rules:
1. Match contestants with equal battle counts (prefer lowest count)
2. Avoid same-character matchups unless no other option
3. Graceful fallback: never error, always find a valid matchup or return None
"""

import random
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

# Add parent paths for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from core.utils import IP_SOURCES, get_variant_to_group
from games.arena import database
from games.arena.image_index import get_index
from games.arena.logging_config import get_logger
from games.arena.path_utils import (
    find_image_by_path,
    normalize_path_set,
    path_in_set,
    paths_equal,
)

# Get logger from centralized config
logger = get_logger(__name__)

# Cached deprecated variants set
_deprecated_variants: Optional[Set[str]] = None


def get_deprecated_variants() -> Set[str]:
    """Get set of deprecated variant names from config."""
    global _deprecated_variants
    if _deprecated_variants is None:
        _deprecated_variants = set()
        # Iterate through universe -> IP -> sources structure
        for universe_ips in IP_SOURCES.values():
            for ip_config in universe_ips.values():
                for source in ip_config.get('sources', []):
                    for dv in source.get('deprecated_tag_variants', []):
                        _deprecated_variants.add(dv['variant_name'])
    return _deprecated_variants


def clear_deprecated_cache():
    """Clear the deprecated variants cache. Call after modifying IP_SOURCES."""
    global _deprecated_variants
    _deprecated_variants = None


def normalize_variant(variant: Optional[str], deprecated: Optional[Set[str]] = None) -> str:
    """
    Normalize variant for matching - deprecated variants treated as base.

    Args:
        variant: The variant string (may be None or empty)
        deprecated: Set of deprecated variant names (fetched if not provided)

    Returns:
        '__base__' for None, empty, or deprecated variants; original otherwise
    """
    if deprecated is None:
        deprecated = get_deprecated_variants()
    if not variant or variant in deprecated:
        return '__base__'
    return variant


def _get_image_battle_counts(candidates: List[Dict]) -> Dict[str, int]:
    """
    Get battle count for each candidate image.

    Uses batch lookup from image_stats table for efficiency.

    Returns dict mapping image path to total battle count.
    """
    paths = [img['path'] for img in candidates]
    # Batch lookup from image_stats table
    counts = database.get_all_image_battle_counts(paths)
    # Ensure all paths have a count (default 0 for new images)
    return {path: counts.get(path, 0) for path in paths}


def _get_image_stats(candidates: List[Dict]) -> Dict[str, Dict]:
    """
    Get full stats (wins, losses, total_battles) for each candidate image.

    Uses batch lookup from image_stats table for efficiency.

    Returns dict mapping image path to {wins, losses, total_battles}.
    """
    paths = [img['path'] for img in candidates]
    return database.get_all_image_stats(paths)


def _get_rating(stats: Dict) -> Tuple[int, int]:
    """
    Get rating tuple (wins, losses) for an image.

    Returns (wins, losses) tuple for grouping.
    """
    return (stats.get('wins', 0), stats.get('losses', 0))


def _select_fair_matchup(candidates: List[Dict], exclude_path: str = None) -> Optional[Tuple[Dict, Dict]]:
    """
    Select a fair matchup from candidates following STRICT rules:
    1. First priority: Match 0v0 images (no battles yet) - by battle count
    2. For images with battles: Match by rating (wins-losses)
    3. Avoid same-character matchups when possible

    Args:
        candidates: List of candidate image dicts
        exclude_path: Optional path to exclude (e.g., for kept image scenarios)

    Returns:
        Tuple of (img1, img2) or None if no valid matchup
    """
    logger.debug(f"_select_fair_matchup called with {len(candidates)} candidates, exclude_path={exclude_path}")

    if exclude_path:
        candidates = [c for c in candidates if not paths_equal(c['path'], exclude_path)]
        logger.debug(f"After excluding path, {len(candidates)} candidates remain")

    if len(candidates) < 2:
        logger.warning("Less than 2 candidates, returning None")
        return None

    # Get full stats for all candidates
    all_stats = _get_image_stats(candidates)
    logger.debug(f"Image stats: {all_stats}")

    # Separate candidates into 0-battle (new) and battled groups
    new_images = []
    battled_images = []
    for img in candidates:
        stats = all_stats[img['path']]
        if stats['total_battles'] == 0:
            new_images.append(img)
        else:
            battled_images.append(img)

    logger.info(f"New images (0 battles): {len(new_images)}, Battled images: {len(battled_images)}")

    # PRIORITY 1: Match new images (0v0) first
    if len(new_images) >= 2:
        matchup = _select_from_group(new_images, all_stats)
        if matchup:
            img1, img2 = matchup
            s1, s2 = all_stats[img1['path']], all_stats[img2['path']]
            logger.info(f"MATCHUP SELECTED (0v0): {img1['name']} ({s1['wins']}-{s1['losses']}) vs {img2['name']} ({s2['wins']}-{s2['losses']})")
            return matchup

    # PRIORITY 2: Match battled images by rating (wins-losses)
    if len(battled_images) >= 2:
        # Group by rating (wins, losses)
        by_rating: Dict[Tuple[int, int], List[Dict]] = {}
        for img in battled_images:
            stats = all_stats[img['path']]
            rating = _get_rating(stats)
            if rating not in by_rating:
                by_rating[rating] = []
            by_rating[rating].append(img)

        # Log rating distribution
        rating_dist = [(f"{r[0]}-{r[1]}", len(imgs)) for r, imgs in sorted(by_rating.items())]
        logger.info(f"Rating distribution: {rating_dist}")

        # Try each rating group (prioritize lower total battles)
        sorted_ratings = sorted(by_rating.keys(), key=lambda r: r[0] + r[1])  # Sort by total battles

        for rating in sorted_ratings:
            group = by_rating[rating]
            if len(group) >= 2:
                matchup = _select_from_group(group, all_stats)
                if matchup:
                    img1, img2 = matchup
                    s1, s2 = all_stats[img1['path']], all_stats[img2['path']]
                    logger.info(f"MATCHUP SELECTED (rating {rating[0]}-{rating[1]}): {img1['name']} ({s1['wins']}-{s1['losses']}) vs {img2['name']} ({s2['wins']}-{s2['losses']})")
                    return matchup

    # No valid matchup found
    logger.error("No valid matchup found!")
    return None


def _select_from_group(group: List[Dict], all_stats: Dict[str, Dict], allow_same_character: bool = False) -> Optional[Tuple[Dict, Dict]]:
    """
    Select two images from a group, requiring different characters.

    Args:
        group: List of candidate images in the same tier/rating
        all_stats: Pre-fetched stats for all candidates
        allow_same_character: If True, allow same-character matchups as fallback

    Returns:
        Tuple of (img1, img2) or None if no valid matchup (e.g., only one character)
    """
    if len(group) < 2:
        return None

    # Group by character name
    by_character: Dict[str, List[Dict]] = {}
    for img in group:
        name = img['name']
        if name not in by_character:
            by_character[name] = []
        by_character[name].append(img)

    characters = list(by_character.keys())

    if len(characters) >= 2:
        # Pick from 2 different characters
        char1, char2 = random.sample(characters, 2)
        img1 = random.choice(by_character[char1])
        img2 = random.choice(by_character[char2])
        return (img1, img2)
    else:
        # Only one character in this group
        if allow_same_character:
            # Same character - pick two different images (only at character/source/variant scope)
            img1, img2 = random.sample(group, 2)
            logger.debug(f"Same-character matchup allowed: {img1['name']} vs {img2['name']}")
            return (img1, img2)
        else:
            # Return None to signal caller should try other groups
            logger.debug(f"Only one character ({characters[0]}) in group, skipping")
            return None


def get_matchup(
    scope_level: str,
    scope_ip: str,
    scope_group: Optional[str] = None,
    scope_character: Optional[str] = None,
    scope_source: Optional[str] = None,
    scope_variant: Optional[str] = None,
    match_source: bool = False,
    match_variant: bool = False,
    match_variant_group: bool = False,
    exclude_recent: Optional[List[str]] = None,
    scope_universe: Optional[str] = None
) -> Optional[Tuple[Dict, Dict]]:
    """
    Get a random matchup based on scope and constraints.

    Scope levels (hierarchical):
        - 'universe': All images in a universe (if supported)
        - 'ip': All images in the IP
        - 'group': All images in a specific group (gen)
        - 'character': All images of a specific character
        - 'source': All images from a specific source
        - 'variant': All images of a specific variant

    Args:
        scope_level: One of 'universe', 'ip', 'group', 'character', 'source', 'variant'
        scope_ip: IP name (required for level >= 'ip')
        scope_group: Group/gen name (required if level >= 'group')
        scope_character: Character name (required if level >= 'character')
        scope_source: Source name (required if level >= 'source')
        scope_variant: Variant name (required if level == 'variant')
        match_source: If True, both images must have same source
        match_variant: If True, both images must have same variant
        match_variant_group: If True, both images must have same variant_group (AI, artist, niche)
        exclude_recent: List of recent image paths to exclude (if possible)
        scope_universe: Universe name (optional, filters by universe)

    Returns:
        Tuple of (image1_dict, image2_dict) or None if not enough images
    """
    logger.info("=== get_matchup called ===")
    logger.info(f"Scope: level={scope_level}, universe={scope_universe}, ip={scope_ip}, group={scope_group}, char={scope_character}")
    logger.info(f"Constraints: match_source={match_source}, match_variant={match_variant}, match_variant_group={match_variant_group}")
    logger.info(f"exclude_recent count: {len(exclude_recent) if exclude_recent else 0}")

    index = get_index()

    # Get candidate pool based on scope level
    candidates = _get_scope_candidates(
        index, scope_level, scope_ip, scope_group,
        scope_character, scope_source, scope_variant, scope_universe
    )
    logger.info(f"Total candidates from scope: {len(candidates)}")

    if len(candidates) < 2:
        logger.warning("Less than 2 candidates, returning None")
        return None

    # Try to exclude recent images first (soft constraint)
    if exclude_recent:
        exclude_set = normalize_path_set(exclude_recent)
        filtered_candidates = [c for c in candidates if not path_in_set(c['path'], exclude_set)]
        logger.debug(f"After excluding recent: {len(filtered_candidates)} candidates (was {len(candidates)})")
        # Only use filtered if we still have enough for a matchup
        if len(filtered_candidates) >= 2:
            candidates = filtered_candidates
        else:
            logger.warning("Not enough candidates after excluding recent, using all")

    # Apply match constraints
    if match_source or match_variant or match_variant_group:
        logger.debug("Using constrained matchup")
        result = _get_constrained_matchup(candidates, match_source, match_variant, match_variant_group)
    else:
        logger.debug("Using random matchup")
        result = _get_random_matchup(candidates)

    if result:
        img1, img2 = result
        # Get fresh battle counts for logging
        counts = _get_image_battle_counts([img1, img2])
        logger.info(f"=== FINAL MATCHUP: {img1['name']} ({counts[img1['path']]} battles) vs {img2['name']} ({counts[img2['path']]} battles) ===")
    else:
        logger.warning("=== NO MATCHUP FOUND ===")

    return result


def _get_scope_candidates(
    index,
    scope_level: str,
    scope_ip: str,
    scope_group: Optional[str] = None,
    scope_character: Optional[str] = None,
    scope_source: Optional[str] = None,
    scope_variant: Optional[str] = None,
    scope_universe: Optional[str] = None
) -> List[Dict]:
    """Get candidate images based on scope level."""

    # Build filter kwargs based on scope
    kwargs: Dict[str, Optional[str]] = {}

    # Always add universe if provided
    if scope_universe:
        kwargs['universe'] = scope_universe

    # Add IP if we're at IP level or below
    if scope_level in ['ip', 'group', 'character', 'source', 'variant']:
        kwargs['ip'] = scope_ip

    if scope_level in ['group', 'character', 'source', 'variant']:
        kwargs['group'] = scope_group

    if scope_level in ['character', 'source', 'variant']:
        kwargs['character'] = scope_character

    if scope_level in ['source', 'variant']:
        kwargs['source'] = scope_source

    if scope_level == 'variant':
        kwargs['variant'] = scope_variant

    return index.get_images(**kwargs)


def _get_random_matchup(candidates: List[Dict]) -> Optional[Tuple[Dict, Dict]]:
    """
    Get a fair matchup from candidates.

    STRICT rules:
    1. Equal battle count (lowest tier first)
    2. Different characters when possible
    3. NO fallback to unequal battle counts
    """
    if len(candidates) < 2:
        return None

    # Use strict fair matchup - no fallbacks
    return _select_fair_matchup(candidates)


def _get_constrained_matchup(
    candidates: List[Dict],
    match_source: bool,
    match_variant: bool,
    match_variant_group: bool = False
) -> Optional[Tuple[Dict, Dict]]:
    """
    Get matchup respecting match_source, match_variant, and match_variant_group constraints.

    Strategy (two-pass for global 0v0 priority):
    1. Group candidates by the constraint key(s)
    2. FIRST PASS: Try 0v0 matches across ALL groups (prioritize new images globally)
    3. SECOND PASS: Fall back to rating-based matching within groups

    Note: match_variant and match_variant_group are mutually exclusive.
    If both are set, match_variant takes precedence.
    """
    # Build grouping key
    # Get deprecated variants once for efficiency
    deprecated = get_deprecated_variants()

    # Get variant_to_group lookup for the IP (all candidates share same IP)
    # Return empty dict if no candidates (shouldn't happen given earlier checks)
    ip = candidates[0]['ip'] if candidates else None
    variant_to_group = get_variant_to_group(ip) if ip else {}

    def get_key(img: Dict) -> tuple:
        key_parts = []
        if match_source:
            key_parts.append(img['source'])
        if match_variant:
            # Normalize variant - deprecated variants are treated as base
            key_parts.append(normalize_variant(img.get('variant'), deprecated))
        elif match_variant_group:
            # Group by variant_group (AI, artist, niche)
            # Use variant_group from image dict, or lookup from variant_to_group
            vg = img.get('variant_group') or variant_to_group.get(img.get('variant'))
            key_parts.append(vg or '__none__')
        return tuple(key_parts)

    # Group candidates
    groups: Dict[tuple, List[Dict]] = {}
    for img in candidates:
        key = get_key(img)
        if key not in groups:
            groups[key] = []
        groups[key].append(img)

    # Filter to groups with at least 2 images
    valid_groups = [g for g in groups.values() if len(g) >= 2]

    if not valid_groups:
        return None

    # Get stats for ALL candidates once (for efficiency)
    all_stats = _get_image_stats(candidates)

    # FIRST PASS: Try 0v0 matches across ALL groups (global priority for new images)
    logger.debug("Constrained matchup: FIRST PASS - looking for 0v0 matches across all groups")
    random.shuffle(valid_groups)
    for group in valid_groups:
        # Filter to new images only
        new_images = [img for img in group if all_stats[img['path']]['total_battles'] == 0]
        if len(new_images) >= 2:
            matchup = _select_from_group(new_images, all_stats)
            if matchup:
                img1, img2 = matchup
                logger.info(f"CONSTRAINED MATCHUP (0v0): {img1['name']} vs {img2['name']}")
                return matchup

    # SECOND PASS: Fall back to rating-based matching within groups
    logger.debug("Constrained matchup: SECOND PASS - rating-based matching")
    for group in valid_groups:
        matchup = _select_fair_matchup(group)
        if matchup:
            return matchup

    # No fair matchup found - don't fallback to unequal counts
    return None


def get_matchup_with_image(
    keep_path: str,
    scope_level: str,
    scope_ip: str,
    scope_group: str = None,
    scope_character: str = None,
    scope_source: str = None,
    scope_variant: str = None,
    match_source: bool = False,
    match_variant: bool = False,
    match_variant_group: bool = False,
    exclude_recent: List[str] = None,
    scope_universe: str = None
) -> Optional[Tuple[Dict, Dict]]:
    """
    Get a matchup that includes a specific image (the 'kept' image from a delete).

    The kept image will be img1, and a random opponent will be img2.
    Applies fair matchup rules (equal battles, different characters).

    If no valid opponent can be found for the kept image, returns None.
    The caller should fall back to a regular matchup.

    Args:
        keep_path: Path to the image that must be in the matchup
        scope_universe: Universe name (optional)
        (other args same as get_matchup)

    Returns:
        Tuple of (kept_image_dict, opponent_dict) or None if not possible
    """
    logger.info("=== get_matchup_with_image called ===")
    logger.info(f"keep_path={keep_path}")

    index = get_index()

    # Find the kept image in the index (case-insensitive on Windows)
    kept_image = find_image_by_path(index, keep_path)

    if not kept_image:
        logger.warning(f"Kept image not found in index: {keep_path}")
        return None

    logger.info(f"Kept image: {kept_image['name']}")

    # Get candidate pool based on scope level
    candidates = _get_scope_candidates(
        index, scope_level, scope_ip, scope_group,
        scope_character, scope_source, scope_variant, scope_universe
    )
    logger.info(f"Total candidates from scope: {len(candidates)}")

    # Remove the kept image from candidates (case-insensitive on Windows)
    candidates = [c for c in candidates if not paths_equal(c['path'], keep_path)]
    logger.debug(f"After removing kept image: {len(candidates)} candidates")

    if not candidates:
        logger.warning("No candidates after removing kept image")
        return None

    # Try to exclude recent images (soft constraint - only if we have alternatives)
    if exclude_recent:
        exclude_set = normalize_path_set(exclude_recent)
        # Don't exclude the kept image from the exclude set check
        filtered_candidates = [c for c in candidates if not path_in_set(c['path'], exclude_set)]
        logger.debug(f"After excluding recent: {len(filtered_candidates)} candidates")
        if filtered_candidates:
            candidates = filtered_candidates

    # Apply match constraints if needed
    if match_source or match_variant or match_variant_group:
        # Filter candidates to match the kept image's source/variant/variant_group
        deprecated = get_deprecated_variants()
        filtered = []

        # Get variant_to_group lookup for the IP
        ip = kept_image.get('ip')
        variant_to_group = get_variant_to_group(ip) if ip else {}

        # Get kept image's variant_group
        kept_variant_group = kept_image.get('variant_group') or variant_to_group.get(kept_image.get('variant'))

        for c in candidates:
            source_ok = not match_source or c['source'] == kept_image['source']
            # Normalize variants - deprecated variants are treated as base
            variant_ok = not match_variant or normalize_variant(c.get('variant'), deprecated) == normalize_variant(kept_image.get('variant'), deprecated)
            # Check variant_group match
            c_variant_group = c.get('variant_group') or variant_to_group.get(c.get('variant'))
            variant_group_ok = not match_variant_group or c_variant_group == kept_variant_group
            if source_ok and variant_ok and variant_group_ok:
                filtered.append(c)

        logger.debug(f"After match constraints: {len(filtered)} candidates")
        if not filtered:
            logger.warning("No candidates match constraints")
            return None
        candidates = filtered

    # Get full stats for candidates and kept image
    all_stats = _get_image_stats([*candidates, kept_image])
    kept_stats = all_stats[kept_image['path']]
    kept_rating = _get_rating(kept_stats)
    logger.info(f"Kept image rating: {kept_rating[0]}-{kept_rating[1]}")

    # STRICT: Only match with same rating (wins-losses)
    # For 0-0 images, match with other 0-0 images
    # For battled images, match with same rating

    # Try to find opponent with:
    # 1. Same rating as kept image
    # 2. Different character name (preferred)

    # First pass: same rating + different character
    same_rating_diff_char = [
        c for c in candidates
        if _get_rating(all_stats[c['path']]) == kept_rating
        and c['name'] != kept_image['name']
    ]
    logger.debug(f"Same rating + diff char: {len(same_rating_diff_char)} candidates")
    if same_rating_diff_char:
        opponent = random.choice(same_rating_diff_char)
        opp_stats = all_stats[opponent['path']]
        logger.info(f"=== MATCHUP WITH KEPT: {kept_image['name']} ({kept_rating[0]}-{kept_rating[1]}) vs {opponent['name']} ({opp_stats['wins']}-{opp_stats['losses']}) ===")
        return (kept_image, opponent)

    # Second pass: same rating + same character (if no other option)
    same_rating_same_char = [
        c for c in candidates
        if _get_rating(all_stats[c['path']]) == kept_rating
    ]
    logger.debug(f"Same rating + same char: {len(same_rating_same_char)} candidates")
    if same_rating_same_char:
        opponent = random.choice(same_rating_same_char)
        opp_stats = all_stats[opponent['path']]
        logger.info(f"=== MATCHUP WITH KEPT (same char): {kept_image['name']} ({kept_rating[0]}-{kept_rating[1]}) vs {opponent['name']} ({opp_stats['wins']}-{opp_stats['losses']}) ===")
        return (kept_image, opponent)

    # No same rating match available - return None to trigger regular matchup
    logger.warning(f"No same rating match for kept image (rating={kept_rating[0]}-{kept_rating[1]}), falling back to regular matchup")
    return None


def get_scope_options(
    scope_universe: Optional[str] = None,
    scope_ip: Optional[str] = None,
    scope_group: Optional[str] = None,
    scope_character: Optional[str] = None,
    scope_source: Optional[str] = None
) -> Dict:
    """
    Get available options for scope dropdowns (cascading).

    Returns dict with available options at each level, plus metadata:
    - has_groups: Whether the selected IP uses group organization
    """
    index = get_index()

    result = {
        'universes': index.get_universes(),
        'ips': index.get_ips(scope_universe),
        'groups': [],
        'characters': [],
        'sources': [],
        'variants': [],
        'variant_groups': [],
        'has_groups': False  # Default to no groups
    }

    if scope_ip:
        result['groups'] = index.get_groups(scope_ip)
        result['has_groups'] = index.has_groups(scope_ip)
        result['sources'] = index.get_sources(scope_ip)
        result['characters'] = index.get_characters(scope_ip)

        # Narrow down based on filters
        if scope_group:
            result['characters'] = index.get_characters(scope_ip, scope_group)
            result['sources'] = index.get_sources(scope_ip, scope_group)

        if scope_character:
            result['sources'] = index.get_sources(scope_ip, scope_group, scope_character)

        # Get variants and variant_groups based on current filters
        result['variants'] = index.get_variants(
            scope_ip, scope_group, scope_character, scope_source
        )
        result['variant_groups'] = index.get_variant_groups(
            scope_ip, scope_group, scope_character, scope_source
        )

    return result


def get_available_count(
    scope_level: str,
    scope_ip: str,
    scope_group: Optional[str] = None,
    scope_character: Optional[str] = None,
    scope_source: Optional[str] = None,
    scope_variant: Optional[str] = None,
    match_source: bool = False,
    match_variant: bool = False,
    scope_universe: Optional[str] = None
) -> Dict:
    """
    Get count of available images for a given scope.

    Returns dict with total count and whether matchup is possible.
    """
    index = get_index()

    candidates = _get_scope_candidates(
        index, scope_level, scope_ip, scope_group,
        scope_character, scope_source, scope_variant, scope_universe
    )

    total = len(candidates)

    # Check if matchup possible with constraints
    can_match = False
    if total >= 2:
        if match_source or match_variant:
            matchup = _get_constrained_matchup(candidates, match_source, match_variant)
            can_match = matchup is not None
        else:
            can_match = True

    return {
        'total': total,
        'can_match': can_match
    }
