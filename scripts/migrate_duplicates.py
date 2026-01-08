"""
Migrate duplicate cross-character images to a shared 'multiple' folder.

This script:
1. Finds images downloaded for multiple characters (same URL or same MD5 hash)
2. Merges their battle records using existing merge_images()
3. Moves surviving image to Output/{universe}/{ip}/multiple/
4. Renames to multiple-{source}-{variant}-{n}.{ext}
5. Updates output.json: removes from character results, adds to "multiple" section
6. Updates arena.db paths

Duplicate Detection Modes:
- URL-based: Find images with the same source URL (default)
- MD5-based: Find images with identical content via MD5 hash (--md5)

Merge Priority (when merging duplicates):
1. Prefer image with more battle records (wins)
2. Prefer image with better metadata (has URL vs "unknown")
3. Prefer higher resolution image

Usage:
    python scripts/migrate_duplicates.py --dry-run              # Preview URL-based changes
    python scripts/migrate_duplicates.py --md5 --dry-run        # Preview MD5-based changes
    python scripts/migrate_duplicates.py --ip genshin_impact    # Run on specific IP
    python scripts/migrate_duplicates.py                        # Execute migration
"""

import hashlib
import json
import os
import re
import shutil
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from PIL import Image

from core.utils import get_ip_output_dir
from extractors.utils import extract_variant_from_filename

# Paths
ARENA_DB = PROJECT_ROOT / 'games' / 'arena' / 'arena.db'


def get_output_paths(ip: str) -> Tuple[Path, Path]:
    """Get output directory and output.json path for an IP."""
    output_dir = Path(get_ip_output_dir(ip))
    output_json = output_dir / 'output.json'
    return output_dir, output_json


def compute_md5(file_path: str) -> Optional[str]:
    """Compute MD5 hash of a file for duplicate detection (non-security use).
    
    MD5 is used here solely for detecting duplicate image files by comparing
    file content. This is NOT for security purposes (authentication, integrity
    verification, etc.), so we explicitly set usedforsecurity=False.
    """
    try:
        hash_md5 = hashlib.md5(usedforsecurity=False)  # nosec B324 - not for security
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()
    except Exception:
        return None


def find_duplicates_by_url(output_data: Dict) -> Dict[str, List[Tuple[str, str, Dict]]]:
    """
    Find images that have the same URL across multiple characters.

    Returns:
        Dict mapping URL -> list of (character_key, character_name, image_entry) tuples
    """
    url_to_images = defaultdict(list)

    for entry in output_data.get('results', []):
        char_key = entry.get('key', '')
        char_name = entry.get('name', '')

        for img in entry.get('images', []):
            url = img.get('url', '')
            if url and url != 'unknown (backfilled from disk)':
                # Store character key, name, and full image entry
                url_to_images[url].append((char_key, char_name, img))

    # Filter to only duplicates (URLs appearing for multiple characters)
    duplicates = {url: imgs for url, imgs in url_to_images.items() if len(imgs) > 1}

    return duplicates


def find_duplicates_by_md5(output_data: Dict) -> Dict[str, List[Tuple[str, str, Dict]]]:
    """
    Find images that have the same MD5 hash (identical content).

    This detects duplicates even when:
    - Same image downloaded from different URLs
    - Images re-fetched with --getnew that match existing images
    - Backfilled images that match newly fetched ones

    Returns:
        Dict mapping MD5 -> list of (character_key, character_name, image_entry) tuples
    """
    md5_to_images = defaultdict(list)

    for entry in output_data.get('results', []):
        char_key = entry.get('key', '')
        char_name = entry.get('name', '')

        for img in entry.get('images', []):
            path = img.get('path', '')
            if path and os.path.exists(path):
                md5 = compute_md5(path)
                if md5:
                    md5_to_images[md5].append((char_key, char_name, img))

    # Filter to only duplicates (same MD5 appearing multiple times)
    duplicates = {md5: imgs for md5, imgs in md5_to_images.items() if len(imgs) > 1}

    return duplicates


