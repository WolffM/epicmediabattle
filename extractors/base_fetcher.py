"""
Base fetcher class with shared scraping logic.

This module contains the abstract base class that both sync and async fetchers
inherit from. It extracts all the duplicate scraping strategy logic while leaving
I/O operations (HTTP requests) to be implemented by subclasses.
"""

import json
import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse

from core import config
from core.utils import get_ip_aliases


def substitute_tag_placeholders(tags_template: str, character_name: str, ip: str) -> str:
    """
    Substitute placeholders in a tags template.

    Supports:
        - {character_name}: Character name
        - {ip}: IP name
        - {ip_alt1}, {ip_alt2}, {ip_alt3}: IP aliases (for multi-tag IPs)

    Args:
        tags_template: Tags template with placeholders
        character_name: Character name to substitute
        ip: IP name to substitute

    Returns:
        Tags string with all placeholders replaced
    """
    tags = tags_template.replace("{character_name}", character_name).replace("{ip}", ip)

    # Get IP aliases and substitute
    aliases = get_ip_aliases(ip)
    for i, alias in enumerate(aliases[:3], start=1):
        tags = tags.replace(f"{{ip_alt{i}}}", alias)

    # If fewer than 3 aliases, fill remaining with empty string
    for i in range(len(aliases) + 1, 4):
        tags = tags.replace(f"{{ip_alt{i}}}", "")

    return tags


