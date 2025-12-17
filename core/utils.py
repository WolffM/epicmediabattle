"""
Core utility functions - URL processing and general-purpose utilities.
These are shared across extractors and other modules.
"""

import json
import os
import re
from typing import Dict, List, Optional, Tuple
from urllib.parse import quote, unquote, urljoin

# =============================================================================
# Path Utilities
# =============================================================================

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INPUT_DIR = os.path.join(BASE_DIR, "Input")
OUTPUT_DIR = os.path.join(BASE_DIR, "Output")

# Default group name for IPs without explicit groups (flat character lists)
# This allows the system to work uniformly while supporting both grouped and flat IPs
DEFAULT_GROUP = "_default"

# Load IP sources from JSON file in Input folder
_ip_sources_path = os.path.join(INPUT_DIR, "ip_sources.json")
with open(_ip_sources_path, encoding="utf-8") as f:
    IP_SOURCES = json.load(f)


def reload_ip_sources():
    """
    Reload IP_SOURCES from disk.

    Call this after modifying ip_sources.json to ensure the global
    is updated. Any caches that depend on IP_SOURCES should be cleared
    after calling this function.
    """
    global IP_SOURCES
    with open(_ip_sources_path, encoding="utf-8") as f:
        IP_SOURCES = json.load(f)


# =============================================================================
# Universe/IP Hierarchy Helpers
# =============================================================================


def get_universes() -> List[str]:
    """Get list of all universe names."""
    return list(IP_SOURCES.keys())


def get_ips_for_universe(universe: str) -> List[str]:
    """Get list of IP names within a universe."""
    if universe not in IP_SOURCES:
        return []
    return list(IP_SOURCES[universe].keys())


def get_all_ips() -> List[Tuple[str, str]]:
    """
    Get all (universe, ip) tuples across all universes.

    Returns:
        List of (universe, ip) tuples
    """
    result = []
    for universe in IP_SOURCES:
        for ip in IP_SOURCES[universe]:
            result.append((universe, ip))
    return result


def resolve_ip_alias(ip: str) -> Tuple[str, Optional[str]]:
    """
    Resolve an IP alias to its canonical name and universe.

    If the IP is an alias defined in ip_aliases, returns the canonical name.
    Otherwise returns the original IP name.

    Args:
        ip: IP name or alias to resolve

    Returns:
        Tuple of (canonical_ip_name, universe) - universe may be None if not found
    """
    # First check direct match
    for universe, ips in IP_SOURCES.items():
        if ip in ips:
            return ip, universe

    # Check aliases
    for universe, ips in IP_SOURCES.items():
        for canonical_ip, config in ips.items():
            aliases = config.get("ip_aliases", [])
            if ip in aliases:
                return canonical_ip, universe

    # Not found - return original
    return ip, None


def get_universe_for_ip(ip: str) -> Optional[str]:
    """
    Find which universe contains a given IP (or its alias).

    Args:
        ip: IP name to search for

    Returns:
        Universe name or None if not found
    """
    _, universe = resolve_ip_alias(ip)
    return universe


def get_ip_config(ip: str, universe: Optional[str] = None) -> Optional[Dict]:
    """
    Get the configuration dict for an IP.

    Supports IP aliases - if ip matches an alias, returns the canonical config.

    Args:
        ip: IP name (or alias)
        universe: Universe name (optional, will search if not provided)

    Returns:
        IP configuration dict or None if not found
    """
    # Resolve alias first
    canonical_ip, resolved_universe = resolve_ip_alias(ip)

    if universe:
        if universe in IP_SOURCES and canonical_ip in IP_SOURCES[universe]:
            return IP_SOURCES[universe][canonical_ip]
        return None

    if resolved_universe:
        return IP_SOURCES[resolved_universe][canonical_ip]
    return None


def _get_ip_data(ip: str) -> Dict:
    """
    Internal helper to get IP data, searching across universes.

    Raises ValueError if IP not found.
    """
    config = get_ip_config(ip)
    if config is None:
        raise ValueError(f"No configuration found for IP: {ip}")
    return config