def find_duplicates(output_data: Dict, use_md5: bool = False) -> Dict[str, List[Tuple[str, str, Dict]]]:
    """
    Find duplicate images using URL or MD5 matching.

    Args:
        output_data: The output.json data
        use_md5: If True, use MD5 hash comparison. If False, use URL matching.

    Returns:
        Dict mapping identifier (URL or MD5) -> list of (char_key, char_name, image_entry) tuples
    """
    if use_md5:
        return find_duplicates_by_md5(output_data)
    return find_duplicates_by_url(output_data)


def get_image_resolution(path: str) -> int:
    """Get image resolution (width * height). Returns 0 if cannot read."""
    try:
        with Image.open(path) as img:
            return img.width * img.height
    except Exception:
        return 0


def get_battle_wins(path: str) -> int:
    """Get total wins for an image from arena.db. Returns 0 if not found."""
    if not ARENA_DB.exists():
        return 0

    try:
        conn = sqlite3.connect(str(ARENA_DB))
        cursor = conn.cursor()
        cursor.execute("""
            SELECT COALESCE(ip_wins, 0) + COALESCE(group_wins, 0) +
                   COALESCE(character_wins, 0) + COALESCE(source_wins, 0) +
                   COALESCE(variant_wins, 0) as total_wins
            FROM image_stats
            WHERE path = ? COLLATE NOCASE
        """, (path,))
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else 0
    except Exception:
        return 0


def get_metadata_score(img: Dict) -> int:
    """
    Score image metadata quality. Higher = better.

    Scores:
    - Has real URL (not backfilled): +10
    - Has page_url: +5
    - Has source: +2
    - Has variant: +2
    """
    score = 0
    url = img.get('url', '')
    if url and url != 'unknown (backfilled from disk)':
        score += 10
    if img.get('page_url'):
        score += 5
    if img.get('source'):
        score += 2
    if img.get('variant'):
        score += 2
    return score


def select_survivor(image_list: List[Tuple[str, str, Dict]]) -> Tuple[Dict, List[Dict]]:
    """
    Select which image should survive from a list of duplicates.

    Priority (in order):
    1. Most battle wins
    2. Best metadata (real URL vs backfilled)
    3. Highest resolution

    Args:
        image_list: List of (char_key, char_name, img_dict) tuples

    Returns:
        (survivor_img, list_of_duplicate_imgs)
    """
    # Score each image
    scored: List[Dict[str, Any]] = []
    for char_key, char_name, img in image_list:
        path = img.get('path', '')
        wins = get_battle_wins(path) if path and os.path.exists(path) else 0
        metadata_score = get_metadata_score(img)
        resolution = get_image_resolution(path) if path and os.path.exists(path) else 0

        scored.append({
            'char_key': char_key,
            'char_name': char_name,
            'img': img,
            'wins': wins,
            'metadata_score': metadata_score,
            'resolution': resolution
        })

    # Sort by priority: wins desc, metadata desc, resolution desc
    scored.sort(key=lambda x: (-x['wins'], -x['metadata_score'], -x['resolution']))

    survivor = scored[0]
    duplicates = scored[1:]

    # Merge metadata from duplicates into survivor if survivor is missing data
    survivor_img = survivor['img'].copy()
    for dup in duplicates:
        dup_img = dup['img']
        # If survivor has backfilled URL but duplicate has real URL, use duplicate's
        if survivor_img.get('url') == 'unknown (backfilled from disk)':
            if dup_img.get('url') and dup_img['url'] != 'unknown (backfilled from disk)':
                survivor_img['url'] = dup_img['url']
        # Same for page_url
        if not survivor_img.get('page_url') and dup_img.get('page_url'):
            survivor_img['page_url'] = dup_img['page_url']

    return survivor_img, [d['img'] for d in duplicates]


def generate_multiple_filename(source: str, variant: str, count: int, ext: str) -> str:
    """Generate filename for multiple-character images."""
    # Sanitize variant name
    safe_variant = re.sub(r'[<>:"/\\|?*]', '', variant).replace(' ', '_')
    return f"multiple-{source}-{safe_variant}-{count}{ext}"


