"""
Main script to fetch character images.

Usage:
    python cli/fetch_images.py [--ip pokemon] [--num N] [--sources S] [--dry-run] [--async] [--getnew]

Modes:
    Default (replace mode): Only fetch images for variants where files are missing (deleted).
                           Existing images on disk are kept, only gaps are filled.
    --getnew:              Fetch new images up to the target count, regardless of disk state.
                           Use this to expand your collection beyond current counts.

Examples:
    python cli/fetch_images.py --ip pokemon --num 2 --sources 3 --async
    python cli/fetch_images.py --ip pokemon --async --getnew
"""

import argparse
import asyncio
import os
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core import config
from extractors.fetcher import ImageFetcher
from extractors.pipeline import (
    ImageProcessor,
    print_download_status,
    print_save_failure,
    print_save_success,
    print_search_results,
    print_variant_status,
)
from extractors.utils import (
    create_character_entry,
    ensure_directory,
    generate_summary_report,
    get_all_downloaded_urls,
    get_fetch_needs,
    load_characters,
    load_output_log,
    log_fetch_event,
    print_purge_report,
    purge_corrupted_images,
    save_output_log,
)


def process_character(
    fetcher: ImageFetcher,
    character: Dict,
    entry: Dict,
    target: Dict,
    ip: str,
    dry_run: bool = False,
    replace_mode: bool = True,
    global_urls: Optional[set] = None
) -> int:
    """
    Process a single character, fetching images as needed.

    For wiki-style sources (bulbapedia, fandom):
        Loop through wiki variants (base, anime, game)
    For tag-based sources (booru sites):
        Loop through all tag_variants sequentially

    Args:
        fetcher: ImageFetcher instance
        character: Character dictionary
        entry: Character's output log entry
        target: Target configuration
        ip: Intellectual property name
        dry_run: If True, simulate without downloading
        replace_mode: If True, only fetch for missing files. If False, fetch up to target.
        global_urls: Set of ALL URLs already downloaded across all characters (to prevent dupes)

    Returns:
        Number of new images fetched
    """
    name = character['name']
    group = character['group']
    output_dir = config.get_output_dir(ip, group)

    images_per_source = target['images_per_source']
    num_sources = target['num_sources']
    num_variants = target['name_variants']

    sources = config.get_sources(ip)

    # Get what we still need (pass sources for priority checking and output_dir for file existence checks)
    needs = get_fetch_needs(entry, replace_mode=replace_mode, available_sources=sources, output_dir=output_dir)

    if not needs['needs_more']:
        return 0
    # Merge character-specific URLs with global URLs to prevent cross-character duplicates
    existing_urls = needs['existing_urls']
    if global_urls:
        existing_urls = existing_urls | global_urls
    variant_source_counts = needs['variant_source_counts']

    new_images_count = 0
    sources_processed = 0

    # Create pipeline processor
    processor = ImageProcessor(ip, target, dry_run, replace_mode)

    # Process each source (up to num_sources)
    for source in sources:
        if sources_processed >= num_sources:
            break

        source_name = source['name']
        source_short = source['short_name']

        print(f"  === Source: {source_name} ===")

        # Check if this source uses tag variants (booru sites)
        if config.has_tag_variants(source):
            # Process tag-based variants (all variants, sequentially)
            tag_variants = config.get_tag_variants(source, num_variants=None)
            base_name = character['search_name'].replace(' ', '_')

            for tag_variant in tag_variants:
                variant_name = tag_variant['variant_name']
                tags_template = tag_variant['tags']

                # Check if we should skip this variant
                should_skip, existing_count, images_needed = processor.should_skip_variant(
                    variant_name, source_short, variant_source_counts
                )

                print_variant_status(
                    variant_name, existing_count, images_per_source,
                    images_needed, skip=should_skip
                )

                if should_skip:
                    continue

                if dry_run:
                    print("      [DRY RUN] Would search for images")
                    continue

                # Find images using tag variant
                found_images = fetcher.find_booru_images_with_tags(
                    source=source,
                    character_name=base_name,
                    tags_template=tags_template,
                    variant_name=variant_name,
                    max_images=images_needed,
                    existing_urls=existing_urls,
                    ip=ip
                )

                print_search_results(len(found_images) if found_images else 0, len(existing_urls))

                if not found_images:
                    log_fetch_event(config.LOG_FILE, character, source_short, variant_name,
                                   "NO_RESULTS", f"Search returned 0 images (checked {len(existing_urls)} existing URLs)")
                    continue

                log_fetch_event(config.LOG_FILE, character, source_short, variant_name,
                               "SEARCH", f"Found {len(found_images)} new images")

                # Download and save
                for img_info in found_images:
                    if images_needed <= 0:
                        break

                    url = img_info['url']
                    print_download_status(url)

                    image_data, extension = fetcher.download_image(url, img_info.get('source'))

                    if not image_data:
                        print_save_failure()
                        log_fetch_event(config.LOG_FILE, character, source_short, variant_name,
                                       "DOWNLOAD_FAIL", "Failed to download image", url=url)
                        continue

                    # Count images for this specific variant
                    variant_img_count = len([img for img in entry.get('images', [])
                                            if img.get('variant') == variant_name and img['source'] == source_short])
                    count = variant_img_count + 1

                    filename = processor.generate_filename(name, source_short, count, extension, variant_name)
                    output_path = os.path.join(output_dir, filename)

                    if processor.save_image(image_data, output_path):
                        print_save_success(filename)

                        processor.add_to_entry(entry, {
                            'filename': filename,
                            'source': source_short,
                            'url': url,
                            'page_url': img_info.get('page_url', ''),
                            'variant': variant_name
                        })

                        new_images_count += 1
                        images_needed -= 1

                        # Update tracking
                        variant_source_counts[(variant_name, source_short)] = variant_source_counts.get((variant_name, source_short), 0) + 1

                        log_fetch_event(config.LOG_FILE, character, source_short, variant_name,
                                       "SUCCESS", f"Downloaded {filename}", url=url)

                    time.sleep(config.REQUEST_DELAY)

        else:
            # Process wiki-style variants (base, anime, game)
            source_variants = config.get_source_variants(source, num_variants)

            for variant_suffix in source_variants:
                variant_label = processor.extract_variant_label(variant_suffix)

                # Check if we should skip this variant
                should_skip, existing_count, images_needed = processor.should_skip_variant(
                    variant_label, source_short, variant_source_counts
                )

                print_variant_status(
                    variant_label, existing_count, images_per_source,
                    images_needed, skip=should_skip
                )

                if should_skip:
                    continue

                if dry_run:
                    print("      [DRY RUN] Would search for images")
                    continue

                found_images = fetcher.find_images_for_character(
                    character=character,
                    variant_suffix=variant_suffix,
                    source=source,
                    max_images=images_needed,
                    existing_urls=existing_urls
                )

                print_search_results(len(found_images) if found_images else 0, len(existing_urls))

                if not found_images:
                    log_fetch_event(config.LOG_FILE, character, source_short, variant_label,
                                   "NO_RESULTS", f"Search returned 0 images (checked {len(existing_urls)} existing URLs)")
                    continue

                log_fetch_event(config.LOG_FILE, character, source_short, variant_label,
                               "SEARCH", f"Found {len(found_images)} new images")

                for img_info in found_images:
                    if images_needed <= 0:
                        break

                    url = img_info['url']
                    print_download_status(url)

                    image_data, extension = fetcher.download_image(url, img_info.get('source'))

                    if not image_data:
                        print_save_failure()
                        log_fetch_event(config.LOG_FILE, character, source_short, variant_label,
                                       "DOWNLOAD_FAIL", "Failed to download image", url=url)
                        continue

                    total_from_source = len([img for img in entry.get('images', [])
                                            if img['source'] == source_short])
                    count = total_from_source + 1
                    # Always include variant in filename for consistent naming
                    filename = processor.generate_filename(name, source_short, count, extension, variant_label)
                    output_path = os.path.join(output_dir, filename)

                    if processor.save_image(image_data, output_path):
                        print_save_success(filename)

                        processor.add_to_entry(entry, {
                            'filename': filename,
                            'source': source_short,
                            'url': url,
                            'page_url': img_info.get('page_url', ''),
                            'variant': variant_label
                        })

                        new_images_count += 1
                        images_needed -= 1

                        # Update tracking
                        variant_source_counts[(variant_label, source_short)] = variant_source_counts.get((variant_label, source_short), 0) + 1

                        log_fetch_event(config.LOG_FILE, character, source_short, variant_label,
                                       "SUCCESS", f"Downloaded {filename}", url=url)

                    time.sleep(config.REQUEST_DELAY)

        sources_processed += 1

    return new_images_count


