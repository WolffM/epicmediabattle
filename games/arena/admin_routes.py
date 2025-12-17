"""
Admin API endpoints for Arena application.
These endpoints provide analysis and configuration management.
"""

import json
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException

from core.utils import reload_ip_sources
from games.arena import matcher
from games.arena.character_config import clear_retired_cache

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/variant-stats")
async def get_admin_variant_stats(
    ip: str = "pokemon",
    source: Optional[str] = None,
    variant_group: Optional[str] = None
):
    """Get comprehensive variant statistics for admin analysis."""
    from games.arena.analysis import get_variant_statistics

    stats = get_variant_statistics(ip)

    # Apply filters
    if source:
        stats = [s for s in stats if s.get('source') == source]
    if variant_group:
        stats = [s for s in stats if s.get('variant_group') == variant_group]

    return stats


@router.get("/character-stats")
async def get_admin_character_stats(
    ip: str = "pokemon",
    gen: Optional[str] = None
):
    """Get character statistics including missing variants."""
    from games.arena.analysis import get_character_statistics

    stats = get_character_statistics(ip, gen)
    return stats


@router.get("/coverage-matrix")
async def get_admin_coverage_matrix(ip: str = "pokemon"):
    """Get character × variant coverage heatmap data."""
    from games.arena.analysis import get_coverage_matrix

    matrix_data = get_coverage_matrix(ip)
    return matrix_data


@router.get("/deprecation-candidates")
async def get_admin_deprecation_candidates(ip: str = "pokemon"):
    """Get auto-flagged deprecation/retirement candidates."""
    from games.arena.analysis import get_deprecation_candidates

    candidates = get_deprecation_candidates(ip)
    return candidates


@router.get("/best-images")
async def get_admin_best_images(ip: str = "pokemon", limit: int = 5):
    """Get top performing images per variant."""
    from games.arena.analysis import get_best_images_per_variant

    best_images = get_best_images_per_variant(ip, limit)
    return best_images


@router.post("/deprecate-variant")
async def deprecate_variant(
    variant_name: str,
    source_name: str,
    ip: str = "pokemon",
    universe: str = "nintendo"
):
    """Move a variant to deprecated_tag_variants in ip_sources.json."""
    ip_sources_path = Path("Input/ip_sources.json")

    # Read current config
    with open(ip_sources_path, encoding='utf-8') as f:
        ip_sources = json.load(f)

    if universe not in ip_sources:
        raise HTTPException(status_code=404, detail=f"Universe '{universe}' not found")

    if ip not in ip_sources[universe]:
        raise HTTPException(status_code=404, detail=f"IP '{ip}' not found in universe '{universe}'")

    # Find the source
    source = None
    for src in ip_sources[universe][ip]['sources']:
        if src['name'] == source_name:
            source = src
            break

    if not source:
        raise HTTPException(status_code=404, detail=f"Source '{source_name}' not found")

    # Find the variant in tag_variants
    variant_to_move = None
    for i, tv in enumerate(source.get('tag_variants', [])):
        if tv['variant_name'] == variant_name:
            variant_to_move = source['tag_variants'].pop(i)
            break

    if not variant_to_move:
        raise HTTPException(status_code=404, detail=f"Variant '{variant_name}' not found in {source_name}")

    # Add to deprecated_tag_variants
    if 'deprecated_tag_variants' not in source:
        source['deprecated_tag_variants'] = []
    source['deprecated_tag_variants'].append(variant_to_move)

    # Save updated config
    with open(ip_sources_path, 'w', encoding='utf-8') as f:
        json.dump(ip_sources, f, indent=4, ensure_ascii=False)

    # Refresh global IP_SOURCES first, then clear dependent caches
    reload_ip_sources()
    matcher.clear_deprecated_cache()

    return {"success": True, "message": f"Variant '{variant_name}' deprecated in {source_name}"}


@router.post("/retire-character")
async def retire_character(
    character_name: str,
    group: str,
    ip: str = "pokemon",
    universe: str = "nintendo"
):
    """Move a character to the retired list in ip_sources.json."""
    ip_sources_path = Path("Input/ip_sources.json")

    # Read current config
    with open(ip_sources_path, encoding='utf-8') as f:
        ip_sources = json.load(f)

    if universe not in ip_sources:
        raise HTTPException(status_code=404, detail=f"Universe '{universe}' not found")

    if ip not in ip_sources[universe]:
        raise HTTPException(status_code=404, detail=f"IP '{ip}' not found in universe '{universe}'")

    # Find the group in characters
    group_data = None
    for grp in ip_sources[universe][ip]['characters']:
        if str(grp['group']) == str(group):
            group_data = grp
            break

    if not group_data:
        raise HTTPException(status_code=404, detail=f"Group '{group}' not found")

    # Remove from contestants
    if character_name not in group_data.get('contestants', []):
        raise HTTPException(status_code=404, detail=f"Character '{character_name}' not found in group {group}")

    group_data['contestants'].remove(character_name)

    # Add to retired
    if 'retired' not in group_data:
        group_data['retired'] = []
    if character_name not in group_data['retired']:
        group_data['retired'].append(character_name)

    # Save updated config
    with open(ip_sources_path, 'w', encoding='utf-8') as f:
        json.dump(ip_sources, f, indent=4, ensure_ascii=False)

    # Refresh global IP_SOURCES first, then clear dependent caches
    reload_ip_sources()
    clear_retired_cache()

    return {"success": True, "message": f"Character '{character_name}' retired from group {group}"}