def migrate_duplicates(ip: str = "pokemon", dry_run: bool = True, use_md5: bool = False) -> Dict:
    """
    Migrate duplicate images to multiple/ folder.

    Args:
        ip: IP to process (e.g., "pokemon", "genshin_impact")
        dry_run: If True, only preview changes
        use_md5: If True, use MD5 hash to find duplicates. If False, use URL matching.

    Returns:
        Dict with migration stats
    """
    # Get paths for this IP
    OUTPUT_DIR, OUTPUT_JSON = get_output_paths(ip)

    # Load output.json
    if not OUTPUT_JSON.exists():
        print(f"Error: {OUTPUT_JSON} not found")
        return {}

    with open(OUTPUT_JSON, encoding='utf-8') as f:
        output_data = json.load(f)

    # Find duplicates
    duplicates = find_duplicates(output_data, use_md5=use_md5)

    if not duplicates:
        print("No duplicate images found.")
        return {'duplicates_found': 0}

    mode_str = "MD5" if use_md5 else "URL"
    print("=" * 70)
    print(f"DUPLICATE IMAGE MIGRATION ({mode_str} mode)" + (" (DRY RUN)" if dry_run else ""))
    print(f"IP: {ip}")
    print("=" * 70)
    print(f"\nFound {len(duplicates)} duplicate sets\n")

    # Track counts for (source, variant) combinations
    source_variant_counts = defaultdict(int)

    # Track changes for database updates
    path_updates = {}  # old_path -> new_path
    paths_to_merge = []  # list of (surviving_path, duplicate_paths, new_path, survivor_img)

    # Track images to remove from character results
    images_to_remove = []  # list of (char_key, path)

    # Track entries for "multiple" section
    multiple_entries = []

    # Process each duplicate set
    for identifier, image_list in duplicates.items():
        # Show identifier (URL or MD5)
        if use_md5:
            print(f"\nDuplicate MD5: {identifier[:16]}...")
        else:
            print(f"\nDuplicate URL: {identifier[:80]}...")

        char_names = [name for _, name, _ in image_list]
        print(f"  Characters: {', '.join(char_names)}")

        # Check how many files exist on disk
        existing = [(ck, cn, img) for ck, cn, img in image_list
                    if img.get('path') and os.path.exists(img['path'])]

        if len(existing) < 2:
            print("  [SKIP] Less than 2 files exist on disk")
            continue

        # Use smart survivor selection (wins > metadata > resolution)
        survivor_img, duplicate_imgs = select_survivor(image_list)
        survivor_path = survivor_img.get('path', '')

        # Get paths of duplicates
        duplicate_paths = [img.get('path', '') for img in duplicate_imgs if img.get('path')]

        # Show selection reasoning
        wins = get_battle_wins(survivor_path)
        meta_score = get_metadata_score(survivor_img)
        resolution = get_image_resolution(survivor_path)
        print(f"  Survivor: {os.path.basename(survivor_path)}")
        print(f"    (wins={wins}, metadata={meta_score}, res={resolution:,}px)")
        for dup_path in duplicate_paths:
            print(f"  Duplicate: {os.path.basename(dup_path)}")

        # Extract variant from survivor filename
        survivor_filename = os.path.basename(survivor_path)
        variant = extract_variant_from_filename(survivor_filename)
        source = survivor_img.get('source', 'unknown')

        # Generate new filename
        source_variant_counts[(source, variant)] += 1
        count = source_variant_counts[(source, variant)]
        ext = os.path.splitext(survivor_path)[1]
        new_filename = generate_multiple_filename(source, variant, count, ext)

        # New path in multiple/ folder
        multiple_dir = OUTPUT_DIR / 'multiple'
        new_path = str(multiple_dir / new_filename)

        print(f"  -> {new_filename}")

        # Track for later processing
        paths_to_merge.append((survivor_path, duplicate_paths, new_path, survivor_img))
        path_updates[survivor_path] = new_path

        # Track images to remove from character results (by path for MD5 mode)
        for char_key, _char_name, img in image_list:
            images_to_remove.append((char_key, img.get('path', '')))

        # Create entry for "multiple" section (with merged metadata)
        url_value = survivor_img.get('url', identifier if not use_md5 else '')
        multiple_entry = {
            'path': new_path,
            'source': source,
            'url': url_value,
            'page_url': survivor_img.get('page_url', ''),
            'variant': variant,
            'original_characters': char_names
        }
        multiple_entries.append(multiple_entry)

    print("\n" + "=" * 70)
    print(f"Total duplicate sets: {len(paths_to_merge)}")
    print(f"Images to merge: {sum(1 + len(dups) for _, dups, _, _ in paths_to_merge)}")
    print(f"Files to move: {len(paths_to_merge)}")
    print("=" * 70)

    if not dry_run:
        # Create multiple/ directory
        multiple_dir = OUTPUT_DIR / 'multiple'
        multiple_dir.mkdir(exist_ok=True)

        # Process each duplicate set
        for survivor_path, duplicate_paths, new_path, _ in paths_to_merge:
            # Merge battle records in database
            merge_battle_records(survivor_path, duplicate_paths)

            # Move survivor to new location
            shutil.move(survivor_path, new_path)

            # Delete duplicate files
            for dup_path in duplicate_paths:
                if os.path.exists(dup_path):
                    os.remove(dup_path)

            # Update database paths
            update_db_path(survivor_path, new_path)

    return {
        'duplicates_found': len(duplicates),
        'paths_merged': paths_to_merge,
        'path_updates': path_updates,
        'images_to_remove': images_to_remove,
        'multiple_entries': multiple_entries,
        'output_data': output_data,
        'output_json_path': OUTPUT_JSON,
        'ip': ip
    }


