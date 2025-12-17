"""
Extractor utility functions - character loading, filename handling, and output logging.
"""

import json
import os
import re
import sys
from datetime import datetime
from typing import Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core import config

# =============================================================================
# Variant Label Helpers
# =============================================================================

def extract_variant_label(variant_suffix: str) -> str:
    """
    Convert variant suffix to variant label.

    Args:
        variant_suffix: Suffix like '_(anime)', '_(game)', or empty string

    Returns:
        Label: 'anime', 'game', or 'base'
    """
    if variant_suffix == '_(anime)':
        return 'anime'
    elif variant_suffix == '_(game)':
        return 'game'
    return 'base'


def extract_variant_from_filename(filename: str) -> str:
    """
    Extract variant from filename pattern: Name-source-variant-count.ext

    Args:
        filename: Image filename to parse

    Returns:
        Variant name or 'base' if no variant found
    """
    # Pattern: Name-source-variant-count.ext
    match = re.match(r'^.+-[a-z0-9]{5,8}-(.+)-\d+\.[a-z]+$', filename, re.IGNORECASE)
    if match:
        return match.group(1)
    return 'base'


# =============================================================================
# Character Loading
# =============================================================================

def load_characters(ip: str) -> List[Dict[str, any]]:
    """
    Load and flatten character data from IP_SOURCES config.

    Args:
        ip: The IP name (e.g., 'pokemon')

    Returns:
        List of character dictionaries with name, group, and search_name
    """
    data = config.get_characters(ip)

    characters = []
    for group_data in data:
        group = group_data['group']
        for contestant in group_data['contestants']:
            characters.append({
                'name': contestant,
                'group': group,
                'search_name': clean_character_name(contestant)
            })

    return characters


def clean_character_name(name: str) -> str:
    """
    Clean character name for search queries.
    Converts underscores to spaces while preserving the original casing.

    Args:
        name: Original character name (e.g., "Player's_Mom")

    Returns:
        Cleaned name for search (e.g., "Player's Mom")
    """
    return name.replace('_', ' ')


def sanitize_filename(name: str) -> str:
    """
    Sanitize character name for use as filename.
    Removes or replaces characters that are invalid in filenames.
    Preserves underscores for names with spaces.

    Args:
        name: Character name

    Returns:
        Safe filename (without extension)
    """
    # Replace invalid filename characters
    name = re.sub(r'[<>:"/\\|?*]', '', name)
    # Replace spaces with underscores (preserve existing underscores)
    name = name.replace(' ', '_')
    return name


def generate_image_filename(
    name: str,
    source_short: str,
    count: int,
    extension: str,
    variant_name: str = None
) -> str:
    """
    Generate filename in format: {name}-{source5}-{variant}-{count}.{ext}
    or {name}-{source5}-{count}.{ext} if no variant specified.

    Args:
        name: Character name (will be sanitized)
        source_short: Short source name (5 chars, e.g., 'bulba', 'dbwiki')
        count: Image count for this variant (1-indexed)
        extension: File extension including dot (e.g., '.png')
        variant_name: Optional variant name (e.g., 'super_saiyan', 'base')

    Returns:
        Formatted filename (e.g., 'Goku-dbwiki-super_saiyan-1.png' or 'Vegeta-bulba-1.png')
    """
    safe_name = sanitize_filename(name)
    if variant_name:
        safe_variant = sanitize_filename(variant_name)
        return f"{safe_name}-{source_short}-{safe_variant}-{count}{extension}"
    return f"{safe_name}-{source_short}-{count}{extension}"


def ensure_directory(directory: str) -> None:
    """
    Create directory if it doesn't exist.

    Args:
        directory: Path to directory
    """
    os.makedirs(directory, exist_ok=True)


def log_result(log_file: str, character: Dict, message: str, verbose: bool = True) -> None:
    """
    Log a message to the text log file.

    Args:
        log_file: Path to log file
        character: Character dictionary with name and group
        message: Message to log
        verbose: Whether to print to console
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"[{timestamp}] Group {character['group']} - {character['name']} - {message}\n"

    with open(log_file, 'a', encoding='utf-8') as f:
        f.write(log_entry)

    if verbose:
        print(log_entry.strip())


def log_fetch_event(
    log_file: str,
    character: Dict,
    source: str,
    variant: str,
    event_type: str,
    details: str,
    url: Optional[str] = None,
    verbose: bool = False
) -> None:
    """
    Log a detailed fetch event for debugging.

    Args:
        log_file: Path to log file
        character: Character dictionary with name and group
        source: Source name
        variant: Variant name (e.g., 'AIBest', 'base')
        event_type: Type of event - SUCCESS, FAIL, SKIP, ERROR, SEARCH, NO_RESULTS
        details: Human-readable details
        url: Optional URL involved
        verbose: Whether to print to console
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    char_name = character.get('name', 'unknown')
    group = character.get('group', 'unknown')

    log_entry = f"[{timestamp}] [{event_type}] {group}/{char_name} | {source}/{variant} | {details}"
    if url:
        log_entry += f" | URL: {url}"
    log_entry += "\n"

    with open(log_file, 'a', encoding='utf-8') as f:
        f.write(log_entry)

    if verbose:
        print(log_entry.strip())