# =============================================================================
# Path Utilities (Updated for hierarchy)
# =============================================================================


def get_input_file(ip: str) -> str:
    """Get the input JSON file path for a given IP."""
    return os.path.join(INPUT_DIR, f"{ip}_female_characters.json")


def get_ip_output_dir(ip: str, universe: Optional[str] = None) -> str:
    """
    Get the IP-level output directory (where output.json lives).

    Resolves IP aliases to canonical names for consistent directory structure.

    Args:
        ip: IP name (or alias)
        universe: Universe name (optional, will be looked up if not provided)

    Returns:
        Path to IP output directory (e.g., Output/hoyoverse/genshin_impact)
    """
    # Resolve alias to canonical name
    canonical_ip, resolved_universe = resolve_ip_alias(ip)
    if universe is None:
        universe = resolved_universe
    if universe:
        return os.path.join(OUTPUT_DIR, universe, canonical_ip)
    # Fallback for backward compatibility
    return os.path.join(OUTPUT_DIR, canonical_ip)


def get_output_dir(ip: str, group=None, universe: Optional[str] = None) -> str:
    """
    Get the output directory for a given IP and group.

    Resolves IP aliases to canonical names for consistent directory structure.

    Args:
        ip: IP name (or alias)
        group: Group/generation identifier (None or empty uses DEFAULT_GROUP)
        universe: Universe name (optional, will be looked up if not provided)

    Returns:
        Path to output directory
    """
    # Resolve alias to canonical name
    canonical_ip, resolved_universe = resolve_ip_alias(ip)
    if universe is None:
        universe = resolved_universe

    # Use default group if none provided
    group_str = str(group) if group else DEFAULT_GROUP

    if universe:
        return os.path.join(OUTPUT_DIR, universe, canonical_ip, group_str)
    # Fallback for backward compatibility
    return os.path.join(OUTPUT_DIR, ip, group_str)


# =============================================================================
# URL Processing Utilities
# =============================================================================

def clean_fandom_url(url: str) -> Optional[str]:
    """
    Clean Fandom image URL to get full resolution.
    Remove /revision/... and /scale-to-width-down/... parameters.

    Args:
        url: Raw Fandom image URL

    Returns:
        Cleaned URL or None if invalid
    """
    if not url:
        return None

    # Remove revision and scaling parameters
    url = re.sub(r'/revision/[^/]+', '', url)
    url = re.sub(r'/scale-to-width-down/\d+', '', url)
    url = re.sub(r'/window-crop/.*$', '', url)

    # Ensure https
    if url.startswith('//'):
        url = 'https:' + url

    return url if url.startswith('http') else None


def resolve_bulbapedia_thumbnail(src: str, base_url: str = 'https://bulbapedia.bulbagarden.net') -> Optional[str]:
    """
    Resolve Bulbapedia thumbnail URL to full image URL.

    Thumbnails look like: /w/thumb.php?f=...&w=150
    Or: //archives.bulbagarden.net/media/thumb/.../150px-...

    Args:
        src: Image source URL (may be thumbnail)
        base_url: Base URL for relative paths

    Returns:
        Full resolution image URL or None
    """
    if 'thumb.php' in src:
        # Extract filename from thumb.php URL
        match = re.search(r'f=([^&]+)', src)
        if match:
            filename = unquote(match.group(1))
            return f"https://archives.bulbagarden.net/media/upload/{filename}"

    elif '/thumb/' in src:
        # Convert thumbnail path to full path
        # Remove /thumb/ and the size suffix (e.g., /150px-...)
        full_url = re.sub(r'/thumb/(.+)/\d+px-[^/]+$', r'/\1', src)
        if not full_url.startswith('http'):
            full_url = 'https:' + full_url if full_url.startswith('//') else urljoin(base_url, full_url)
        return full_url

    elif src.startswith('//'):
        return 'https:' + src
    elif src.startswith('/'):
        return urljoin(base_url, src)

    return src if src.startswith('http') else None


