"""
Image fetcher with multi-source, multi-image support (sync version).
"""

import os
import re
import sys
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import quote, urljoin

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import config
from core.utils import build_booru_search_url, get_fandom_image_by_filename
from extractors.base_fetcher import BaseFetcher, substitute_tag_placeholders
from extractors.utils import get_extension_from_url, get_image_extension, is_url_valid_image


class ImageFetcher(BaseFetcher):
    """Fetches character images from multiple sources with multi-image support."""

    def __init__(self, ip: str):
        """
        Initialize the ImageFetcher.

        Args:
            ip: The intellectual property (e.g., 'pokemon')
        """
        sources = config.get_sources(ip)
        super().__init__(sources, ip)

        self.session = requests.Session()
        self.session.headers.update({'User-Agent': config.USER_AGENT})

    def find_images_for_character(
        self,
        character: dict,
        variant_suffix: str,
        source: dict,
        max_images: int,
        existing_urls: Set[str]
    ) -> List[Dict]:
        """
        Find multiple images for a character from a specific source.

        Args:
            character: Character dictionary with name and search_name
            variant_suffix: Suffix to append (e.g., '', '_(anime)', '_(game)')
            source: Source configuration dictionary
            max_images: Maximum number of images to find
            existing_urls: Set of URLs already fetched (to avoid dupes)

        Returns:
            List of image info dicts with keys: url, page_url, variant
        """
        source_name = source['name']
        search_name = character['search_name'].replace(' ', '_') + variant_suffix

        # Determine variant label
        if variant_suffix == '_(anime)':
            variant = 'anime'
        elif variant_suffix == '_(game)':
            variant = 'game'
        else:
            variant = 'base'

        # Route based on site_type or source_name for backwards compatibility
        site_type = source.get('site_type')

        if site_type == 'booru':
            # Booru sites use base character name (no wiki variants)
            base_name = character['search_name'].replace(' ', '_')
            return self._find_booru_images(source, base_name, variant, max_images, existing_urls)
        elif source_name == 'bulbapedia':
            return self._find_bulbapedia_images(search_name, variant, max_images, existing_urls)
        elif source_name == 'fandom':
            return self._find_fandom_images(search_name, variant, max_images, existing_urls)
        elif site_type == 'booru_scrape':
            # Legacy: Booru scraping without API
            base_name = character['search_name'].replace(' ', '_')
            return self._find_booru_scrape_images(base_name, variant, max_images, existing_urls)
        else:
            return []

    def _find_bulbapedia_images(
        self,
        search_name: str,
        variant: str,
        max_images: int,
        existing_urls: Set[str]
    ) -> List[Dict]:
        """
        Find images from Bulbapedia page with legacy strategies.

        This wraps the base class method and adds legacy strategies.
        """
        source = {
            'name': 'bulbapedia',
            'base_url': 'https://bulbapedia.bulbagarden.net',
            'url_template': 'https://bulbapedia.bulbagarden.net/wiki/{character}'
        }

        # Use base class method
        images = self.find_bulbapedia_images(search_name, variant, source, max_images)

        # Add additional legacy strategies if needed
        base_url = "https://bulbapedia.bulbagarden.net"
        page_url = f"{base_url}/wiki/{quote(search_name)}"

        # If we didn't find enough, try File: page strategy
        if len(images) < max_images:
            html = self._fetch_page(page_url)
            if html:
                soup = BeautifulSoup(html, 'html.parser')
                file_links = soup.find_all('a', href=re.compile(r'/wiki/File:.*\.(png|jpg|jpeg|webp)', re.IGNORECASE))

                for link in file_links:
                    if len(images) >= max_images:
                        break

                    href = link.get('href', '')
                    file_page_url = urljoin(base_url, href)
                    img_url = self._get_bulbapedia_file_image(file_page_url)

                    if img_url and img_url not in existing_urls and is_url_valid_image(img_url):
                        images.append({
                            'url': img_url,
                            'page_url': page_url,
                            'variant': variant,
                            'source': 'bulbapedia'
                        })
                        existing_urls.add(img_url)

        # Filter existing URLs and update set
        new_images = []
        for img in images:
            if img['url'] not in existing_urls:
                new_images.append(img)
                existing_urls.add(img['url'])
            elif img in images and img['url'] in existing_urls:
                # Already added above
                new_images.append(img)

        return new_images[:max_images]

    def _get_bulbapedia_file_image(self, file_page_url: str) -> Optional[str]:
        """
        Get the actual image URL from a Bulbapedia File: page.
        """
        try:
            response = self.session.get(file_page_url, timeout=config.REQUEST_TIMEOUT)
            if response.status_code != 200:
                return None

            soup = BeautifulSoup(response.content, 'html.parser')

            # Look for the full image link
            full_media = soup.find('div', class_='fullMedia')
            if full_media:
                link = full_media.find('a')
                if link and link.get('href'):
                    return urljoin(file_page_url, link['href'])

            # Alternative: look for the main image
            file_img = soup.find('img', class_='mw-file-element')
            if file_img and file_img.get('src'):
                return self._resolve_bulbapedia_image(file_img['src'], 'https://bulbapedia.bulbagarden.net')

        except Exception:
            pass

        return None

    def _find_fandom_images(
        self,
        search_name: str,
        variant: str,
        max_images: int,
        existing_urls: Set[str]
    ) -> List[Dict]:
        """
        Find images from Pokemon Fandom wiki with legacy strategies.

        This wraps the base class method and adds legacy strategies.
        """
        source = {
            'name': 'fandom',
            'base_url': 'https://pokemon.fandom.com',
            'url_template': 'https://pokemon.fandom.com/wiki/{character}'
        }

        # Use base class method
        images = self.find_fandom_images(search_name, variant, source, max_images)

        # Add additional legacy strategy for ?file= gallery links if needed
        base_url = "https://pokemon.fandom.com"
        page_url = f"{base_url}/wiki/{quote(search_name)}"

        if len(images) < max_images:
            html = self._fetch_page(page_url)
            if html:
                soup = BeautifulSoup(html, 'html.parser')
                gallery_links = soup.find_all('a', href=re.compile(r'\?file='))

                for link in gallery_links:
                    if len(images) >= max_images:
                        break

                    href = link.get('href', '')
                    match = re.search(r'\?file=([^&]+)', href)
                    if match:
                        from urllib.parse import unquote
                        filename = unquote(match.group(1).replace('+', ' '))
                        img_url = get_fandom_image_by_filename(filename)

                        if img_url and img_url not in existing_urls and is_url_valid_image(img_url):
                            images.append({
                                'url': img_url,
                                'page_url': page_url,
                                'variant': variant,
                                'source': 'fandom'
                            })
                            existing_urls.add(img_url)

        # Filter existing URLs and update set
        new_images = []
        for img in images:
            if img['url'] not in existing_urls:
                new_images.append(img)
                existing_urls.add(img['url'])
            elif img in images and img['url'] in existing_urls:
                # Already added above
                new_images.append(img)

        return new_images[:max_images]

    # =========================================================================
    # Booru methods (scraping-based)
    # =========================================================================

    def _find_booru_scrape_images(
        self,
        character_name: str,
        variant: str,
        max_images: int,
        existing_urls: Set[str]
    ) -> List[Dict]:
        """Find images from booru site using default tags (legacy method)."""
        default_tags = "{character_name}_({ip}) sort:score ( solo ~ 1girls ) -multiple_girls -multiple_females -male -animated -comic"
        return self.find_booru_scrape_images_with_tags(
            character_name, default_tags, variant, max_images, existing_urls
        )

    def find_booru_images_with_tags(
        self,
        source: dict,
        character_name: str,
        tags_template: str,
        variant_name: str,
        max_images: int,
        existing_urls: Set[str],
        ip: str = "pokemon"
    ) -> List[Dict]:
        """
        Find images from any booru site using custom tags.

        Handles both HTML scraping and Danbooru-style (API) boorus.

        Args:
            source: Source configuration dict
            character_name: Base character name (e.g., "May")
            tags_template: Tags template with {character_name} and {ip} placeholders
            variant_name: Name of this tag variant (e.g., "solo", "action")
            max_images: Maximum number of images to find
            existing_urls: Set of URLs already fetched (modified in place)
            ip: IP name for tag substitution (e.g., "pokemon")

        Returns:
            List of image info dicts with keys: url, page_url, variant
        """
        # Check if this is a Danbooru-style API booru
        if source.get('site_type') == 'booru':
            # Use the Danbooru API method
            return self._find_booru_images_with_tags(source, character_name, tags_template, variant_name, max_images, existing_urls, ip)
        else:
            # Use HTML scraping method (API if configured, otherwise scraping)
            return self.find_booru_scrape_images_with_tags(character_name, tags_template, variant_name, max_images, existing_urls, ip, source)

    def find_booru_scrape_images_with_tags(
        self,
        character_name: str,
        tags_template: str,
        variant_name: str,
        max_images: int,
        existing_urls: Set[str],
        ip: str = "pokemon",
        source: dict = None
    ) -> List[Dict]:
        """
        Find images from booru site using custom tags.

        Uses JSON API if api_key is configured, otherwise falls back to HTML scraping.

        Args:
            character_name: Base character name (e.g., "Goku")
            tags_template: Tags template with {character_name} and {ip} placeholders
            variant_name: Name of this tag variant (e.g., "super_saiyan", "base")
            max_images: Maximum number of images to find
            existing_urls: Set of URLs already fetched (modified in place)
            ip: IP name for tag substitution (e.g., "dragonball")
            source: Source config dict (optional, for API key access)

        Returns:
            List of image info dicts with keys: url, page_url, variant
        """
        # Check if we have API credentials
        if source and source.get('api_key') and source.get('user_id'):
            return self._find_booru_images_via_api(
                character_name, tags_template, variant_name,
                max_images, existing_urls, ip, source
            )

        # Fall back to HTML scraping
        return self._find_booru_images_via_scraping(
            character_name, tags_template, variant_name,
            max_images, existing_urls, ip
        )

    def _find_booru_images_via_api(
        self,
        character_name: str,
        tags_template: str,
        variant_name: str,
        max_images: int,
        existing_urls: Set[str],
        ip: str,
        source: dict
    ) -> List[Dict]:
        """Find images from booru site using JSON API."""
        found_images = []

        try:
            # Substitute placeholders into tags template
            tags = substitute_tag_placeholders(tags_template, character_name, ip)

            # Build API URL
            base_url = source.get('base_url', 'https://example.booru.org')
            api_url = source.get('api_url', f'{base_url}/index.php')
            api_key = source['api_key']
            user_id = source['user_id']

            params = {
                'page': 'dapi',
                's': 'post',
                'q': 'index',
                'tags': tags,
                'limit': max_images * 2,
                'json': 1,
                'api_key': api_key,
                'user_id': user_id
            }

            response = self.session.get(api_url, params=params, timeout=config.REQUEST_TIMEOUT)
            if response.status_code != 200:
                print(f"    Booru API returned status {response.status_code}")
                return []

            data = response.json()
            if not isinstance(data, list):
                return []

            for post in data:
                if len(found_images) >= max_images:
                    break

                file_url = post.get('file_url')
                if file_url and file_url not in existing_urls:
                    post_url = f"{base_url}/index.php?page=post&s=view&id={post.get('id', '')}"
                    found_images.append({
                        'url': file_url,
                        'page_url': post_url,
                        'variant': variant_name
                    })
                    existing_urls.add(file_url)

        except Exception as e:
            print(f"    Error fetching from Booru API: {e}")

        return found_images[:max_images]

    def _find_booru_images_via_scraping(
        self,
        character_name: str,
        tags_template: str,
        variant_name: str,
        max_images: int,
        existing_urls: Set[str],
        ip: str
    ) -> List[Dict]:
        """Find images from booru site using HTML scraping (legacy method)."""
        found_images = []

        try:
            # Substitute placeholders into tags template
            tags = substitute_tag_placeholders(tags_template, character_name, ip)
            search_url = self._build_booru_search_url_from_tags(tags)

            # Get more post URLs than needed to handle duplicates
            post_urls = self._get_booru_post_urls(search_url, max_images * 3)

            if not post_urls:
                return []

            # Stage 2: Get image URL from each post
            for post_url in post_urls:
                if len(found_images) >= max_images:
                    break

                img_url = self._get_booru_image_from_post(post_url)

                if img_url and img_url not in existing_urls:
                    found_images.append({
                        'url': img_url,
                        'page_url': post_url,
                        'variant': variant_name
                    })
                    existing_urls.add(img_url)

        except Exception as e:
            print(f"    Error fetching from Booru: {e}")

        return found_images[:max_images]

    def _build_booru_search_url_from_tags(self, tags: str) -> str:
        """Build booru search URL from tags string."""
        return build_booru_search_url(tags)

    def _get_booru_post_urls(self, search_url: str, max_posts: int) -> List[str]:
        """
        Get post URLs from booru search results page.

        Args:
            search_url: Search results URL
            max_posts: Maximum number of post URLs to return

        Returns:
            List of post URLs
        """
        try:
            response = self.session.get(search_url, timeout=config.REQUEST_TIMEOUT)
            if response.status_code != 200:
                return []

            soup = BeautifulSoup(response.content, 'html.parser')

            # Find post thumbnails
            thumbs = soup.find_all('span', class_='thumb')
            if not thumbs:
                return []

            post_urls = []
            base_url = "https://example.booru.org"  # Will be overridden by actual URL
            for thumb in thumbs[:max_posts]:
                link = thumb.find('a')
                if link and link.get('href'):
                    post_url = urljoin(base_url, link['href'])
                    post_urls.append(post_url)

            return post_urls

        except Exception as e:
            print(f"    Error getting Booru search results: {e}")
            return []

    def _get_booru_image_from_post(self, post_url: str) -> Optional[str]:
        """
        Get the full-resolution image URL from a booru post page.

        Args:
            post_url: URL of the post page

        Returns:
            Image URL or None
        """
        try:
            response = self.session.get(post_url, timeout=config.REQUEST_TIMEOUT)
            if response.status_code != 200:
                return None

            soup = BeautifulSoup(response.content, 'html.parser')

            # Strategy 1: Look for "Original image" link (best quality)
            original_link = soup.find('a', string=re.compile(r'Original image', re.IGNORECASE))
            if original_link and original_link.get('href'):
                img_url = original_link['href']
                if not img_url.startswith('http'):
                    from urllib.parse import urlparse
                    parsed = urlparse(post_url)
                    base = f"{parsed.scheme}://{parsed.netloc}"
                    img_url = urljoin(base, img_url)
                return img_url

            # Strategy 2: Look for the main image element (id="image")
            main_img = soup.find('img', id='image')
            if main_img and main_img.get('src'):
                img_url = main_img['src']
                if not img_url.startswith('http'):
                    from urllib.parse import urlparse
                    parsed = urlparse(post_url)
                    base = f"{parsed.scheme}://{parsed.netloc}"
                    img_url = urljoin(base, img_url)
                return img_url

            return None

        except Exception as e:
            print(f"    Error getting Booru image from post: {e}")
            return None

    # =========================================================================
    # Download Implementation
    # =========================================================================

    def download_image(self, url: str, source_name: Optional[str] = None) -> Tuple[Optional[bytes], Optional[str]]:
        """
        Download image from URL.

        Args:
            url: Image URL
            source_name: Optional source name to use cookies if required

        Returns:
            Tuple of (image_data, extension) or (None, None) if failed
        """
        try:
            # Get cookies for this source if needed
            cookies = {}
            if source_name:
                cookies = self.source_cookies.get(source_name, {})

            response = self.session.get(url, cookies=cookies, timeout=config.REQUEST_TIMEOUT)

            if response.status_code == 200:
                content_type = response.headers.get('Content-Type', '')
                extension = get_image_extension(content_type)

                # If content type doesn't give extension, try URL
                if not extension:
                    extension = get_extension_from_url(url)

                # Validate it's a supported format
                if extension and extension in config.SUPPORTED_IMAGE_FORMATS:
                    return response.content, extension

                print(f"    Unsupported format for {url}")

        except Exception as e:
            print(f"    Error downloading {url}: {e!s}")

        return None, None

    # =========================================================================
    # Abstract Method Implementations (I/O operations)
    # =========================================================================

    def _fetch_page(self, url: str, cookies: Optional[Dict] = None) -> Optional[str]:
        """Fetch page HTML content."""
        try:
            response = self.session.get(url, cookies=cookies or {}, timeout=config.REQUEST_TIMEOUT)
            if response.status_code == 200:
                return response.text
        except Exception as e:
            print(f"    Error fetching page: {e}")
        return None

    def _fetch_json(self, url: str, params: Optional[Dict] = None,
                    cookies: Optional[Dict] = None) -> Optional[Any]:
        """Fetch JSON API response."""
        try:
            response = self.session.get(
                url,
                params=params or {},
                cookies=cookies or {},
                timeout=config.REQUEST_TIMEOUT
            )
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            print(f"    Error fetching JSON: {e}")
        return None

    def _find_booru_images(
        self,
        source: dict,
        character_name: str,
        variant: str,
        max_images: int,
        existing_urls: Set[str]
    ) -> List[Dict]:
        """
        Find images from a Danbooru-style booru site using simple character tag.

        This is a wrapper that uses the base class's find_booru_images method.
        """
        images = self.find_booru_images(character_name, variant, source, max_images)

        # Filter out already-seen URLs and update existing_urls
        new_images = []
        for img in images:
            if img['url'] not in existing_urls:
                new_images.append(img)
                existing_urls.add(img['url'])

        return new_images

    def _find_booru_images_with_tags(
        self,
        source: dict,
        character_name: str,
        tags_query: str,
        variant: str,
        max_images: int,
        existing_urls: Set[str],
        ip: str = "pokemon"
    ) -> List[Dict]:
        """
        Find images from a Danbooru-style booru site using custom tags.

        This wraps the base class method with existing_urls tracking.
        """
        # Build tags query
        char_with_ip = f"{character_name.lower()}_({ip})"
        char_tag = self._apply_character_alias(char_with_ip)

        # Substitute placeholders (use char_tag without IP suffix for character_name)
        tags = substitute_tag_placeholders(tags_query, char_tag.replace(f"_({ip})", ""), ip)

        # Use base class JSON fetching
        api_url = f"{source['base_url']}/posts.json"
        params = {
            'tags': tags,
            'limit': max_images * 2
        }

        cookies = self.source_cookies.get(source['name'], {})
        data = self._fetch_json(api_url, params, cookies)

        if not data:
            return []

        # Parse using base class
        images = self._parse_booru_json(data, character_name, variant, source, source['name'])
        images = self._filter_booru_images(images, max_images)

        # Filter out already-seen URLs
        new_images = []
        for img in images:
            if img['url'] not in existing_urls:
                new_images.append(img)
                existing_urls.add(img['url'])

        return new_images

    def close(self):
        """Close the session."""
        self.session.close()