def get_image_extension(content_type: str) -> Optional[str]:
    """
    Get file extension from content type.
    Only returns extensions for supported formats.

    Args:
        content_type: HTTP Content-Type header value

    Returns:
        File extension including the dot (e.g., '.png') or None if unsupported
    """
    content_type_map = {
        'image/png': '.png',
        'image/jpeg': '.jpg',
        'image/jpg': '.jpg',
        'image/webp': '.webp',
    }

    # Extract just the type part (ignore charset, etc.)
    if ';' in content_type:
        content_type = content_type.split(';')[0].strip()

    return content_type_map.get(content_type.lower())


def get_extension_from_url(url: str) -> Optional[str]:
    """
    Extract file extension from URL.
    Only returns extensions for supported formats.

    Args:
        url: Image URL

    Returns:
        File extension including the dot (e.g., '.png') or None if unsupported
    """
    url_lower = url.lower()
    for ext in config.SUPPORTED_IMAGE_FORMATS:
        if ext in url_lower:
            return ext
    return None


def is_url_valid_image(url: str) -> bool:
    """
    Check if URL points to a supported image format.

    Args:
        url: Image URL

    Returns:
        True if URL ends with a supported image extension
    """
    url_lower = url.lower()
    return any(ext in url_lower for ext in config.SUPPORTED_IMAGE_FORMATS)


# =============================================================================
# Output Log Functions (multi-image structure)
# =============================================================================

def load_output_log(output_log_path: str) -> Dict[str, Dict]:
    """
    Load the output.json log file.

    Args:
        output_log_path: Path to output.json

    Returns:
        Dictionary mapping character keys to their results
        Key format: "group{X}_{character_name}"
    """
    if not os.path.exists(output_log_path):
        return {}

    try:
        with open(output_log_path, encoding='utf-8') as f:
            data = json.load(f)
            return {entry['key']: entry for entry in data.get('results', [])}
    except Exception as e:
        print(f"Warning: Could not load output log: {e}")
        return {}


def get_all_downloaded_urls(output_log: Dict) -> set:
    """
    Get all URLs that have been downloaded across ALL characters.

    This is used to prevent duplicate downloads when the same image
    appears in search results for multiple characters (e.g., group images).

    Args:
        output_log: Dictionary mapping character keys to their entries

    Returns:
        Set of all URLs that have been downloaded
    """
    all_urls = set()
    for entry in output_log.values():
        for img in entry.get('images', []):
            if img.get('url'):
                all_urls.add(img['url'])
    return all_urls


def save_output_log(output_log_path: str, results: List[Dict]) -> None:
    """
    Save results to output.json log file.

    Args:
        output_log_path: Path to output.json
        results: List of result dictionaries
    """
    # Count statistics
    total_images = sum(len(r.get('images', [])) for r in results)
    chars_complete = sum(1 for r in results if r.get('result') == 'success')
    chars_partial = sum(1 for r in results if r.get('result') == 'partial')
    chars_failed = sum(1 for r in results if r.get('result') == 'fail')

    output_data = {
        'timestamp': datetime.now().isoformat(),
        'total_characters': len(results),
        'total_images': total_images,
        'characters_complete': chars_complete,
        'characters_partial': chars_partial,
        'characters_failed': chars_failed,
        'results': results
    }

    with open(output_log_path, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)


def create_character_entry(character: Dict, target: Dict) -> Dict:
    """
    Create a new character entry for the output log.

    Args:
        character: Character dictionary with name and group
        target: Target configuration dict with images_per_source, num_sources, name_variants

    Returns:
        New character entry dictionary
    """
    key = f"group{character['group']}_{character['name']}"

    return {
        'key': key,
        'name': character['name'],
        'group': character['group'],
        'target': target.copy(),
        'images': [],
        'sources_completed': [],
        'result': 'fail',
        'timestamp': datetime.now().isoformat()
    }