def get_fandom_image_by_filename(filename: str) -> str:
    """
    Construct Fandom image URL from filename.

    Args:
        filename: Image filename

    Returns:
        Constructed URL (may not be valid)
    """
    filename_clean = filename.replace(' ', '_')
    return f"https://static.wikia.nocookie.net/pokemon/images/{filename_clean}"


def is_likely_character_image(url: str, search_name: str = '') -> bool:
    """
    Heuristic to determine if URL is likely a character image.
    Filter out icons, logos, UI elements, etc.

    Args:
        url: Image URL
        search_name: Character search name (optional, for better matching)

    Returns:
        True if likely a character image
    """
    url_lower = url.lower()

    # Exclude patterns - small images and UI elements
    exclude_patterns = [
        'icon', 'logo', 'button', 'sprite', 'symbol',
        'bag_', 'item_', 'menu_', 'ui_', 'nav_',
        'flag', 'badge', 'type_', 'category',
        '15px', '20px', '25px', '30px',  # Tiny images
    ]

    for pattern in exclude_patterns:
        if pattern in url_lower:
            return False

    # Include patterns (character-related)
    include_patterns = [
        'artwork', 'art.png', 'art.jpg',
        'ruby', 'sapphire', 'emerald', 'diamond', 'pearl',
        'sun', 'moon', 'sword', 'shield',
        'trainer', 'character', 'anime',
        'oras', 'hgss', 'bw', 'xy', 'swsh',
    ]

    if search_name:
        include_patterns.append(search_name.lower().replace('_', ''))

    for pattern in include_patterns:
        if pattern in url_lower:
            return True

    # Default: accept if it's a reasonably sized image path
    return '.png' in url_lower or '.jpg' in url_lower


def build_booru_search_url(tags: str, base_url: str = "https://example.booru.org") -> str:
    """
    Build booru search URL from tags string.

    Args:
        tags: Search tags
        base_url: Base URL of the booru site

    Returns:
        Full search URL
    """
    encoded_tags = quote(tags)
    return f"{base_url}/index.php?page=post&s=list&tags={encoded_tags}"


def count_images_by_variant_source(entry: Dict) -> Dict[Tuple[str, str], int]:
    """
    Count images in an entry by (variant, source) combination.
    Single-pass efficient counting.

    Args:
        entry: Character entry with 'images' list

    Returns:
        Dict mapping (variant, source) tuples to counts
    """
    counts: Dict[tuple, int] = {}
    for img in entry.get('images', []):
        variant = img.get('variant', 'base')
        src = img['source']
        key = (variant, src)
        counts[key] = counts.get(key, 0) + 1
    return counts


# =============================================================================
# IP Source Configuration Helpers
# =============================================================================

def get_sources(ip: str) -> List[dict]:
    """Get the prioritized list of sources for a given IP."""
    ip_data = _get_ip_data(ip)
    sources = ip_data.get("sources", [])
    return sorted(sources, key=lambda x: x["priority"])


def get_source_variants(source: dict, num_variants: int = 1) -> List[str]:
    """
    Get the name variant suffixes for a specific source (wiki-style sources).

    Args:
        source: Source configuration dictionary
        num_variants: How many variants to return

    Returns:
        List of suffix strings to append to character names
    """
    variants = source.get("variants", [""])
    return variants[:num_variants]


def get_tag_variants(source: dict, num_variants: Optional[int] = None) -> List[dict]:
    """
    Get the tag variants for a tag-based source (booru sites).

    Args:
        source: Source configuration dictionary
        num_variants: How many variants to return (None = all)

    Returns:
        List of tag variant dicts with 'variant_name' and 'tags' keys
    """
    tag_variants = source.get("tag_variants", [])
    if num_variants is None:
        return tag_variants
    return tag_variants[:num_variants]


def has_tag_variants(source: dict) -> bool:
    """Check if a source uses tag-based variants."""
    return "tag_variants" in source and len(source["tag_variants"]) > 0


def get_gen_aliases(ip: str) -> dict:
    """Get generation aliases for an IP."""
    config = get_ip_config(ip)
    if config is None:
        return {}
    return config.get("gen_aliases", {})


