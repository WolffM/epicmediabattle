"""
Image processing pipeline - shared logic for sync and async fetching.

This module contains the shared processing logic extracted from fetch_images.py
to eliminate duplication between sync and async code paths.
"""

import os
from typing import Dict, Optional, Tuple


class ImageProcessor:
    """
    Shared image processing logic for both sync and async pipelines.

    This class handles the common logic for:
    - Processing tag variants (booru sites)
    - Processing wiki variants (bulbapedia, fandom)
    - Downloading and saving images
    - Updating entries and tracking
    """

    def __init__(
        self,
        ip: str,
        target: Dict,
        dry_run: bool = False,
        replace_mode: bool = True
    ):
        """
        Initialize the image processor.

        Args:
            ip: Intellectual property name (e.g., 'pokemon')
            target: Target configuration dict
            dry_run: If True, simulate without downloading
            replace_mode: If True, only fetch for missing files
        """
        self.ip = ip
        self.target = target
        self.dry_run = dry_run
        self.replace_mode = replace_mode

        self.images_per_source = target['images_per_source']
        self.num_variants = target['name_variants']

    def should_skip_variant(
        self,
        variant_name: str,
        source_short: str,
        variant_source_counts: Dict[Tuple[str, str], int]
    ) -> Tuple[bool, int, int]:
        """
        Check if we should skip fetching for this variant/source combination.

        Args:
            variant_name: Name of the variant
            source_short: Short source name
            variant_source_counts: Dict tracking counts per (variant, source)

        Returns:
            Tuple of (should_skip, existing_count, images_needed)
        """
        existing_count = variant_source_counts.get((variant_name, source_short), 0)
        images_needed = self.images_per_source - existing_count

        should_skip = images_needed <= 0
        return should_skip, existing_count, images_needed

    def save_image(
        self,
        image_data: bytes,
        output_path: str
    ) -> bool:
        """
        Save image data to disk.

        Args:
            image_data: Image bytes to save
            output_path: Full path where to save the image

        Returns:
            True if successful, False otherwise
        """
        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(output_path), exist_ok=True)

            with open(output_path, 'wb') as f:
                f.write(image_data)
            return True
        except Exception as e:
            print(f"    [FAIL] Failed to save: {e}")
            return False

    def generate_filename(
        self,
        name: str,
        source_short: str,
        count: int,
        extension: str,
        variant_name: Optional[str] = None
    ) -> str:
        """
        Generate standardized image filename.

        Args:
            name: Character name
            source_short: Short source name
            count: Image count for this character/source
            extension: File extension (with dot)
            variant_name: Optional variant name to include

        Returns:
            Generated filename
        """
        from extractors.utils import generate_image_filename
        return generate_image_filename(name, source_short, count, extension, variant_name)

    def add_to_entry(
        self,
        entry: Dict,
        image_info: Dict
    ) -> None:
        """
        Add image info to character entry.

        Args:
            entry: Character entry dict to update
            image_info: Image information to add
        """
        # Import here to avoid circular dependency
        from extractors.utils import add_image_to_entry
        add_image_to_entry(entry, image_info)

    def extract_variant_label(self, variant_suffix: str) -> str:
        """
        Extract variant label from suffix.

        Args:
            variant_suffix: Variant suffix (e.g., '', '_(anime)', '_(game)')

        Returns:
            Variant label (e.g., 'base', 'anime', 'game')
        """
        # Import here to avoid circular dependency
        from extractors.utils import extract_variant_label
        return extract_variant_label(variant_suffix)

def print_variant_status(
    variant_name: str,
    existing_count: int,
    images_per_source: int,
    images_needed: int,
    skip: bool = False
):
    """
    Print standardized status message for variant processing.

    Args:
        variant_name: Name of the variant
        existing_count: Number of existing images
        images_per_source: Target images per source
        images_needed: Number of images needed
        skip: Whether we're skipping this variant
    """
    if skip:
        print(f"    [{variant_name}] SKIP - already have {existing_count}/{images_per_source}")
    else:
        print(f"    [{variant_name}] need {images_needed} more (have {existing_count}/{images_per_source})...")


def print_download_status(url: str, max_len: int = 80):
    """
    Print standardized download status message.

    Args:
        url: URL being downloaded
        max_len: Maximum length to display
    """
    print(f"      Downloading: {url[:max_len]}...")


def print_search_results(found_count: int, existing_urls_count: int):
    """
    Print standardized search results message.

    Args:
        found_count: Number of images found
        existing_urls_count: Total existing URLs checked
    """
    if found_count > 0:
        print(f"      Found {found_count} candidate images")
    else:
        print(f"      No new images found (checked {existing_urls_count} existing URLs)")


def print_save_success(filename: str):
    """Print standardized save success message."""
    print(f"      [OK] Saved: {filename}")


def print_save_failure():
    """Print standardized save failure message."""
    print("      Failed to download")
