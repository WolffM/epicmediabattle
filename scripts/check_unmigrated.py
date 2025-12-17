"""Check for unmigrated files."""
import json
import os
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
OUTPUT_JSON = PROJECT_ROOT / 'output' / 'pokemon' / 'output.json'

with open(OUTPUT_JSON) as f:
    data = json.load(f)

unmigrated = []
for entry in data['results']:
    for img in entry.get('images', []):
        path = img.get('path', '')
        source = img.get('source', '')

        if source in ['bulba', 'fando']:
            fname = Path(path).stem  # Without extension
            # Check if filename matches old pattern (no variant): Name-source-count
            # NOT: Name-source-variant-count
            if re.match(r'^[^-]+-[a-z0-9]{5}-\d+$', fname, re.IGNORECASE):
                unmigrated.append({
                    'path': path,
                    'filename': Path(path).name,
                    'variant': img.get('variant'),
                    'exists': os.path.exists(path)
                })

print(f"Found {len(unmigrated)} unmigrated files")
for u in unmigrated[:10]:
    print(f"  {u['filename']} (variant={u['variant']}, exists={u['exists']})")