def get_ip_aliases(ip: str) -> List[str]:
    """
    Get IP name aliases for tag searching.

    Some IPs have multiple tag names on booru sites (e.g., afk_arena, afk_journey).
    This returns a list of aliases to try when searching.

    Args:
        ip: IP name

    Returns:
        List of IP aliases (including the IP name itself if no aliases defined)
    """
    config = get_ip_config(ip)
    if config is None:
        return [ip]
    aliases = config.get("ip_aliases", [])
    if not aliases:
        return [ip]
    return aliases


def get_variant_groups(ip: str) -> dict:
    """
    Get variant groups for an IP.
    Calculated dynamically from tag_variants in sources.

    Returns:
        Dict mapping group name -> list of variant names
    """
    config = get_ip_config(ip)
    if config is None:
        return {}

    groups: Dict[str, List[str]] = {}
    for source in config.get("sources", []):
        for tv in source.get("tag_variants", []):
            group = tv.get("variant_group")
            variant = tv.get("variant_name")
            if group and variant:
                if group not in groups:
                    groups[group] = []
                if variant not in groups[group]:
                    groups[group].append(variant)
    return groups


def get_variant_to_group(ip: str) -> dict:
    """
    Build reverse lookup: variant_name -> group_name for an IP.
    Calculated dynamically from tag_variants in sources.
    """
    config = get_ip_config(ip)
    if config is None:
        return {}

    result = {}
    for source in config.get("sources", []):
        for tv in source.get("tag_variants", []):
            variant = tv.get("variant_name")
            group = tv.get("variant_group")
            if variant and group:
                result[variant] = group
    return result


def get_characters(ip: str) -> List[dict]:
    """
    Get the character data for a given IP.

    Returns:
        List of group dictionaries with 'group', 'retired', and 'contestants' keys.
        For flat character lists, returns a single group with group=DEFAULT_GROUP.
    """
    ip_data = _get_ip_data(ip)
    characters = ip_data.get("characters", [])

    # If no characters defined, return empty list
    if not characters:
        return []

    # Check if it's a flat list (list of strings) or grouped (list of dicts)
    if characters and isinstance(characters[0], str):
        # Flat list - wrap in default group structure
        return [{
            "group": DEFAULT_GROUP,
            "contestants": characters,
            "retired": []
        }]

    return characters


def ip_has_groups(ip: str) -> bool:
    """
    Check if an IP uses group organization or flat character list.

    Returns:
        True if IP has explicit groups, False if flat list or uses DEFAULT_GROUP
    """
    ip_data = _get_ip_data(ip)
    characters = ip_data.get("characters", [])

    if not characters:
        return False

    # Flat list = no groups
    if isinstance(characters[0], str):
        return False

    # Check if it's the default group
    if len(characters) == 1 and characters[0].get("group") == DEFAULT_GROUP:
        return False

    return True


def normalize_gen(gen_value, ip: str = "pokemon", compact: bool = False) -> str:
    """
    Normalize a generation/group value for display.
    Converts numeric gens to "Gen X" format, uses aliases for special groups.

    Args:
        gen_value: The generation/group value (int, str, etc.)
        ip: The IP to look up aliases for
        compact: If True, omit "Gen " prefix for numeric values (use in columns already labeled "Gen")

    Returns:
        Formatted string for display (e.g., "Gen 1" or "1", "Archeus", "Horizons")
    """
    gen_str = str(gen_value)
    aliases = get_gen_aliases(ip)

    # Check if it's a special alias (reverse lookup)
    for name, alias_val in aliases.items():
        if gen_str == alias_val or gen_str.lower() == name.lower():
            return name.title()

    # If it's a number, format as "Gen X" or just "X" in compact mode
    if gen_str.isdigit():
        return gen_str if compact else f"Gen {gen_str}"

    # Otherwise return as-is with title case
    return gen_str.title()


# Backwards compatibility - expose pokemon-specific values at module level
GEN_ALIASES = get_gen_aliases("pokemon")
VARIANT_GROUPS = get_variant_groups("pokemon")