def add_image_to_entry(entry: Dict, image_info: Dict) -> None:
    """
    Add an image to a character entry.

    Args:
        entry: Character entry dictionary
        image_info: Image info dict with path, source, url, page_url, variant
    """
    entry['images'].append(image_info)
    entry['timestamp'] = datetime.now().isoformat()

    # Update sources_completed
    source = image_info['source']
    if source not in entry['sources_completed']:
        entry['sources_completed'].append(source)

    # Update result status
    _update_entry_result(entry)


def _update_entry_result(entry: Dict) -> None:
    """
    Update the result status of a character entry based on targets.

    Target is: images_per_source × num_sources × name_variants
    Each variant should independently get images_per_source from num_sources.

    Args:
        entry: Character entry dictionary
    """
    target = entry.get('target', {})
    images_per_source = target.get('images_per_source', 1)
    num_sources = target.get('num_sources', 1)
    name_variants = target.get('name_variants', 1)

    # Count images per (variant, source) combination
    variant_source_counts = {}
    for img in entry.get('images', []):
        variant = img.get('variant', 'base')
        src = img['source']
        key = (variant, src)
        variant_source_counts[key] = variant_source_counts.get(key, 0) + 1

    # For each variant, count how many sources meet the target
    variant_labels = ['base', 'anime', 'game'][:name_variants]
    variants_complete = 0

    for variant in variant_labels:
        sources_meeting_target = 0
        for src in {src for (v, src) in variant_source_counts if v == variant}:
            if variant_source_counts.get((variant, src), 0) >= images_per_source:
                sources_meeting_target += 1
        if sources_meeting_target >= num_sources:
            variants_complete += 1

    # Total target = all variants complete
    if variants_complete >= name_variants:
        entry['result'] = 'success'
    elif entry.get('images'):
        entry['result'] = 'partial'
    else:
        entry['result'] = 'fail'


def get_fetch_needs(
    entry: Dict,
    replace_mode: bool = True,
    available_sources: list = None,
    output_dir: str = None
) -> Dict:
    """
    Determine what still needs to be fetched for a character.

    Tracks needs per (variant, source) combination since total target is:
    images_per_source × num_sources × name_variants

    Args:
        entry: Character entry dictionary
        replace_mode: If True (default), only count images that exist on disk.
                      If False (getnew mode), count all logged images regardless of disk state.
        available_sources: List of source dicts (sorted by priority). Used to check if we need
                          images from the top priority sources.
        output_dir: Output directory path. Used to construct full paths from filenames.
                   Required when replace_mode is True and images use 'filename' (not 'path').

    Returns:
        Dict with:
            - needs_more: bool indicating if more fetching needed
            - variant_source_counts: dict mapping (variant, source) to count
            - existing_urls: set of already-fetched URLs (to avoid dupes)
            - variants_complete: list of variants that have met their targets
            - missing_variants: list of (variant, source) tuples that need replacement
    """
    target = entry.get('target', {})
    images_per_source = target.get('images_per_source', 1)
    num_sources = target.get('num_sources', 1)
    name_variants_count = target.get('name_variants', 1)

    # Count existing images per (variant, source) combination
    variant_source_counts = {}
    existing_urls = set()
    missing_variants = []  # Track which (variant, source) combos have missing files

    for img in entry.get('images', []):
        variant = img.get('variant', 'base')
        src = img['source']
        key = (variant, src)

        # Always track URLs to avoid re-downloading same image
        if img.get('url'):
            existing_urls.add(img['url'])

        # In replace mode, only count if file actually exists
        if replace_mode:
            # Support both 'filename' (new) and 'path' (legacy) formats
            path = img.get('path', '')
            if not path and img.get('filename') and output_dir:
                # Construct path from filename + output_dir
                path = os.path.join(output_dir, img['filename'])

            if path and os.path.exists(path):
                variant_source_counts[key] = variant_source_counts.get(key, 0) + 1
            else:
                # File is missing - needs replacement
                if key not in missing_variants:
                    missing_variants.append(key)
        else:
            # getnew mode - count all logged images
            variant_source_counts[key] = variant_source_counts.get(key, 0) + 1

    # Check which variants are complete
    variant_labels = ['base', 'anime', 'game'][:name_variants_count]
    variants_complete = []

    # Get the top priority source short names if available
    priority_sources = []
    if available_sources:
        priority_sources = [s['short_name'] for s in available_sources[:num_sources]]

    for variant in variant_labels:
        if priority_sources:
            # Check if we have images from the top priority sources
            sources_meeting_target = 0
            for src_short in priority_sources:
                if variant_source_counts.get((variant, src_short), 0) >= images_per_source:
                    sources_meeting_target += 1
            if sources_meeting_target >= num_sources:
                variants_complete.append(variant)
        else:
            # Legacy behavior: count any sources
            sources_meeting_target = 0
            for src in {src for (v, src) in variant_source_counts if v == variant}:
                if variant_source_counts.get((variant, src), 0) >= images_per_source:
                    sources_meeting_target += 1
            if sources_meeting_target >= num_sources:
                variants_complete.append(variant)

    # Need more if not all variants are complete
    needs_more = len(variants_complete) < name_variants_count

    return {
        'needs_more': needs_more,
        'variant_source_counts': variant_source_counts,
        'existing_urls': existing_urls,
        'variants_complete': variants_complete,
        'missing_variants': missing_variants
    }


