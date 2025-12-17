"""
Fetch character name aliases from Danbooru-style booru sites.

This script queries the tag_aliases API to get all character name mappings
(e.g., may_(pokemon) -> haruka_(pokemon)) and saves them to a JSON file.

Usage:
    python cli/fetch_booru_aliases.py
"""

import json
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import requests

from core import config
from core.utils import get_sources
from extractors.crawler_utils import RateLimiter


def load_cookies(cookie_path: str) -> dict:
    """Load cookies from JSON file."""
    with open(cookie_path) as f:
        cookies_list = json.load(f)
    return {c['name']: c['value'] for c in cookies_list}


def fetch_all_character_aliases(
    base_url: str,
    cookies: dict,
    rate_limiter: RateLimiter,
    ip: str = "pokemon"
) -> dict:
    """
    Fetch all character name aliases for a given IP from a Danbooru-style booru.

    Args:
        base_url: Base URL of the booru
        cookies: Authentication cookies
        rate_limiter: Rate limiter instance
        ip: IP name (e.g., 'pokemon', 'dragonball')

    Returns:
        Dict mapping antecedent names to consequent names
    """
    aliases = {}
    page = 1
    per_page = 100
    total_fetched = 0

    print(f"Fetching {ip} character aliases from {base_url}...")

    while True:
        # Rate limit
        rate_limiter.wait_sync(base_url)

        # Query for aliases with IP copyright tag
        url = f"{base_url}/tag_aliases.json"
        params = {
            'search[consequent_tag][post_count_gte]': 1,  # Only get aliases that are actually used
            'search[status]': 'active',  # Only active aliases
            'limit': per_page,
            'page': page
        }

        print(f"  Fetching page {page}...", end='', flush=True)

        try:
            response = requests.get(url, params=params, cookies=cookies, timeout=30)
            response.raise_for_status()

            data = response.json()

            if not data:
                print(" no more results")
                break

            # Filter for IP-related aliases
            page_aliases = 0
            for alias in data:
                antecedent = alias.get('antecedent_name', '')
                consequent = alias.get('consequent_name', '')

                # Check if it's a character from this IP (has _(<ip>) suffix)
                if f'_({ip})' in antecedent or f'_({ip})' in consequent:
                    aliases[antecedent] = consequent
                    page_aliases += 1

            total_fetched += page_aliases
            print(f" found {page_aliases} {ip} aliases (total: {total_fetched})")

            # If we got fewer results than per_page, we're done
            if len(data) < per_page:
                break

            page += 1

        except requests.RequestException as e:
            print(f"\n  Error fetching page {page}: {e}")
            break

    print(f"\nTotal {ip} character aliases found: {len(aliases)}")
    return aliases


def main():
    """Main function to fetch and save aliases."""
    # Get Danbooru-style booru config
    sources = get_sources('pokemon')
    danbooru_source = None
    for source in sources:
        if source.get('site_type') == 'danbooru':
            danbooru_source = source
            break

    if not danbooru_source:
        print("Error: Danbooru-style booru source not found in ip_sources.json")
        return

    # Load cookies
    cookie_path = danbooru_source.get('cookie_path', 'Input/cookies/booru/cookies.json')
    print(f"Loading cookies from: {cookie_path}")
    cookies = load_cookies(cookie_path)

    # Setup rate limiter using config.RATE_LIMITS
    base_url = danbooru_source['base_url']
    domain = urlparse(base_url).netloc
    rate_limit_delay = config.RATE_LIMITS.get(domain, 2.0)
    rate_limiter = RateLimiter(default_delay=rate_limit_delay)
    print(f"Rate limit: {rate_limit_delay}s between requests (from config.RATE_LIMITS)")

    # Fetch aliases
    base_url = danbooru_source['base_url']
    aliases = fetch_all_character_aliases(base_url, cookies, rate_limiter)

    # Save to file
    output_path = Path('Input/booru_character_aliases.json')
    output_data = {
        'source': danbooru_source['name'],
        'base_url': base_url,
        'fetched_at': time.strftime('%Y-%m-%d %H:%M:%S'),
        'total_aliases': len(aliases),
        'aliases': aliases
    }

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, indent=4, ensure_ascii=False)

    print(f"\nAliases saved to: {output_path}")

    # Print some examples
    print("\nExample aliases:")
    for _i, (antecedent, consequent) in enumerate(list(aliases.items())[:10]):
        print(f"  {antecedent} -> {consequent}")
    if len(aliases) > 10:
        print(f"  ... and {len(aliases) - 10} more")


if __name__ == '__main__':
    main()