def main(
    ip: str = "pokemon",
    images_per_source: int = 1,
    num_sources: int = 1,
    name_variants: int = 1,
    dry_run: bool = False,
    replace_mode: bool = True
):
    """
    Main function to orchestrate image fetching.

    Args:
        ip: Intellectual property (e.g., 'pokemon')
        images_per_source: Max images to fetch from each source
        num_sources: Number of sources to fetch from
        name_variants: Number of name variants to try (1=base, 2=+anime, 3=+game)
        dry_run: If True, only simulate without downloading
        replace_mode: If True (default), only fetch for missing files.
                      If False (--getnew), fetch up to target count.
    """
    mode_str = "REPLACE MODE (missing files only)" if replace_mode else "GETNEW MODE (up to target)"
    print("="*60)
    print("CHARACTER IMAGE FETCHER")
    print(f"IP: {ip.upper()}")
    print(f"Mode: {mode_str}")
    print(f"Target: {images_per_source} img/source x {num_sources} sources x {name_variants} variants")
    print("="*60)

    # Target configuration
    target = {
        'images_per_source': images_per_source,
        'num_sources': num_sources,
        'name_variants': name_variants
    }

    # Clear/create text log file
    if os.path.exists(config.LOG_FILE):
        os.remove(config.LOG_FILE)

    # Load characters
    print(f"\nLoading characters for {ip}...")
    characters = load_characters(ip)
    groups = {c['group'] for c in characters}
    num_groups = len(groups)
    # Check if using default group (flat character list)
    uses_default = config.DEFAULT_GROUP in groups and num_groups == 1
    if uses_default:
        print(f"Found {len(characters)} characters (flat list)")
    else:
        print(f"Found {len(characters)} characters across {num_groups} groups")

    if dry_run:
        print("\n[DRY RUN MODE - No images will be downloaded]\n")

    # Create output directories and setup output log
    ip_output_dir = config.get_ip_output_dir(ip)
    ensure_directory(ip_output_dir)
    output_log_path = os.path.join(ip_output_dir, "output.json")

    for group in groups:
        output_dir = config.get_output_dir(ip, group)
        ensure_directory(output_dir)
        if not uses_default:
            print(f"Created output directory: {output_dir}")

    # Load existing output log for resume capability
    print(f"\nLoading output log from {output_log_path}...")
    output_log = load_output_log(output_log_path)

    # Build global URL set to prevent cross-character duplicates
    global_urls = get_all_downloaded_urls(output_log)
    print(f"Loaded {len(global_urls)} existing URLs to prevent duplicates")

    # Count already complete characters
    complete_count = 0
    for char in characters:
        key = f"group{char['group']}_{char['name']}"
        if key in output_log:
            entry = output_log[key]
            # Update target in case it changed
            entry['target'] = target.copy()
            sources = config.get_sources(ip)
            char_output_dir = config.get_output_dir(ip, char['group'])
            needs = get_fetch_needs(entry, replace_mode=replace_mode, available_sources=sources, output_dir=char_output_dir)
            if not needs['needs_more']:
                complete_count += 1

    if complete_count > 0:
        print(f"Found {complete_count} already complete characters")

    # Initialize fetcher
    fetcher = ImageFetcher(ip)
    json_results = []

    # Process each character
    print(f"\n{'='*60}")
    print("FETCHING IMAGES")
    print(f"{'='*60}\n")

    for idx, character in enumerate(characters, 1):
        name = character['name']
        group = character['group']
        key = f"group{group}_{name}"

        print(f"[{idx}/{len(characters)}] Group {group} - {name}")

        # Get or create entry
        if key in output_log:
            entry = output_log[key]
            # Update target
            entry['target'] = target.copy()
        else:
            entry = create_character_entry(character, target)
            output_log[key] = entry

        # Check if already complete
        sources = config.get_sources(ip)
        output_dir = config.get_output_dir(ip, group)
        needs = get_fetch_needs(entry, replace_mode=replace_mode, available_sources=sources, output_dir=output_dir)
        if not needs['needs_more']:
            existing_images = len(entry.get('images', []))
            print(f"  [OK] Already complete ({existing_images} images)")
            json_results.append(entry)
            print()
            continue

        # Process character
        process_character(
            fetcher=fetcher,
            character=character,
            entry=entry,
            target=target,
            ip=ip,
            dry_run=dry_run,
            replace_mode=replace_mode,
            global_urls=global_urls
        )

        # Update global_urls with any new downloads from this character
        for img in entry.get('images', []):
            if img.get('url'):
                global_urls.add(img['url'])

        # Update result status
        total_images = len(entry.get('images', []))
        if total_images > 0:
            status_icon = "[OK]" if entry['result'] == 'success' else "[PARTIAL]"
            print(f"  {status_icon} Total: {total_images} images ({entry['result']})")
        else:
            print("  [FAIL] No images found")

        json_results.append(entry)
        print()

        # Save output log after each character (incremental saves)
        save_output_log(output_log_path, json_results)

    # Cleanup
    fetcher.close()

    # Final save of output log
    save_output_log(output_log_path, json_results)

    # Generate and display summary
    summary = generate_summary_report(json_results)
    print(summary)

    # Save summary to log
    with open(config.LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(summary)

    print(f"\nDetailed log saved to: {config.LOG_FILE}")
    print(f"JSON output log saved to: {output_log_path}")

    # Post-processing: Purge corrupted images
    if not dry_run:
        print("\nValidating downloaded images...")
        purge_stats = purge_corrupted_images(ip, output_log_path, dry_run=False)
        if purge_stats['corrupted'] > 0 or purge_stats['missing'] > 0:
            print_purge_report(purge_stats)
        else:
            print("  All images validated successfully.")


# =============================================================================
# Async Mode Functions
# =============================================================================

async def process_source_async(
    fetcher,  # AsyncImageFetcher
    characters: List[Dict],
    source: Dict,
    target: Dict,
    ip: str,
    output_log: Dict,
    dry_run: bool = False,
    replace_mode: bool = True,
    global_urls: Optional[set] = None
) -> Dict[str, Dict]:
    """
    Process all characters for a single source asynchronously.

    Args:
        fetcher: AsyncImageFetcher instance
        characters: List of character dictionaries
        source: Source configuration
        target: Target configuration
        ip: Intellectual property name
        output_log: Existing output log
        dry_run: If True, simulate without downloading
        replace_mode: If True, only fetch for missing files. If False, fetch up to target.
        global_urls: Set of ALL URLs already downloaded across all characters (to prevent dupes)

    Returns:
        Dict mapping character keys to their updated entries
    """
    source_name = source['name']
    source_short = source['short_name']
    images_per_source = target['images_per_source']
    num_variants = target['name_variants']

    results = {}

    # Create pipeline processor
    processor = ImageProcessor(ip, target, dry_run, replace_mode)

    for character in characters:
        name = character['name']
        group = character['group']
        key = f"group{group}_{name}"
        output_dir = config.get_output_dir(ip, group)

        # Get or create entry
        if key in output_log:
            entry = output_log[key].copy()
            entry['target'] = target.copy()
        else:
            entry = create_character_entry(character, target)

        sources_list = config.get_sources(ip)
        needs = get_fetch_needs(entry, replace_mode=replace_mode, available_sources=sources_list, output_dir=output_dir)
        # Merge character-specific URLs with global URLs to prevent cross-character duplicates
        existing_urls = needs['existing_urls']
        if global_urls:
            existing_urls = existing_urls | global_urls
        variant_source_counts = needs['variant_source_counts']

        # Check if this source uses tag variants (booru sites)
        if config.has_tag_variants(source):
            # Process tag-based variants (all variants, sequentially)
            tag_variants = config.get_tag_variants(source, num_variants=None)
            base_name = character['search_name'].replace(' ', '_')

            for tag_variant in tag_variants:
                variant_name = tag_variant['variant_name']
                tags_template = tag_variant['tags']

                # Check if we should skip this variant
                should_skip, existing_count, images_needed = processor.should_skip_variant(
                    variant_name, source_short, variant_source_counts
                )

                if should_skip:
                    print(f"  [{source_name}] {name} ({variant_name}): SKIP - already have {existing_count}/{images_per_source}")
                    continue

                print(f"  [{source_name}] {name} ({variant_name}): need {images_needed} more (have {existing_count}/{images_per_source})")

                if dry_run:
                    print("    [DRY RUN] Would search for images")
                    continue

                found_images = await fetcher.find_booru_images_with_tags(
                    source=source,
                    character_name=base_name,
                    tags_template=tags_template,
                    variant_name=variant_name,
                    max_images=images_needed,
                    existing_urls=existing_urls,
                    ip=ip
                )

                print_search_results(len(found_images) if found_images else 0, len(existing_urls))

                if not found_images:
                    log_fetch_event(config.LOG_FILE, character, source_short, variant_name,
                                   "NO_RESULTS", f"Search returned 0 images (checked {len(existing_urls)} existing URLs)")
                    continue

                log_fetch_event(config.LOG_FILE, character, source_short, variant_name,
                               "SEARCH", f"Found {len(found_images)} new images")

                for img_info in found_images:
                    if images_needed <= 0:
                        break

                    url = img_info['url']
                    print(f"    Downloading: {url[:60]}...")

                    image_data, extension = await fetcher.download_image(url, img_info.get('page_url'), img_info.get('source'))

                    if not image_data:
                        print_save_failure()
                        log_fetch_event(config.LOG_FILE, character, source_short, variant_name,
                                       "DOWNLOAD_FAIL", "Failed to download image", url=url)
                        continue

                    variant_img_count = len([img for img in entry.get('images', [])
                                            if img.get('variant') == variant_name and img['source'] == source_short])
                    count = variant_img_count + 1
                    filename = processor.generate_filename(name, source_short, count, extension, variant_name)
                    output_path = os.path.join(output_dir, filename)

                    if processor.save_image(image_data, output_path):
                        print_save_success(filename)

                        processor.add_to_entry(entry, {
                            'filename': filename,
                            'source': source_short,
                            'url': url,
                            'page_url': img_info.get('page_url', ''),
                            'variant': variant_name
                        })

                        images_needed -= 1

                        log_fetch_event(config.LOG_FILE, character, source_short, variant_name,
                                       "SUCCESS", f"Downloaded {filename}", url=url)

        else:
            # Process wiki-style variants (base, anime, game)
            source_variant_suffixes = config.get_source_variants(source, num_variants)

            for variant_suffix in source_variant_suffixes:
                variant_label = processor.extract_variant_label(variant_suffix)

                # Check if we should skip this variant
                should_skip, existing_count, images_needed = processor.should_skip_variant(
                    variant_label, source_short, variant_source_counts
                )

                if should_skip:
                    print(f"  [{source_name}] {name} ({variant_label}): SKIP - already have {existing_count}/{images_per_source}")
                    continue

                print(f"  [{source_name}] {name} ({variant_label}): need {images_needed} more (have {existing_count}/{images_per_source})")

                if dry_run:
                    print("    [DRY RUN] Would search for images")
                    continue

                found_images = await fetcher.find_images_for_character(
                    character=character,
                    variant_suffix=variant_suffix,
                    source=source,
                    max_images=images_needed,
                    existing_urls=existing_urls
                )

                print_search_results(len(found_images) if found_images else 0, len(existing_urls))

                if not found_images:
                    log_fetch_event(config.LOG_FILE, character, source_short, variant_label,
                                   "NO_RESULTS", f"Search returned 0 images (checked {len(existing_urls)} existing URLs)")
                    continue

                log_fetch_event(config.LOG_FILE, character, source_short, variant_label,
                               "SEARCH", f"Found {len(found_images)} new images")

                for img_info in found_images:
                    if images_needed <= 0:
                        break

                    url = img_info['url']
                    print(f"    Downloading: {url[:60]}...")

                    image_data, extension = await fetcher.download_image(url, img_info.get('page_url'), img_info.get('source'))

                    if not image_data:
                        print_save_failure()
                        log_fetch_event(config.LOG_FILE, character, source_short, variant_label,
                                       "DOWNLOAD_FAIL", "Failed to download image", url=url)
                        continue

                    total_from_source = len([img for img in entry.get('images', [])
                                            if img['source'] == source_short])
                    count = total_from_source + 1
                    # Always include variant in filename for consistent naming
                    filename = processor.generate_filename(name, source_short, count, extension, variant_label)
                    output_path = os.path.join(output_dir, filename)

                    if processor.save_image(image_data, output_path):
                        print_save_success(filename)

                        processor.add_to_entry(entry, {
                            'filename': filename,
                            'source': source_short,
                            'url': url,
                            'page_url': img_info.get('page_url', ''),
                            'variant': variant_label
                        })

                        images_needed -= 1

                        log_fetch_event(config.LOG_FILE, character, source_short, variant_label,
                                       "SUCCESS", f"Downloaded {filename}", url=url)

        results[key] = entry

    return results


async def main_async(
    ip: str = "pokemon",
    images_per_source: int = 1,
    num_sources: int = 1,
    name_variants: int = 1,
    dry_run: bool = False,
    replace_mode: bool = True
):
    """
    Async main function to orchestrate parallel image fetching.

    Each source runs as an independent async task.

    Args:
        replace_mode: If True (default), only fetch for missing files.
                      If False (--getnew), fetch up to target count.
    """
    from extractors.async_fetcher import AsyncImageFetcher

    mode_str = "REPLACE MODE (missing files only)" if replace_mode else "GETNEW MODE (up to target)"
    print("="*60)
    print("CHARACTER IMAGE FETCHER (ASYNC MODE)")
    print(f"IP: {ip.upper()}")
    print(f"Mode: {mode_str}")
    print(f"Target: {images_per_source} img/source x {num_sources} sources x {name_variants} variants")
    print("="*60)

    target = {
        'images_per_source': images_per_source,
        'num_sources': num_sources,
        'name_variants': name_variants
    }

    # Load characters
    print(f"\nLoading characters for {ip}...")
    characters = load_characters(ip)
    groups = {c['group'] for c in characters}
    num_groups = len(groups)
    # Check if using default group (flat character list)
    uses_default = config.DEFAULT_GROUP in groups and num_groups == 1
    if uses_default:
        print(f"Found {len(characters)} characters (flat list)")
    else:
        print(f"Found {len(characters)} characters across {num_groups} groups")

    if dry_run:
        print("\n[DRY RUN MODE - No images will be downloaded]\n")

    # Create output directories
    ip_output_dir = config.get_ip_output_dir(ip)
    ensure_directory(ip_output_dir)
    output_log_path = os.path.join(ip_output_dir, "output.json")

    for group in groups:
        output_dir = config.get_output_dir(ip, group)
        ensure_directory(output_dir)

    # Load existing output log
    print(f"Loading output log from {output_log_path}...")
    output_log = load_output_log(output_log_path)

    # Build global URL set to prevent cross-character duplicates
    global_urls = get_all_downloaded_urls(output_log)
    print(f"Loaded {len(global_urls)} existing URLs to prevent duplicates")

    # Get sources to process
    all_sources = config.get_sources(ip)
    sources_to_use = all_sources[:num_sources]

    print(f"\n{'='*60}")
    print(f"FETCHING IMAGES (PARALLEL - {len(sources_to_use)} sources)")
    print(f"{'='*60}\n")

    # Process sources in parallel
    async with AsyncImageFetcher(ip) as fetcher:
        tasks = []
        for source in sources_to_use:
            print(f"Starting worker for: {source['name']}")
            task = asyncio.create_task(
                process_source_async(
                    fetcher=fetcher,
                    characters=characters,
                    source=source,
                    target=target,
                    ip=ip,
                    output_log=output_log,
                    dry_run=dry_run,
                    replace_mode=replace_mode,
                    global_urls=global_urls
                )
            )
            tasks.append(task)

        # Wait for all sources to complete
        results = await asyncio.gather(*tasks)

    # Merge results from all sources
    merged_results = {}
    for source_results in results:
        for key, entry in source_results.items():
            if key in merged_results:
                # Merge images from this source into existing entry
                existing_entry = merged_results[key]
                existing_urls = {img['url'] for img in existing_entry.get('images', [])}
                for img in entry.get('images', []):
                    if img['url'] not in existing_urls:
                        existing_entry['images'].append(img)
                        existing_urls.add(img['url'])
            else:
                merged_results[key] = entry

    # Convert to list and save
    json_results = list(merged_results.values())
    save_output_log(output_log_path, json_results)

    # Generate and display summary
    summary = generate_summary_report(json_results)
    print(summary)

    with open(config.LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(summary)

    print(f"\nDetailed log saved to: {config.LOG_FILE}")
    print(f"JSON output log saved to: {output_log_path}")

    # Post-processing: Purge corrupted images
    if not dry_run:
        print("\nValidating downloaded images...")
        purge_stats = purge_corrupted_images(ip, output_log_path, dry_run=False)
        if purge_stats['corrupted'] > 0 or purge_stats['missing'] > 0:
            print_purge_report(purge_stats)
        else:
            print("  All images validated successfully.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Fetch character images from multiple sources",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Modes:
  Default (replace): Only fetch images for variants where files are missing.
  --getnew:          Fetch new images up to the target count.

Examples:
  python fetch_images.py --ip genshin_impact "afk_(series)" -n 1 -s 4 --async  # Multiple IPs, 1 img from 4 sources
  python fetch_images.py --ip pokemon --num 2 --sources 3 --async              # 2 images from 3 sources
  python fetch_images.py --ip pokemon --async --getnew                         # Get new images (all sources)
        """
    )
    parser.add_argument(
        "--ip",
        type=str,
        nargs='+',
        default=None,
        help="Intellectual property to fetch images for (can specify multiple, default: all IPs in config)"
    )
    parser.add_argument(
        "--num", "-n",
        type=int,
        default=1,
        help="Max images to fetch per source (default: 1)"
    )
    parser.add_argument(
        "--sources", "-s",
        type=int,
        default=None,
        help="Number of sources to fetch from (default: all sources)"
    )
    parser.add_argument(
        "--variants", "-v",
        type=int,
        default=1,
        help="Name variants to try: 1=base, 2=+anime, 3=+game (default: 1)"
    )
    # Keep positional args for backwards compatibility but they come AFTER --ip
    parser.add_argument(
        "images_per_source",
        type=int,
        nargs='?',
        default=None,
        help="(Legacy) Max images per source - prefer using --num"
    )
    parser.add_argument(
        "num_sources",
        type=int,
        nargs='?',
        default=None,
        help="(Legacy) Number of sources - prefer using --sources"
    )
    parser.add_argument(
        "name_variants",
        type=int,
        nargs='?',
        default=None,
        help="(Legacy) Name variants - prefer using --variants"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate the fetch process without actually downloading images"
    )
    parser.add_argument(
        "--async",
        dest="use_async",
        action="store_true",
        help="Use async mode with parallel source processing"
    )
    parser.add_argument(
        "--getnew",
        action="store_true",
        help="Fetch new images up to target count (default: only replace missing files)"
    )

    args = parser.parse_args()

    # Default is replace mode (only fetch for missing files)
    # --getnew disables replace mode to fetch up to target
    replace_mode = not args.getnew

    # Resolve arguments: named args take precedence over legacy positional args
    # Use sensible defaults if both named and positional are None
    images_per_source = args.num if args.images_per_source is None else args.images_per_source
    num_sources = args.sources if args.num_sources is None else args.num_sources
    name_variants = args.variants if args.name_variants is None else args.name_variants

    # Default num_sources to 99 (effectively all) if still None
    if num_sources is None:
        num_sources = 99

    # Get list of IPs to process
    if args.ip:
        ips_to_process = args.ip  # Already a list due to nargs='+'
    else:
        # Process all IPs in config
        ips_to_process = list(config.IP_SOURCES.keys())
        print(f"No --ip specified, will process all IPs: {', '.join(ips_to_process)}\n")

    try:
        for ip in ips_to_process:
            if len(ips_to_process) > 1:
                print(f"\n{'#'*60}")
                print(f"# PROCESSING IP: {ip.upper()}")
                print(f"{'#'*60}\n")

            if args.use_async:
                # Run async version
                asyncio.run(main_async(
                    ip=ip,
                    images_per_source=images_per_source,
                    num_sources=num_sources,
                    name_variants=name_variants,
                    dry_run=args.dry_run,
                    replace_mode=replace_mode
                ))
            else:
                # Run sync version
                main(
                    ip=ip,
                    images_per_source=images_per_source,
                    num_sources=num_sources,
                    name_variants=name_variants,
                    dry_run=args.dry_run,
                    replace_mode=replace_mode
                )

            # After --getnew, run duplicate check to merge metadata
            if args.getnew and not args.dry_run:
                try:
                    from scripts.migrate_duplicates import run_post_fetch_dedup
                    run_post_fetch_dedup(ip)
                except ImportError:
                    print("\n[Warning] Could not import migrate_duplicates for post-fetch dedup")
                except Exception as e:
                    print(f"\n[Warning] Post-fetch dedup failed: {e}")

    except KeyboardInterrupt:
        print("\n\nProcess interrupted by user. Exiting...")
        sys.exit(0)
    except Exception as e:
        print(f"\n\nUnexpected error: {e!s}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
