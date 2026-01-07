"""
Migrate bulba/fando filenames to include variant.

Current format: {Name}-{source}-{count}.{ext}
New format:     {Name}-{source}-{variant}-{count}.{ext}

This script:
1. Renames files on disk
2. Updates output.json with new paths
3. Updates arena.db battles table with new paths
4. Updates arena.db image_stats table with new paths

Usage:
    python scripts/migrate_filenames.py --dry-run   # Preview changes
    python scripts/migrate_filenames.py             # Execute migration
"""

import json
import os
import re
import sqlite3
import sys
from pathlib import Path
from typing import Dict, Optional, Tuple

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

# Paths
PROJECT_ROOT = Path(__file__).parent.parent
OUTPUT_JSON = PROJECT_ROOT / 'output' / 'pokemon' / 'output.json'
ARENA_DB = PROJECT_ROOT / 'Arena' / 'arena.db'


def parse_old_filename(filename: str) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
    """
    Parse old filename format: {Name}-{source}-{count}.{ext}

    Returns:
        Tuple of (name, source, count, extension) or (None, None, None, None) if parsing fails
    """
    # Match pattern: Name-source-count.ext
    # e.g., "Misty-bulba-1.png" -> ("Misty", "bulba", "1", ".png")
    match = re.match(r'^(.+)-([a-z0-9]+)-(\d+)(\.[a-z]+)$', filename, re.IGNORECASE)
    if match:
        return match.groups()  # type: ignore[return-value]
    return None, None, None, None


def build_new_filename(name: str, source: str, variant: str, count: str, ext: str) -> str:
    """Build new filename with variant included."""
    # Sanitize variant name (remove problematic chars)
    safe_variant = re.sub(r'[<>:"/\\|?*]', '', variant).replace(' ', '_')
    return f"{name}-{source}-{safe_variant}-{count}{ext}"


def get_variant_for_image(path: str, output_data: Dict) -> str:
    """Look up the variant for an image from output.json."""
    for entry in output_data.get('results', []):
        for img in entry.get('images', []):
            if img.get('path') == path:
                return img.get('variant', 'base')
    return 'base'


def migrate_filenames(dry_run: bool = True) -> Dict:
    """
    Migrate filenames to include variant.

    Returns:
        Dict with migration stats and path mappings
    """
    # Load output.json
    if not OUTPUT_JSON.exists():
        print(f"Error: {OUTPUT_JSON} not found")
        return {}

    with open(OUTPUT_JSON, encoding='utf-8') as f:
        output_data = json.load(f)

    # Build path mapping: old_path -> new_path
    path_mapping = {}
    files_renamed = 0
    files_skipped = 0
    files_missing = 0

    print("=" * 60)
    print("FILENAME MIGRATION" + (" (DRY RUN)" if dry_run else ""))
    print("=" * 60)

    for entry in output_data.get('results', []):
        for img in entry.get('images', []):
            old_path = img.get('path', '')
            source = img.get('source', '')
            variant = img.get('variant', 'base')

            if not old_path:
                continue

            # Only migrate bulba and fando (wiki sources without variant in filename)
            if source not in ['bulba', 'fando']:
                continue

            # Parse the old filename
            filename = os.path.basename(old_path)
            name, src, count, ext = parse_old_filename(filename)

            if not name:
                print(f"  [SKIP] Could not parse: {filename}")
                files_skipped += 1
                continue

            # At this point, all values are non-None due to the guard check above
            assert src is not None and count is not None and ext is not None

            # Check if already has variant in filename (already migrated)
            # Pattern with variant: Name-source-variant-count.ext
            if re.match(r'^.+-[a-z0-9]+-[a-zA-Z0-9_]+-\d+\.[a-z]+$', filename, re.IGNORECASE):
                # Could be already migrated, check if variant matches
                parts = filename.rsplit('-', 2)
                if len(parts) >= 3:
                    files_skipped += 1
                    continue

            # Build new filename
            new_filename = build_new_filename(name, src, variant, count, ext)
            new_path = os.path.join(os.path.dirname(old_path), new_filename)

            # Skip if no change needed
            if old_path == new_path:
                files_skipped += 1
                continue

            # Check if file exists
            if not os.path.exists(old_path):
                # print(f"  [MISSING] {old_path}")
                files_missing += 1
                continue

            # Store mapping
            path_mapping[old_path] = new_path

            print(f"  {filename} -> {new_filename}")

            # Rename file
            if not dry_run:
                try:
                    os.rename(old_path, new_path)
                    files_renamed += 1
                except Exception as e:
                    print(f"    [ERROR] Failed to rename: {e}")
            else:
                files_renamed += 1

    print()
    print(f"Files to rename: {files_renamed}")
    print(f"Files skipped: {files_skipped}")
    print(f"Files missing: {files_missing}")

    return {
        'path_mapping': path_mapping,
        'files_renamed': files_renamed,
        'files_skipped': files_skipped,
        'files_missing': files_missing,
        'output_data': output_data
    }


