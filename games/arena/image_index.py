"""
Image index for scanning and cataloging images from the Output folder.
Parses filenames to extract metadata: name, source, variant, etc.
"""

import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional

# Add parent paths for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from core.utils import DEFAULT_GROUP, get_gen_aliases, get_universes, get_variant_to_group

# Path to Output folder (relative to games/arena/)
OUTPUT_DIR = Path(__file__).parent.parent.parent / "Output"


@dataclass
class ImageMetadata:
    """Metadata for a single image."""
    path: str           # Full file path
    name: str           # Character name
    group_name: str     # Generation/group (e.g., "1", "2", "archeus")
    source: str         # Source short name (e.g., "dbwiki", "bulba")
    variant: Optional[str]  # Variant name (e.g., "super_saiyan", "base") or None
    filename: str       # Just the filename
    ip: str             # IP name (e.g., "pokemon", "genshin_impact")
    universe: str       # Universe name (e.g., "nintendo", "hoyoverse")
    display_group: Optional[str] = None   # Normalized gen display name (e.g., "8A" for "archeus")
    variant_group: Optional[str] = None   # Variant group (e.g., "AI", "artist", "niche")

    def __post_init__(self):
        # Set display_group from gen aliases
        if self.display_group is None:
            gen_aliases = get_gen_aliases(self.ip)
            self.display_group = gen_aliases.get(self.group_name, self.group_name)
        # Set variant_group from variant
        if self.variant_group is None and self.variant:
            variant_to_group = get_variant_to_group(self.ip)
            self.variant_group = variant_to_group.get(self.variant)

    def to_dict(self) -> Dict:
        return asdict(self)


