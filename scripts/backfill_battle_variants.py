"""
Backfill variant field in battles table from path.
Run after migrating filenames to include variant.
"""

import re
import sqlite3
from pathlib import Path

ARENA_DB = Path(__file__).parent.parent / 'Arena' / 'arena.db'

def backfill_variants():
    conn = sqlite3.connect(str(ARENA_DB))
    cursor = conn.cursor()

    # Get all battles with NULL variant
    cursor.execute('SELECT path, rowid FROM battles WHERE variant IS NULL')
    rows = cursor.fetchall()

    updated = 0
    for path, rowid in rows:
        if not path:
            continue

        # Extract filename
        filename = Path(path).stem  # Get filename without extension

        # Try to match with variant: name-source-variant-count
        match = re.match(r'^(.+?)-([a-z0-9]{5})-(.+)-(\d+)$', filename, re.IGNORECASE)
        if match:
            name, source, variant, count = match.groups()
            cursor.execute('UPDATE battles SET variant = ? WHERE rowid = ?', (variant, rowid))
            updated += 1

    conn.commit()
    print(f'Updated {updated} battles with variant from path')

    # Check result
    cursor.execute('SELECT variant, COUNT(*) as cnt FROM battles GROUP BY variant ORDER BY cnt DESC LIMIT 15')
    print('\nNew variant distribution:')
    for row in cursor.fetchall():
        print(f'  {row[0]}: {row[1]}')

    conn.close()


if __name__ == "__main__":
    backfill_variants()