# =============================================================================
# Summary Report
# =============================================================================

def generate_summary_report(results: List[Dict]) -> str:
    """
    Generate a summary report of fetch results.

    Args:
        results: List of character entry dictionaries

    Returns:
        Formatted summary string
    """
    total = len(results)
    complete = sum(1 for r in results if r.get('result') == 'success')
    partial = sum(1 for r in results if r.get('result') == 'partial')
    failed = sum(1 for r in results if r.get('result') == 'fail')
    total_images = sum(len(r.get('images', [])) for r in results)

    # Count images by source
    source_counts = {}
    for r in results:
        for img in r.get('images', []):
            src = img.get('source', 'unknown')
            source_counts[src] = source_counts.get(src, 0) + 1

    # Count images by variant
    variant_counts = {}
    for r in results:
        for img in r.get('images', []):
            variant = img.get('variant', 'base')
            variant_counts[variant] = variant_counts.get(variant, 0) + 1

    # Build report
    report_lines = [
        "\n" + "="*60,
        "IMAGE FETCH SUMMARY REPORT",
        "="*60,
        f"Total Characters: {total}",
        f"  - Complete: {complete} ({complete/total*100:.1f}%)" if total > 0 else "  - Complete: 0",
        f"  - Partial: {partial} ({partial/total*100:.1f}%)" if total > 0 else "  - Partial: 0",
        f"  - Failed: {failed} ({failed/total*100:.1f}%)" if total > 0 else "  - Failed: 0",
        f"Total Images Fetched: {total_images}",
        "",
        "Images by Source:",
    ]

    for source, count in sorted(source_counts.items(), key=lambda x: x[1], reverse=True):
        report_lines.append(f"  - {source}: {count} images")

    # Add variant breakdown if there are multiple variants
    if variant_counts and len(variant_counts) > 1:
        report_lines.append("")
        report_lines.append("Images by Variant:")
        for variant, count in sorted(variant_counts.items(), key=lambda x: x[1], reverse=True):
            report_lines.append(f"  - {variant}: {count} images")

    # List failed characters
    failed_chars = [r for r in results if r.get('result') == 'fail']
    if failed_chars:
        report_lines.append("\nFailed Characters (0 images):")
        for r in failed_chars[:20]:  # Limit to first 20
            report_lines.append(f"  - Group {r['group']}: {r['name']}")
        if len(failed_chars) > 20:
            report_lines.append(f"  ... and {len(failed_chars) - 20} more")

    # List partial characters
    partial_chars = [r for r in results if r.get('result') == 'partial']
    if partial_chars:
        report_lines.append("\nPartial Characters (some images missing):")
        for r in partial_chars[:10]:
            img_count = len(r.get('images', []))
            report_lines.append(f"  - Group {r['group']}: {r['name']} ({img_count} images)")
        if len(partial_chars) > 10:
            report_lines.append(f"  ... and {len(partial_chars) - 10} more")

    report_lines.append("="*60 + "\n")

    return "\n".join(report_lines)


# =============================================================================
# Image Validation and Purge
# =============================================================================

# Image magic bytes for validation
IMAGE_MAGIC_BYTES = {
    b'\xff\xd8\xff': 'jpg',      # JPEG
    b'\x89PNG\r\n\x1a\n': 'png', # PNG
    b'GIF87a': 'gif',            # GIF87a
    b'GIF89a': 'gif',            # GIF89a
    b'RIFF': 'webp',             # WebP (starts with RIFF, has WEBP at byte 8)
}