def merge_battle_records(surviving_path: str, duplicate_paths: List[str]):
    """Merge battle records from duplicates into survivor."""
    if not ARENA_DB.exists():
        return

    conn = sqlite3.connect(str(ARENA_DB))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    for dup_path in duplicate_paths:
        # Update all battle records to point to surviving image
        cursor.execute("""
            UPDATE battles
            SET path = ?
            WHERE path = ?
        """, (surviving_path, dup_path))

        # Delete duplicate's stats row
        cursor.execute("DELETE FROM image_stats WHERE path = ?", (dup_path,))

    # Rebuild stats for surviving image
    cursor.execute("DELETE FROM image_stats WHERE path = ?", (surviving_path,))

    cursor.execute("""
        SELECT scope_level, result, COUNT(*) as count
        FROM battles
        WHERE path = ?
        GROUP BY scope_level, result
    """, (surviving_path,))

    rows = cursor.fetchall()

    if rows:
        stats = {
            'total_battles': 0,
            'ip_wins': 0, 'ip_losses': 0,
            'group_wins': 0, 'group_losses': 0,
            'character_wins': 0, 'character_losses': 0,
            'source_wins': 0, 'source_losses': 0,
            'variant_wins': 0, 'variant_losses': 0
        }

        for row in rows:
            scope_level = row['scope_level'] or 'ip'
            result = row['result']
            count = row['count']

            stats['total_battles'] += count

            if result == 'win':
                stats[f'{scope_level}_wins'] += count
            else:
                stats[f'{scope_level}_losses'] += count

        cursor.execute("""
            INSERT INTO image_stats (
                path, total_battles,
                ip_wins, ip_losses,
                group_wins, group_losses,
                character_wins, character_losses,
                source_wins, source_losses,
                variant_wins, variant_losses
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            surviving_path, stats['total_battles'],
            stats['ip_wins'], stats['ip_losses'],
            stats['group_wins'], stats['group_losses'],
            stats['character_wins'], stats['character_losses'],
            stats['source_wins'], stats['source_losses'],
            stats['variant_wins'], stats['variant_losses']
        ))

    conn.commit()
    conn.close()


def update_db_path(old_path: str, new_path: str):
    """Update path references in arena.db.

    Note: SQLite string matching is case-sensitive, but Windows paths are not.
    We use COLLATE NOCASE to handle this.
    """
    if not ARENA_DB.exists():
        return

    conn = sqlite3.connect(str(ARENA_DB))
    cursor = conn.cursor()

    # Update battles table (case-insensitive match for Windows paths)
    cursor.execute(
        "UPDATE battles SET path = ? WHERE path = ? COLLATE NOCASE",
        (new_path, old_path)
    )

    # Update image_stats table
    cursor.execute(
        "UPDATE image_stats SET path = ? WHERE path = ? COLLATE NOCASE",
        (new_path, old_path)
    )

    # Update deletions table
    cursor.execute(
        "UPDATE deletions SET path = ? WHERE path = ? COLLATE NOCASE",
        (new_path, old_path)
    )

    conn.commit()
    conn.close()


def update_output_json(result: Dict, dry_run: bool = True):
    """Update output.json: remove from character results, add "multiple" section."""
    if not result:
        return

    output_data = result['output_data']
    images_to_remove = result['images_to_remove']  # list of (char_key, path)
    multiple_entries = result['multiple_entries']
    output_json_path = result.get('output_json_path')

    print("\n" + "=" * 70)
    print("UPDATING OUTPUT.JSON" + (" (DRY RUN)" if dry_run else ""))
    print("=" * 70)

    # Remove images from character results (by path, works for both URL and MD5 modes)
    removed_count = 0
    for entry in output_data.get('results', []):
        char_key = entry.get('key', '')
        original_images = entry.get('images', [])

        # Get paths to remove for this character
        paths_to_remove = {path for key, path in images_to_remove if key == char_key}

        # Filter out images by path
        new_images = [img for img in original_images if img.get('path', '') not in paths_to_remove]

        removed = len(original_images) - len(new_images)
        if removed > 0:
            entry['images'] = new_images
            removed_count += removed

    print(f"Images removed from character results: {removed_count}")

    # Add "multiple" section
    output_data['multiple'] = multiple_entries
    print(f"Images added to 'multiple' section: {len(multiple_entries)}")

    # Update total_images count
    total_images = sum(len(e.get('images', [])) for e in output_data.get('results', []))
    total_images += len(multiple_entries)
    output_data['total_images'] = total_images
    print(f"New total_images count: {total_images}")

    if not dry_run and output_json_path:
        with open(output_json_path, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)
        print(f"Saved: {output_json_path}")


def update_arena_db(result: Dict, dry_run: bool = True):
    """Preview database updates (actual updates done during migration)."""
    if not result or dry_run:
        return

    # Database updates are already done in migrate_duplicates() when not dry_run
    print("\n" + "=" * 70)
    print("DATABASE UPDATES COMPLETE")
    print("=" * 70)


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Migrate duplicate cross-character images",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Detection Modes:
  Default (URL):  Find duplicates by matching source URLs
  --md5:          Find duplicates by comparing file content (MD5 hash)
                  Use this after --getnew to merge images with backfilled metadata

Examples:
  python scripts/migrate_duplicates.py --dry-run                    # Preview URL-based (pokemon)
  python scripts/migrate_duplicates.py --ip genshin_impact --md5    # MD5 mode for genshin
  python scripts/migrate_duplicates.py --ip genshin_impact          # Execute on genshin
        """
    )
    parser.add_argument('--dry-run', action='store_true',
                       help="Preview changes without making them")
    parser.add_argument('--ip', type=str, default='pokemon',
                       help="IP to process (default: pokemon)")
    parser.add_argument('--md5', action='store_true',
                       help="Use MD5 hash to find duplicates (for merging backfilled images)")
    args = parser.parse_args()

    dry_run = args.dry_run
    ip = args.ip
    use_md5 = args.md5

    # Step 1: Find and migrate duplicates
    result = migrate_duplicates(ip=ip, dry_run=dry_run, use_md5=use_md5)

    if not result or result.get('duplicates_found', 0) == 0:
        return

    # Step 2: Update output.json
    update_output_json(result, dry_run=dry_run)

    # Step 3: Database updates (already done if not dry_run)
    update_arena_db(result, dry_run=dry_run)

    print("\n" + "=" * 70)
    if dry_run:
        print("DRY RUN COMPLETE - No changes made")
        print("Run without --dry-run to apply changes")
    else:
        print("MIGRATION COMPLETE")
    print("=" * 70)