def update_output_json(path_mapping: Dict, output_data: Dict, dry_run: bool = True):
    """Update output.json with new paths."""
    if not path_mapping:
        print("\nNo paths to update in output.json")
        return

    print("\n" + "=" * 60)
    print("UPDATING OUTPUT.JSON" + (" (DRY RUN)" if dry_run else ""))
    print("=" * 60)

    updates = 0
    for entry in output_data.get('results', []):
        for img in entry.get('images', []):
            old_path = img.get('path', '')
            if old_path in path_mapping:
                img['path'] = path_mapping[old_path]
                updates += 1

    print(f"Paths updated: {updates}")

    if not dry_run and updates > 0:
        with open(OUTPUT_JSON, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)
        print(f"Saved: {OUTPUT_JSON}")


def update_arena_db(path_mapping: Dict, dry_run: bool = True):
    """Update arena.db with new paths."""
    if not path_mapping:
        print("\nNo paths to update in arena.db")
        return

    if not ARENA_DB.exists():
        print(f"\nArena database not found: {ARENA_DB}")
        return

    print("\n" + "=" * 60)
    print("UPDATING ARENA.DB" + (" (DRY RUN)" if dry_run else ""))
    print("=" * 60)

    conn = sqlite3.connect(str(ARENA_DB))
    cursor = conn.cursor()

    # Update battles table
    battles_updated = 0
    for old_path, new_path in path_mapping.items():
        if not dry_run:
            cursor.execute("UPDATE battles SET path = ? WHERE path = ?", (new_path, old_path))
            battles_updated += cursor.rowcount
        else:
            cursor.execute("SELECT COUNT(*) FROM battles WHERE path = ?", (old_path,))
            count = cursor.fetchone()[0]
            if count > 0:
                battles_updated += count

    print(f"Battles table rows to update: {battles_updated}")

    # Update image_stats table
    stats_updated = 0
    for old_path, new_path in path_mapping.items():
        if not dry_run:
            cursor.execute("UPDATE image_stats SET path = ? WHERE path = ?", (new_path, old_path))
            stats_updated += cursor.rowcount
        else:
            cursor.execute("SELECT COUNT(*) FROM image_stats WHERE path = ?", (old_path,))
            count = cursor.fetchone()[0]
            if count > 0:
                stats_updated += count

    print(f"Image_stats table rows to update: {stats_updated}")

    # Update deletions table
    deletions_updated = 0
    for old_path, new_path in path_mapping.items():
        if not dry_run:
            cursor.execute("UPDATE deletions SET path = ? WHERE path = ?", (new_path, old_path))
            deletions_updated += cursor.rowcount
        else:
            cursor.execute("SELECT COUNT(*) FROM deletions WHERE path = ?", (old_path,))
            count = cursor.fetchone()[0]
            if count > 0:
                deletions_updated += count

    print(f"Deletions table rows to update: {deletions_updated}")

    if not dry_run:
        conn.commit()
        print("Database changes committed")

    conn.close()


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Migrate filenames to include variant")
    parser.add_argument('--dry-run', action='store_true',
                       help="Preview changes without making them")
    args = parser.parse_args()

    dry_run = args.dry_run

    # Step 1: Migrate filenames
    result = migrate_filenames(dry_run=dry_run)

    if not result:
        return

    path_mapping = result['path_mapping']
    output_data = result['output_data']

    # Step 2: Update output.json
    update_output_json(path_mapping, output_data, dry_run=dry_run)

    # Step 3: Update arena.db
    update_arena_db(path_mapping, dry_run=dry_run)

    print("\n" + "=" * 60)
    if dry_run:
        print("DRY RUN COMPLETE - No changes made")
        print("Run without --dry-run to apply changes")
    else:
        print("MIGRATION COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    main()