def is_valid_image(file_path: str) -> bool:
    """
    Check if a file is a valid image by examining its magic bytes.

    Args:
        file_path: Path to the image file

    Returns:
        True if the file appears to be a valid image, False otherwise
    """
    if not os.path.exists(file_path):
        return False

    try:
        with open(file_path, 'rb') as f:
            header = f.read(16)

        if len(header) < 3:
            return False

        # Check for HTML content (corrupted download)
        if header.startswith(b'<!DOCTYPE') or header.startswith(b'<html') or header.startswith(b'<HTML'):
            return False

        # Check JPEG
        if header[:3] == b'\xff\xd8\xff':
            return True

        # Check PNG
        if header[:8] == b'\x89PNG\r\n\x1a\n':
            return True

        # Check GIF
        if header[:6] in (b'GIF87a', b'GIF89a'):
            return True

        # Check WebP (RIFF....WEBP)
        if header[:4] == b'RIFF' and header[8:12] == b'WEBP':
            return True

        # Check BMP
        if header[:2] == b'BM':
            return True

        return False

    except OSError:
        return False


def purge_corrupted_images(ip: str, output_log_path: str, dry_run: bool = False) -> dict:
    """
    Scan all images for an IP and remove corrupted ones from disk and metadata.

    Corrupted images include:
    - Files that don't exist
    - Files with invalid image headers (e.g., HTML error pages saved as images)
    - Empty or truncated files

    Args:
        ip: IP name (e.g., 'genshin_impact')
        output_log_path: Path to the output.json file
        dry_run: If True, only report but don't delete

    Returns:
        Dict with purge statistics
    """
    stats = {
        'scanned': 0,
        'valid': 0,
        'corrupted': 0,
        'missing': 0,
        'purged_files': [],
        'purged_entries': []
    }

    # Load output log
    output_log = load_output_log(output_log_path)
    if not output_log:
        print("  No output log found, nothing to purge")
        return stats

    modified = False

    for entry in output_log.values():
        group = entry.get('group', config.DEFAULT_GROUP)
        output_dir = config.get_output_dir(ip, group)

        images_to_keep = []

        for img in entry.get('images', []):
            stats['scanned'] += 1

            # Build file path
            filename = img.get('filename', '')
            path = img.get('path', '')

            if not path and filename:
                path = os.path.join(output_dir, filename)

            if not path:
                # No path info, keep the entry (can't verify)
                images_to_keep.append(img)
                continue

            # Check if file exists
            if not os.path.exists(path):
                stats['missing'] += 1
                stats['purged_entries'].append({
                    'character': entry.get('name', 'unknown'),
                    'file': filename or path,
                    'reason': 'missing'
                })
                modified = True
                continue

            # Validate image content
            if is_valid_image(path):
                stats['valid'] += 1
                images_to_keep.append(img)
            else:
                stats['corrupted'] += 1
                stats['purged_files'].append(path)
                stats['purged_entries'].append({
                    'character': entry.get('name', 'unknown'),
                    'file': filename or path,
                    'reason': 'corrupted'
                })

                # Delete the corrupted file
                if not dry_run:
                    try:
                        os.remove(path)
                    except OSError as e:
                        print(f"    Warning: Could not delete {path}: {e}")

                modified = True

        # Update entry with only valid images
        entry['images'] = images_to_keep

        # Update entry result status
        _update_entry_result(entry)

    # Save updated output log
    if modified and not dry_run:
        results = list(output_log.values())
        save_output_log(output_log_path, results)

    return stats


def print_purge_report(stats: dict, dry_run: bool = False) -> None:
    """Print a formatted report of the purge operation."""
    prefix = "[DRY RUN] " if dry_run else ""

    print(f"\n{'='*60}")
    print(f"{prefix}IMAGE VALIDATION REPORT")
    print(f"{'='*60}")
    print(f"Total images scanned: {stats['scanned']}")
    print(f"  - Valid: {stats['valid']}")
    print(f"  - Missing: {stats['missing']}")
    print(f"  - Corrupted: {stats['corrupted']}")

    if stats['purged_entries']:
        print(f"\n{prefix}Purged entries:")
        for entry in stats['purged_entries'][:20]:
            print(f"  - {entry['character']}: {entry['file']} ({entry['reason']})")
        if len(stats['purged_entries']) > 20:
            print(f"  ... and {len(stats['purged_entries']) - 20} more")

    if not dry_run and stats['corrupted'] > 0:
        print(f"\n{stats['corrupted']} corrupted files deleted and removed from metadata.")
        print("These images are now eligible for re-download.")

    print(f"{'='*60}\n")