class ImageIndex:
    """Index of all images in the Output folder."""

    def __init__(self):
        self.images: List[ImageMetadata] = []
        self._by_universe: Dict[str, List[ImageMetadata]] = {}
        self._by_ip: Dict[str, List[ImageMetadata]] = {}
        self._by_group: Dict[str, Dict[str, List[ImageMetadata]]] = {}
        self._by_name: Dict[str, List[ImageMetadata]] = {}

    def scan(self, output_dir: Path = None):
        """
        Scan the Output folder and index all images.

        Expected structure: Output/{universe}/{ip}/{group}/{filename}
        Filename format: {name}-{source}-{variant}-{count}.{ext}
                     or: {name}-{source}-{count}.{ext}
        """
        if output_dir is None:
            output_dir = OUTPUT_DIR

        self.images = []
        self._by_universe = {}
        self._by_ip = {}
        self._by_group = {}
        self._by_name = {}

        if not output_dir.exists():
            print(f"Output directory not found: {output_dir}")
            return

        # Get known universes from config
        known_universes = set(get_universes())

        # Scan universe folders
        for universe_dir in output_dir.iterdir():
            if not universe_dir.is_dir():
                continue

            universe_name = universe_dir.name

            # Check if this is a universe folder
            if universe_name in known_universes:
                # New structure: Output/{universe}/{ip}/{group}/...
                self._scan_universe(universe_dir, universe_name)
            else:
                # Legacy structure: Output/{ip}/{group}/... (assume "nintendo" universe)
                # Only if it looks like an IP folder (has group subfolders)
                has_group_folders = any(
                    d.is_dir() and not d.name.endswith('.json')
                    for d in universe_dir.iterdir()
                )
                if has_group_folders:
                    self._scan_ip(universe_dir, universe_name, "nintendo")

    def _scan_universe(self, universe_dir: Path, universe_name: str):
        """Scan an entire universe folder."""
        self._by_universe[universe_name] = []

        for ip_dir in universe_dir.iterdir():
            if not ip_dir.is_dir():
                continue

            ip_name = ip_dir.name
            self._scan_ip(ip_dir, ip_name, universe_name)

    def _scan_ip(self, ip_dir: Path, ip_name: str, universe_name: str):
        """Scan an IP folder for images."""
        if ip_name not in self._by_ip:
            self._by_ip[ip_name] = []
        if ip_name not in self._by_group:
            self._by_group[ip_name] = {}

        # Scan group folders
        for group_dir in ip_dir.iterdir():
            if not group_dir.is_dir():
                continue

            # Skip output.json
            if group_dir.name == "output.json":
                continue

            group_name = group_dir.name
            if group_name not in self._by_group[ip_name]:
                self._by_group[ip_name][group_name] = []

            # Scan image files
            for img_file in group_dir.iterdir():
                if not img_file.is_file():
                    continue

                # Check if it's an image
                if img_file.suffix.lower() not in ['.png', '.jpg', '.jpeg', '.webp']:
                    continue

                # Parse filename
                metadata = self._parse_filename(img_file, ip_name, group_name, universe_name)
                if metadata:
                    self.images.append(metadata)

                    # Index by universe
                    if universe_name not in self._by_universe:
                        self._by_universe[universe_name] = []
                    self._by_universe[universe_name].append(metadata)

                    # Index by IP
                    self._by_ip[ip_name].append(metadata)
                    self._by_group[ip_name][group_name].append(metadata)

                    # Index by name
                    if metadata.name not in self._by_name:
                        self._by_name[metadata.name] = []
                    self._by_name[metadata.name].append(metadata)

    def _parse_filename(self, file_path: Path, ip: str, group: str, universe: str) -> Optional[ImageMetadata]:
        """
        Parse filename to extract metadata.

        Formats:
            {name}-{source}-{variant}-{count}.{ext}  (e.g., Goku-dbwiki-super_saiyan-1.jpg)
            {name}-{source}-{count}.{ext}            (e.g., Vegeta-bulba-1.png)
        """
        filename = file_path.stem  # Remove extension

        # Try to match with variant: name-source-variant-count
        # Source pattern: 5-8 alphanumeric chars (bulba, fando, dbwiki)
        # Variant pattern: more permissive to catch artistA, artistB2, etc.
        match_with_variant = re.match(
            r'^(.+?)-([a-z0-9]{5,8})-(.+)-(\d+)$',
            filename,
            re.IGNORECASE
        )

        if match_with_variant:
            name, source, variant, count = match_with_variant.groups()
            return ImageMetadata(
                path=str(file_path),
                name=name,
                group_name=group,
                source=source,
                variant=variant,
                filename=file_path.name,
                ip=ip,
                universe=universe
            )

        # Try to match without variant: name-source-count
        match_no_variant = re.match(
            r'^(.+?)-([a-z0-9]{5,8})-(\d+)$',
            filename,
            re.IGNORECASE
        )

        if match_no_variant:
            name, source, count = match_no_variant.groups()
            return ImageMetadata(
                path=str(file_path),
                name=name,
                group_name=group,
                source=source,
                variant=None,
                filename=file_path.name,
                ip=ip,
                universe=universe
            )

        # Couldn't parse - log and skip
        print(f"Could not parse filename: {filename}")
        return None

    def get_universes(self) -> List[str]:
        """Get list of all universes with images."""
        return list(self._by_universe.keys())

    def get_ips(self, universe: str = None) -> List[str]:
        """
        Get list of all IPs, optionally filtered by universe.

        Args:
            universe: If provided, only return IPs from this universe
        """
        if universe:
            # Filter IPs that have images in this universe
            ips = set()
            for img in self._by_universe.get(universe, []):
                ips.add(img.ip)
            return sorted(ips)
        return list(self._by_ip.keys())

    def get_groups(self, ip: str, include_default: bool = False) -> List[str]:
        """
        Get list of groups for an IP.

        Args:
            ip: IP name
            include_default: If False, excludes DEFAULT_GROUP from results.
                           Set True for internal operations, False for UI display.
        """
        if ip not in self._by_group:
            return []

        groups = list(self._by_group[ip].keys())

        # Filter out default group for UI purposes
        if not include_default:
            groups = [g for g in groups if g != DEFAULT_GROUP]

        # Sort numerically if possible, otherwise alphabetically
        def sort_key(x):
            try:
                return (0, int(x))
            except ValueError:
                return (1, x)
        return sorted(groups, key=sort_key)

    def has_groups(self, ip: str) -> bool:
        """
        Check if an IP has meaningful groups (not just DEFAULT_GROUP).

        Returns:
            True if IP has groups other than DEFAULT_GROUP
        """
        groups = self.get_groups(ip, include_default=False)
        return len(groups) > 0

    def get_characters(self, ip: str, group: str = None) -> List[str]:
        """Get list of unique character names."""
        names = set()
        if group:
            if ip in self._by_group and group in self._by_group[ip]:
                for img in self._by_group[ip][group]:
                    names.add(img.name)
        else:
            if ip in self._by_ip:
                for img in self._by_ip[ip]:
                    names.add(img.name)
        return sorted(names)

    def get_sources(self, ip: str, group: str = None, character: str = None) -> List[str]:
        """Get list of unique sources."""
        sources = set()
        for img in self._filter_images(ip=ip, group=group, character=character):
            sources.add(img.source)
        return sorted(sources)

    def get_variants(self, ip: str, group: str = None, character: str = None, source: str = None) -> List[str]:
        """Get list of unique variants."""
        variants = set()
        for img in self._filter_images(ip=ip, group=group, character=character, source=source):
            if img.variant:
                variants.add(img.variant)
        return sorted(variants)

    def get_variant_groups(self, ip: str, group: str = None, character: str = None, source: str = None) -> List[str]:
        """Get list of unique variant groups (AI, artist, niche)."""
        groups = set()
        for img in self._filter_images(ip=ip, group=group, character=character, source=source):
            if img.variant_group:
                groups.add(img.variant_group)
        return sorted(groups)

    def _filter_images(
        self,
        universe: str = None,
        ip: str = None,
        group: str = None,
        character: str = None,
        source: str = None,
        variant: str = None,
        variant_group: str = None
    ) -> List[ImageMetadata]:
        """Filter images by criteria."""
        result = self.images

        if universe:
            result = [img for img in result if img.universe == universe]
        if ip:
            result = [img for img in result if img.ip == ip]
        if group:
            result = [img for img in result if img.group_name == group]
        if character:
            result = [img for img in result if img.name == character]
        if source:
            result = [img for img in result if img.source == source]
        if variant:
            result = [img for img in result if img.variant == variant]
        if variant_group:
            result = [img for img in result if img.variant_group == variant_group]

        return result

    def get_images(
        self,
        universe: str = None,
        ip: str = None,
        group: str = None,
        character: str = None,
        source: str = None,
        variant: str = None,
        variant_group: str = None
    ) -> List[Dict]:
        """Get images matching the filter criteria as dicts."""
        images = self._filter_images(universe, ip, group, character, source, variant, variant_group)
        return [img.to_dict() for img in images]

    def get_image_count(
        self,
        universe: str = None,
        ip: str = None,
        group: str = None,
        character: str = None,
        source: str = None,
        variant: str = None,
        variant_group: str = None
    ) -> int:
        """Get count of images matching filter."""
        return len(self._filter_images(universe, ip, group, character, source, variant, variant_group))


# Global index instance
_index: Optional[ImageIndex] = None


def get_index() -> ImageIndex:
    """Get or create the global image index."""
    global _index
    if _index is None:
        _index = ImageIndex()
        _index.scan()
    return _index


def refresh_index() -> ImageIndex:
    """Force refresh of the image index."""
    global _index
    _index = ImageIndex()
    _index.scan()
    return _index