class BaseFetcher(ABC):
    """
    Abstract base class for image fetchers.

    Contains all shared scraping logic and strategies for different sources.
    Subclasses must implement the I/O operations (HTTP requests, downloads).
    """

    def __init__(self, sources: List[Dict], ip: str = "pokemon"):
        """
        Initialize base fetcher.

        Args:
            sources: List of source configurations
            ip: IP name (e.g., 'pokemon')
        """
        self.sources = sources
        self.ip = ip

        # Load character aliases for booru sources
        self.character_aliases = self._load_character_aliases()

        # Load cookies for protected sources
        self.source_cookies = self._load_source_cookies()

    def _load_character_aliases(self) -> Dict[str, str]:
        """
        Load character name aliases from booru_character_aliases.json.

        Returns:
            Dict mapping English names to localized names (e.g., goku_dragonball -> kakarot_dragonball)
        """
        alias_path = config.get_input_file('booru_character_aliases.json')
        if not Path(alias_path).exists():
            return {}

        try:
            with open(alias_path, encoding='utf-8') as f:
                data = json.load(f)
                return data.get('aliases', {})
        except Exception as e:
            print(f"Warning: Could not load character aliases: {e}")
            return {}

    def _load_source_cookies(self) -> Dict[str, Dict[str, str]]:
        """
        Load cookies for all sources that require authentication.

        Returns:
            Dict mapping source name to cookie dict
        """
        cookies = {}
        for source in self.sources:
            cookie_path = source.get('cookie_path')
            if cookie_path:
                try:
                    with open(cookie_path, encoding='utf-8') as f:
                        cookies_list = json.load(f)
                        cookies[source['name']] = {
                            c['name']: c['value'] for c in cookies_list
                        }
                except Exception as e:
                    print(f"Warning: Could not load cookies for {source['name']}: {e}")
        return cookies

    def _apply_character_alias(self, character: str) -> str:
        """
        Apply character alias mapping if available.

        Args:
            character: Character name (e.g., may_pokemon)

        Returns:
            Aliased name if found, original name otherwise
        """
        return self.character_aliases.get(character, character)

    # =========================================================================
    # Bulbapedia Scraping Strategy
    # =========================================================================

    def _resolve_bulbapedia_image(self, img_src: str, base_url: str) -> str:
        """
        Resolve Bulbapedia image URL to full-resolution version.

        Bulbapedia uses thumbnails in pages. This converts:
        /thumb/1/2/File.png/200px-File.png -> /1/2/File.png

        Args:
            img_src: Image src attribute from HTML
            base_url: Base URL of the source

        Returns:
            Full-resolution image URL
        """
        full_url = urljoin(base_url, img_src)

        # Convert thumbnail URLs to full resolution
        if '/thumb/' in full_url:
            # Remove /thumb/ and thumbnail size suffix
            full_url = full_url.replace('/thumb/', '/')
            # Remove the /XXXpx-filename.ext part
            parts = full_url.rsplit('/', 1)
            if len(parts) == 2:
                base_part, filename = parts
                # Remove thumbnail size prefix (e.g., 200px-)
                if 'px-' in filename:
                    filename = filename.split('px-', 1)[1]
                full_url = f"{base_part}/{filename}"

        return full_url

    def _parse_bulbapedia_html(
        self,
        html: str,
        character: str,
        variant: str,
        source_name: str
    ) -> List[Dict[str, str]]:
        """
        Parse Bulbapedia HTML to extract image URLs.

        Args:
            html: Page HTML content
            character: Character name
            variant: Tag variant name
            source_name: Source name

        Returns:
            List of dicts with 'url', 'page_url', 'variant', 'source'
        """
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, 'html.parser')
        images = []

        # Find image gallery sections
        for img in soup.find_all('img'):
            src = img.get('src', '')
            if not src:
                continue

            # Skip icons, logos, navigation images
            if any(x in src.lower() for x in ['icon', 'logo', 'button', 'arrow']):
                continue

            # Get parent link for page URL
            parent_link = img.find_parent('a')
            page_url = parent_link.get('href', '') if parent_link else ''

            images.append({
                'url': src,
                'page_url': page_url,
                'variant': variant,
                'source': source_name
            })

        return images

    # =========================================================================
    # Fandom Scraping Strategy
    # =========================================================================

    def _clean_fandom_url(self, url: str) -> str:
        """
        Clean Fandom image URL to get highest quality version.

        Fandom appends scaling parameters. This removes them:
        /image.png/revision/latest/scale-to-width-down/200 -> /image.png/revision/latest

        Args:
            url: Fandom image URL

        Returns:
            Cleaned URL without scaling parameters
        """
        # Remove scale-to-width-down and similar parameters
        url = re.sub(r'/scale-to-[^/]+/\d+', '', url)
        url = re.sub(r'/zoom-crop/[^/]+/\d+/\d+', '', url)

        # Ensure we have /revision/latest for best quality
        if '/revision/' in url and not url.endswith('/latest'):
            url = url.rsplit('/', 1)[0] + '/latest'

        return url

    def _parse_fandom_html(
        self,
        html: str,
        character: str,
        variant: str,
        source_name: str
    ) -> List[Dict[str, str]]:
        """
        Parse Fandom HTML to extract image URLs.

        Args:
            html: Page HTML content
            character: Character name
            variant: Tag variant name
            source_name: Source name

        Returns:
            List of dicts with 'url', 'page_url', 'variant', 'source'
        """
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, 'html.parser')
        images = []

        # Fandom uses various image containers
        for img in soup.find_all('img'):
            src = img.get('src', '') or img.get('data-src', '')
            if not src:
                continue

            # Skip small icons and UI elements
            if any(x in src.lower() for x in ['icon', 'avatar', 'badge', 'emoji']):
                continue

            # Get parent link
            parent_link = img.find_parent('a')
            page_url = parent_link.get('href', '') if parent_link else ''

            images.append({
                'url': src,
                'page_url': page_url,
                'variant': variant,
                'source': source_name
            })

        return images

    # =========================================================================
    # Booru Scraping Strategy (Danbooru-style JSON API)
    # =========================================================================

    def _build_booru_tags(self, character: str, variant: str, source: Dict) -> str:
        """
        Build booru tag query string.

        Args:
            character: Character name (e.g., may_pokemon)
            variant: Variant tag (e.g., gen3)
            source: Source configuration dict

        Returns:
            Space-separated tag string
        """
        # Apply character alias if available
        character = self._apply_character_alias(character)

        # Get base character tag (without _(pokemon) suffix for most boorus)
        char_tag = character

        # Get variant tag mapping
        tag_variants = config.get_tag_variants(source['name'], self.ip)
        variant_tag = tag_variants.get(variant, variant)

        # Build tag query
        tags = [char_tag]
        if variant_tag:
            tags.append(variant_tag)

        return ' '.join(tags)

    def _parse_booru_json(
        self,
        data: Any,
        character: str,
        variant: str,
        source: Dict,
        source_name: str
    ) -> List[Dict[str, str]]:
        """
        Parse Danbooru-style JSON API response.

        Args:
            data: JSON response data (list of post dicts)
            character: Character name
            variant: Variant tag
            source: Source configuration
            source_name: Source name

        Returns:
            List of dicts with 'url', 'page_url', 'variant', 'source'
        """
        if not isinstance(data, list):
            return []

        images = []
        base_url = source['base_url']

        for post in data:
            # Get file URL - different boorus use different field names
            file_url = (
                post.get('file_url') or
                post.get('large_file_url') or
                post.get('url')
            )

            if not file_url:
                continue

            # Make absolute URL if relative
            if file_url.startswith('//'):
                file_url = 'https:' + file_url
            elif file_url.startswith('/'):
                file_url = urljoin(base_url, file_url)

            # Build post URL
            post_id = post.get('id')
            post_url = f"{base_url}/posts/{post_id}" if post_id else ''

            images.append({
                'url': file_url,
                'page_url': post_url,
                'variant': variant,
                'source': source_name
            })

        return images

    def _filter_booru_images(
        self,
        images: List[Dict[str, str]],
        max_images: Optional[int] = None
    ) -> List[Dict[str, str]]:
        """
        Filter and limit booru images.

        Args:
            images: List of image dicts
            max_images: Maximum number of images to return

        Returns:
            Filtered image list
        """
        # Filter by supported formats
        supported_exts = tuple(config.SUPPORTED_IMAGE_FORMATS)
        filtered = [
            img for img in images
            if any(img['url'].lower().endswith(ext) for ext in supported_exts)
        ]

        # Limit if requested
        if max_images:
            filtered = filtered[:max_images]

        return filtered

    # =========================================================================
    # URL Validation Helpers
    # =========================================================================

    def _is_valid_image_url(self, url: str) -> bool:
        """
        Check if URL is a valid image URL.

        Args:
            url: URL to check

        Returns:
            True if valid image URL
        """
        if not url:
            return False

        # Check for supported extensions
        url_lower = url.lower()
        return any(url_lower.endswith(ext) for ext in config.SUPPORTED_IMAGE_FORMATS)

    def _extract_filename_from_url(self, url: str) -> str:
        """
        Extract filename from URL.

        Args:
            url: Image URL

        Returns:
            Filename (e.g., 'image.png')
        """
        parsed = urlparse(url)
        path = parsed.path
        filename = path.split('/')[-1]

        # Remove query parameters if present
        if '?' in filename:
            filename = filename.split('?')[0]

        return filename

    def _get_extension_from_url(self, url: str) -> str:
        """
        Get file extension from URL.

        Args:
            url: Image URL

        Returns:
            Extension including dot (e.g., '.png')
        """
        filename = self._extract_filename_from_url(url)

        # Get extension
        if '.' in filename:
            ext = '.' + filename.rsplit('.', 1)[1].lower()
            if ext in config.SUPPORTED_IMAGE_FORMATS:
                return ext

        return '.jpg'  # Default fallback

    # =========================================================================
    # Abstract Methods (to be implemented by subclasses)
    # =========================================================================

    @abstractmethod
    def _fetch_page(self, url: str, cookies: Optional[Dict] = None) -> Optional[str]:
        """
        Fetch page HTML content.

        Args:
            url: Page URL
            cookies: Optional cookies dict

        Returns:
            HTML content or None on error
        """
        pass

    @abstractmethod
    def _fetch_json(self, url: str, params: Optional[Dict] = None,
                    cookies: Optional[Dict] = None) -> Optional[Any]:
        """
        Fetch JSON API response.

        Args:
            url: API endpoint URL
            params: Optional query parameters
            cookies: Optional cookies dict

        Returns:
            Parsed JSON data or None on error
        """
        pass

    @abstractmethod
    def download_image(self, url: str, source_name: Optional[str] = None) -> Tuple[Optional[bytes], Optional[str]]:
        """
        Download image from URL.

        Args:
            url: Image URL
            source_name: Optional source name for cookie lookup

        Returns:
            Tuple of (image_data, extension) or (None, None) on error
        """
        pass

    # =========================================================================
    # High-Level Scraping Methods (using abstract I/O)
    # =========================================================================

    def find_bulbapedia_images(
        self,
        character: str,
        variant: str,
        source: Dict,
        max_images: Optional[int] = None
    ) -> List[Dict[str, str]]:
        """
        Find images from Bulbapedia source.

        Args:
            character: Character name
            variant: Tag variant
            source: Source configuration
            max_images: Maximum images to return

        Returns:
            List of image dicts
        """
        url = source['url_template'].format(character=character.replace('_', ' ').title())
        html = self._fetch_page(url)

        if not html:
            return []

        images = self._parse_bulbapedia_html(html, character, variant, source['name'])

        # Resolve thumbnail URLs to full resolution
        for img in images:
            img['url'] = self._resolve_bulbapedia_image(img['url'], source['base_url'])

        # Filter and limit
        images = [img for img in images if self._is_valid_image_url(img['url'])]
        if max_images:
            images = images[:max_images]

        return images

    def find_fandom_images(
        self,
        character: str,
        variant: str,
        source: Dict,
        max_images: Optional[int] = None
    ) -> List[Dict[str, str]]:
        """
        Find images from Fandom wiki source.

        Args:
            character: Character name
            variant: Tag variant
            source: Source configuration
            max_images: Maximum images to return

        Returns:
            List of image dicts
        """
        url = source['url_template'].format(character=character.replace('_', ' ').title())
        html = self._fetch_page(url)

        if not html:
            return []

        images = self._parse_fandom_html(html, character, variant, source['name'])

        # Clean URLs to get best quality
        for img in images:
            img['url'] = self._clean_fandom_url(img['url'])

        # Filter and limit
        images = [img for img in images if self._is_valid_image_url(img['url'])]
        if max_images:
            images = images[:max_images]

        return images

    def find_booru_images(
        self,
        character: str,
        variant: str,
        source: Dict,
        max_images: Optional[int] = None
    ) -> List[Dict[str, str]]:
        """
        Find images from Danbooru-style booru source.

        Args:
            character: Character name
            variant: Tag variant
            source: Source configuration
            max_images: Maximum images to return

        Returns:
            List of image dicts
        """
        # Build tags
        tags = self._build_booru_tags(character, variant, source)

        # Build API URL
        api_url = f"{source['base_url']}/posts.json"
        params = {
            'tags': tags,
            'limit': max_images or 100
        }

        # Get cookies if needed
        cookies = self.source_cookies.get(source['name'])

        # Fetch JSON
        data = self._fetch_json(api_url, params, cookies)

        if not data:
            return []

        # Parse and filter
        images = self._parse_booru_json(data, character, variant, source, source['name'])
        images = self._filter_booru_images(images, max_images)

        return images
