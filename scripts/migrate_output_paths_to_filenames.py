"""
Migrate output.json files from absolute paths to filenames.

This script converts the 'path' field in image entries to 'filename',
making the metadata portable across different machines and directory structures.

Before: {"path": "C:\\Users\\...\\Output\\universe\\ip\\group\\Name-source-variant-1.jpg", ...}
After:  {"filename": "Name-source-variant-1.jpg", ...}

Usage:
    python scripts/migrate_output_paths_to_filenames.py [--dry-run]
"""

import argparse
import json
import os
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.utils import OUTPUT_DIR


def migrate_output_json(output_json_path: str, dry_run: bool = False) -> dict:
    """
    Migrate a single output.json file from paths to filenames.

    Args:
        output_json_path: Path to the output.json file
        dry_run: If True, don't write changes

    Returns:
        Dict with migration stats: {migrated: int, already_migrated: int, errors: int}
    """
    stats = {'migrated': 0, 'already_migrated': 0, 'errors': 0}

    if not os.path.exists(output_json_path):
        print(f"  File not found: {output_json_path}")
        return stats

    with open(output_json_path, encoding='utf-8') as f:
        data = json.load(f)

    results = data.get('results', [])
    modified = False

    for entry in results:
        for img in entry.get('images', []):
            if 'path' in img:
                # Extract filename from path
                path = img['path']
                filename = os.path.basename(path)

                # Add filename, remove path
                img['filename'] = filename
                del img['path']
                stats['migrated'] += 1
                modified = True
            elif 'filename' in img:
                stats['already_migrated'] += 1
            else:
                print(f"  Warning: Image entry has neither 'path' nor 'filename': {img}")
                stats['errors'] += 1

    if modified and not dry_run:
        with open(output_json_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)

    return stats


def find_output_json_files(output_dir: str) -> list:
    """Find all output.json files in the Output directory."""
    output_files = []

    for root, _dirs, files in os.walk(output_dir):
        if 'output.json' in files:
            output_files.append(os.path.join(root, 'output.json'))

    return output_files


def main():
    parser = argparse.ArgumentParser(description='Migrate output.json from paths to filenames')
    parser.add_argument('--dry-run', action='store_true', help='Preview changes without writing')
    args = parser.parse_args()

    print("=" * 60)
    print("Migrate output.json: path -> filename")
    print("=" * 60)

    if args.dry_run:
        print("\n[DRY RUN] No changes will be written\n")

    # Find all output.json files
    output_files = find_output_json_files(OUTPUT_DIR)

    if not output_files:
        print(f"No output.json files found in {OUTPUT_DIR}")
        return

    print(f"Found {len(output_files)} output.json files\n")

    total_stats = {'migrated': 0, 'already_migrated': 0, 'errors': 0}

    for output_path in output_files:
        # Get relative path for display
        rel_path = os.path.relpath(output_path, OUTPUT_DIR)
        print(f"Processing: {rel_path}")

        stats = migrate_output_json(output_path, dry_run=args.dry_run)

        print(f"  Migrated: {stats['migrated']}, Already migrated: {stats['already_migrated']}, Errors: {stats['errors']}")

        for key in total_stats:
            total_stats[key] += stats[key]

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Total migrated:         {total_stats['migrated']}")
    print(f"Already migrated:       {total_stats['already_migrated']}")
    print(f"Errors:                 {total_stats['errors']}")

    if args.dry_run:
        print("\n[DRY RUN] Run without --dry-run to apply changes")


if __name__ == '__main__':
    main()