def merge_same_character_duplicates(ip: str = "pokemon", dry_run: bool = True) -> Dict:
    """
    Merge duplicate images within the same character (same MD5, same character).

    This is for the case where:
    - Image was backfilled from disk (no URL)
    - Same image was re-fetched with --getnew (has URL)
    - We want to keep the file but merge metadata (prefer the one with URL)

    Unlike migrate_duplicates(), this:
    - Only looks at duplicates WITHIN the same character
    - Deletes the duplicate file but keeps the survivor in place
    - Updates output.json to merge metadata

    Args:
        ip: IP to process
        dry_run: If True, only preview changes

    Returns:
        Dict with merge stats
    """
    OUTPUT_DIR, OUTPUT_JSON = get_output_paths(ip)

    if not OUTPUT_JSON.exists():
        print(f"Error: {OUTPUT_JSON} not found")
        return {}

    with open(OUTPUT_JSON, encoding='utf-8') as f:
        output_data = json.load(f)

    print("=" * 70)
    print("SAME-CHARACTER DUPLICATE MERGE (MD5 mode)" + (" (DRY RUN)" if dry_run else ""))
    print(f"IP: {ip}")
    print("=" * 70)

    merged_count = 0
    deleted_files = []

    for entry in output_data.get('results', []):
        char_name = entry.get('name', '')
        images = entry.get('images', [])

        if len(images) < 2:
            continue

        # Group by MD5
        md5_groups = defaultdict(list)
        for img in images:
            path = img.get('path', '')
            if path and os.path.exists(path):
                md5 = compute_md5(path)
                if md5:
                    md5_groups[md5].append(img)

        # Process duplicates within this character
        new_images = []
        processed_md5s = set()

        for img in images:
            path = img.get('path', '')
            if not path or not os.path.exists(path):
                new_images.append(img)
                continue

            md5 = compute_md5(path)
            if not md5 or md5 in processed_md5s:
                continue

            group = md5_groups.get(md5, [])
            if len(group) < 2:
                # Not a duplicate
                new_images.append(img)
                processed_md5s.add(md5)
                continue

            # Found duplicates - select survivor
            print(f"\n{char_name}: Found {len(group)} duplicates (MD5: {md5[:12]}...)")

            # Sort by metadata score, then resolution
            scored = []
            for dup_img in group:
                dup_path = dup_img.get('path', '')
                meta_score = get_metadata_score(dup_img)
                resolution = get_image_resolution(dup_path) if dup_path else 0
                wins = get_battle_wins(dup_path) if dup_path else 0
                scored.append({
                    'img': dup_img,
                    'wins': wins,
                    'meta_score': meta_score,
                    'resolution': resolution
                })

            scored.sort(key=lambda x: (-x['wins'], -x['meta_score'], -x['resolution']))

            survivor = scored[0]
            duplicates = scored[1:]

            # Merge metadata from duplicates into survivor
            survivor_img = survivor['img'].copy()
            for dup in duplicates:
                dup_img = dup['img']
                # Take URL from duplicate if survivor doesn't have one
                if survivor_img.get('url') == 'unknown (backfilled from disk)':
                    if dup_img.get('url') and dup_img['url'] != 'unknown (backfilled from disk)':
                        survivor_img['url'] = dup_img['url']
                        print(f"  Merged URL from: {os.path.basename(dup_img.get('path', ''))}")
                if not survivor_img.get('page_url') and dup_img.get('page_url'):
                    survivor_img['page_url'] = dup_img['page_url']

            print(f"  Survivor: {os.path.basename(survivor_img.get('path', ''))} (meta={survivor['meta_score']})")

            # Delete duplicate files
            for dup in duplicates:
                dup_path = dup['img'].get('path', '')
                if dup_path and os.path.exists(dup_path):
                    print(f"  Delete: {os.path.basename(dup_path)}")
                    if not dry_run:
                        os.remove(dup_path)
                    deleted_files.append(dup_path)

            new_images.append(survivor_img)
            processed_md5s.add(md5)
            merged_count += 1

        entry['images'] = new_images

    print("\n" + "=" * 70)
    print(f"Duplicate sets merged: {merged_count}")
    print(f"Files deleted: {len(deleted_files)}")
    print("=" * 70)

    if not dry_run and merged_count > 0:
        # Update total count
        total_images = sum(len(e.get('images', [])) for e in output_data.get('results', []))
        output_data['total_images'] = total_images

        with open(OUTPUT_JSON, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)
        print(f"Saved: {OUTPUT_JSON}")

    return {
        'merged_count': merged_count,
        'deleted_files': deleted_files
    }


def run_post_fetch_dedup(ip: str):
    """
    Run duplicate check after a --getnew fetch.
    Called from fetch_images.py.
    """
    print("\n" + "=" * 70)
    print("POST-FETCH DUPLICATE CHECK")
    print("=" * 70)

    result = merge_same_character_duplicates(ip=ip, dry_run=False)

    if result.get('merged_count', 0) > 0:
        print(f"\nMerged {result['merged_count']} duplicate sets")
    else:
        print("\nNo duplicates found")


if __name__ == "__main__":
    main()
