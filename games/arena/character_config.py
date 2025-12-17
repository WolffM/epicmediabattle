"""
Character configuration loader for arena.
Handles loading retired characters from ip_sources.json.
"""

import sys
from pathlib import Path
from typing import Dict, Set

# Add parent paths for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from core.utils import get_characters


def load_character_config(ip: str = "pokemon") -> Dict:
    """
    Load character configuration from IP_SOURCES.

    Returns dict with:
        - 'retired': Dict[str, Set[str]] mapping group -> set of retired character names
        - 'contestants': Dict[str, Set[str]] mapping group -> set of active character names
    """
    try:
        data = get_characters(ip)
    except ValueError:
        return {'retired': {}, 'contestants': {}}

    retired = {}
    contestants = {}

    for group_entry in data:
        group = str(group_entry.get('group', ''))
        retired[group] = set(group_entry.get('retired', []))
        contestants[group] = set(group_entry.get('contestants', []))

    return {
        'retired': retired,
        'contestants': contestants
    }


def get_retired_characters(ip: str = "pokemon") -> Dict[str, Set[str]]:
    """
    Get retired characters for an IP.

    Returns dict mapping group -> set of retired character names.
    """
    config = load_character_config(ip)
    return config['retired']


def is_character_retired(name: str, group_name: str, ip: str = "pokemon") -> bool:
    """
    Check if a character is retired.

    Args:
        name: Character name
        group_name: Group name
        ip: IP name

    Returns:
        True if character is in the retired list for their group
    """
    retired = get_retired_characters(ip)
    group_retired = retired.get(str(group_name), set())
    return name in group_retired


def get_all_retired_characters(ip: str = "pokemon") -> Set[str]:
    """
    Get all retired character names across all groups.

    Returns set of all retired character names.
    """
    retired = get_retired_characters(ip)
    all_retired = set()
    for group_retired in retired.values():
        all_retired.update(group_retired)
    return all_retired


# Cache for retired characters
_retired_cache: Dict[str, Dict[str, Set[str]]] = {}


def get_retired_characters_cached(ip: str = "pokemon") -> Dict[str, Set[str]]:
    """
    Get retired characters with caching.
    """
    global _retired_cache
    if ip not in _retired_cache:
        _retired_cache[ip] = get_retired_characters(ip)
    return _retired_cache[ip]


def clear_retired_cache():
    """Clear the retired characters cache."""
    global _retired_cache
    _retired_cache = {}
