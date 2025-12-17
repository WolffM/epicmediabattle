"""
Async image fetcher with multi-source, multi-image support (async version).
Uses aiohttp for concurrent requests with rate limiting and backoff.
"""

import asyncio
import os
import re
import sys
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import quote, unquote, urljoin

import aiohttp
from bs4 import BeautifulSoup

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import config
from core.utils import (
    clean_fandom_url,
    get_fandom_image_by_filename,
    is_likely_character_image,
    resolve_bulbapedia_thumbnail,
)
from extractors.async_scrapers import BooruScraperMixin, DanbooruScraperMixin
from extractors.base_fetcher import BaseFetcher, substitute_tag_placeholders
from extractors.crawler_utils import (
    ExponentialBackoff,
    RateLimiter,
    UserAgentRotator,
    get_browser_headers,
    get_image_headers,
)
from extractors.utils import get_extension_from_url, get_image_extension, is_url_valid_image


class AsyncImageFetcher(BaseFetcher, BooruScraperMixin, DanbooruScraperMixin):
    """Async fetcher for character images from multiple sources."""

    def __init__(self, ip: str):
        """
        Initialize the AsyncImageFetcher.

        Args:
            ip: The intellectual property (e.g., 'pokemon')
        """
        sources = config.get_sources(ip)
        super().__init__(sources, ip)

        # Setup rate limiter with domain-specific delays
        self.rate_limiter = RateLimiter(default_delay=config.REQUEST_DELAY)
        for domain, delay in config.RATE_LIMITS.items():
            self.rate_limiter.set_domain_delay(domain, delay)

        # Setup backoff for retries
        self.backoff = ExponentialBackoff(
            base=config.BACKOFF_BASE,
            max_delay=config.BACKOFF_MAX,
            max_retries=config.MAX_RETRIES,
            jitter=config.BACKOFF_JITTER
        )

        # User agent rotation
        self.ua_rotator = UserAgentRotator()

        # Semaphores for concurrency control
        self.source_semaphores: Dict[str, asyncio.Semaphore] = {}
        self.global_semaphore = asyncio.Semaphore(config.MAX_CONCURRENT_TOTAL)

        # Session will be created in context manager
        self._session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self):
        """Async context manager entry."""
        timeout = aiohttp.ClientTimeout(total=config.REQUEST_TIMEOUT)
        self._session = aiohttp.ClientSession(timeout=timeout)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self._session:
            await self._session.close()

    def _get_source_semaphore(self, source_name: str) -> asyncio.Semaphore:
        """Get or create semaphore for a source."""
        if source_name not in self.source_semaphores:
            self.source_semaphores[source_name] = asyncio.Semaphore(
                config.MAX_CONCURRENT_PER_SOURCE
            )
        return self.source_semaphores[source_name]

    async def _fetch_with_retry(
        self,
        url: str,
        headers: Optional[Dict] = None,
        params: Optional[Dict] = None,
        cookies: Optional[Dict] = None,
        silent_retries: bool = False,
        context: Optional[str] = None,
        max_retries: Optional[int] = None
    ) -> Optional[aiohttp.ClientResponse]:
        """
        Fetch URL with rate limiting, retries, and backoff.

        Args:
            url: URL to fetch
            headers: Optional headers dict
            params: Optional query parameters
            cookies: Optional cookies dict
            silent_retries: If True, suppress retry messages (less spam)
            context: Description of what operation this is (e.g., 'API search', 'image download')
            max_retries: Override default max retries (use 1 for fast-fail on 500s)

        Returns:
            Response object or None if all retries failed
        """
        if headers is None:
            headers = get_browser_headers(self.ua_rotator.get_next())

        # Pass cookies via Cookie header instead of aiohttp's cookies param
        # This works better with anti-bot systems that check cookie handling
        if cookies:
            cookie_str = '; '.join([f"{k}={v}" for k, v in cookies.items()])
            headers = dict(headers)  # Make a copy to avoid mutating original
            headers['Cookie'] = cookie_str

        # Use provided max_retries or default
        retries = max_retries if max_retries is not None else config.MAX_RETRIES

        # Extract domain for logging
        from urllib.parse import urlparse
        domain = urlparse(url).netloc
        ctx_str = f"[{context}] " if context else ""

        server_error_count = 0
        last_status = None
        for attempt in range(retries + 1):
            try:
                # Wait for backoff if this is a retry
                await self.backoff.wait(attempt)

                # Rate limit
                await self.rate_limiter.wait(url)

                # Make request (cookies already in headers)
                async with self.global_semaphore:
                    response = await self._session.get(
                        url,
                        headers=headers,
                        params=params
                    )

                    if response.status == 200:
                        return response
                    elif response.status == 429:  # Rate limited
                        if not silent_retries:
                            print(f"      {ctx_str}Rate limited (429) from {domain}, backing off...")
                        await response.release()
                        continue
                    elif response.status >= 500:  # Server error
                        server_error_count += 1
                        last_status = response.status
                        # Print on first error with context
                        if server_error_count == 1 and not silent_retries:
                            print(f"      {ctx_str}Server error ({response.status}) from {domain}")
                        await response.release()
                        continue
                    elif response.status == 403:
                        if not silent_retries:
                            print(f"      {ctx_str}Access denied (403) from {domain} - may need fresh cookies")
                        await response.release()
                        return None
                    elif response.status == 404:
                        # 404 is expected for some queries, don't log unless debugging
                        await response.release()
                        return None
                    else:
                        # Other 4xx errors - don't retry
                        if not silent_retries:
                            print(f"      {ctx_str}HTTP {response.status} from {domain}")
                        await response.release()
                        return None

            except asyncio.TimeoutError:
                if not silent_retries and attempt == 0:
                    print(f"      {ctx_str}Timeout from {domain}, retrying...")
                continue
            except aiohttp.ClientError as e:
                if not silent_retries and attempt == 0:
                    print(f"      {ctx_str}Connection error from {domain}: {e}")
                continue

        # Log final failure if we had server errors
        if server_error_count > 0 and not silent_retries:
            print(f"      {ctx_str}FAILED: {server_error_count}x HTTP {last_status} from {domain}")
        return None

    async def find_images_for_character(
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

        # Use source-specific semaphore
        semaphore = self._get_source_semaphore(source_name)

        async with semaphore:
            if site_type == 'booru':
                # Booru sites use base character name (no wiki variants)
                base_name = character['search_name'].replace(' ', '_')
                return await self._find_booru_images(source, base_name, variant, max_images, existing_urls)
            elif source_name == 'bulbapedia':
                return await self._find_bulbapedia_images(search_name, variant, max_images, existing_urls)
            elif source_name == 'fandom':
                return await self._find_fandom_images(search_name, variant, max_images, existing_urls)
            elif site_type == 'booru_scrape':
                # Legacy: Booru scraping without API
                base_name = character['search_name'].replace(' ', '_')
                return await self._find_booru_scrape_images(base_name, variant, max_images, existing_urls)
            else:
                return []

    async def _find_bulbapedia_images(
        self,
        search_name: str,
        variant: str,
        max_images: int,
        existing_urls: Set[str]
    ) -> List[Dict]:
        """Find images from Bulbapedia page."""
        base_url = "https://bulbapedia.bulbagarden.net"
        page_url = f"{base_url}/wiki/{quote(search_name)}"

        found_images = []

        try:
            response = await self._fetch_with_retry(page_url, context="bulbapedia wiki")
            if not response:
                return []

            content = await response.read()
            await response.release()

            soup = BeautifulSoup(content, 'html.parser')

            # Strategy 1: Look for infobox image first
            infobox = soup.find('table', class_='roundy')
            if infobox:
                img = infobox.find('img')
                if img and img.get('src'):
                    img_url = self._resolve_bulbapedia_image(img['src'], base_url)
                    if img_url and img_url not in existing_urls and is_url_valid_image(img_url):
                        found_images.append({
                            'url': img_url,
                            'page_url': page_url,
                            'variant': variant
                        })
                        existing_urls.add(img_url)

            if len(found_images) >= max_images:
                return found_images[:max_images]

            # Strategy 2: Look for gallery links (File: pages)
            file_links = soup.find_all('a', href=re.compile(r'/wiki/File:.*\.(png|jpg|jpeg|webp)', re.IGNORECASE))
            for link in file_links:
                if len(found_images) >= max_images:
                    break

                href = link.get('href', '')
                file_page_url = urljoin(base_url, href)
                img_url = await self._get_bulbapedia_file_image(file_page_url)

                if img_url and img_url not in existing_urls and is_url_valid_image(img_url):
                    found_images.append({
                        'url': img_url,
                        'page_url': page_url,
                        'variant': variant
                    })
                    existing_urls.add(img_url)

            # Strategy 3: Look for images in the main content
            content_images = soup.find_all('img')
            for img in content_images:
                if len(found_images) >= max_images:
                    break

                src = img.get('src', '')
                if 'thumb' in src and '/thumb/' in src:
                    img_url = self._resolve_bulbapedia_image(src, base_url)
                else:
                    img_url = urljoin(base_url, src)

                if img_url and img_url not in existing_urls and is_url_valid_image(img_url) and is_likely_character_image(img_url, search_name):
                    found_images.append({
                        'url': img_url,
                        'page_url': page_url,
                        'variant': variant
                    })
                    existing_urls.add(img_url)

        except Exception as e:
            print(f"    Error fetching from Bulbapedia: {e}")

        return found_images[:max_images]

    def _resolve_bulbapedia_image(self, src: str, base_url: str) -> Optional[str]:
        """Resolve Bulbapedia thumbnail URL to full image URL."""
        return resolve_bulbapedia_thumbnail(src, base_url)

    async def _get_bulbapedia_file_image(self, file_page_url: str) -> Optional[str]:
        """Get the actual image URL from a Bulbapedia File: page."""
        try:
            response = await self._fetch_with_retry(file_page_url, context="bulbapedia file")
            if not response:
                return None

            content = await response.read()
            await response.release()

            soup = BeautifulSoup(content, 'html.parser')

            full_media = soup.find('div', class_='fullMedia')
            if full_media:
                link = full_media.find('a')
                if link and link.get('href'):
                    return urljoin(file_page_url, link['href'])

            file_img = soup.find('img', class_='mw-file-element')
            if file_img and file_img.get('src'):
                return self._resolve_bulbapedia_image(file_img['src'], 'https://bulbapedia.bulbagarden.net')

        except Exception:
            pass

        return None

    async def _find_fandom_images(
        self,
        search_name: str,
        variant: str,
        max_images: int,
        existing_urls: Set[str]
    ) -> List[Dict]:
        """Find images from Pokemon Fandom wiki."""
        base_url = "https://pokemon.fandom.com"
        page_url = f"{base_url}/wiki/{quote(search_name)}"

        found_images = []

        try:
            response = await self._fetch_with_retry(page_url, context="fandom wiki")
            if not response:
                return []

            content = await response.read()
            await response.release()

            soup = BeautifulSoup(content, 'html.parser')

            # Strategy 1: Infobox image
            infobox = soup.find('aside', class_='portable-infobox')
            if infobox:
                img = infobox.find('img')
                if img and img.get('src'):
                    img_url = self._clean_fandom_url(img['src'])
                    if img_url and img_url not in existing_urls and is_url_valid_image(img_url):
                        found_images.append({
                            'url': img_url,
                            'page_url': page_url,
                            'variant': variant
                        })
                        existing_urls.add(img_url)

            if len(found_images) >= max_images:
                return found_images[:max_images]

            # Strategy 2: Gallery images
            gallery_links = soup.find_all('a', href=re.compile(r'\?file='))
            for link in gallery_links:
                if len(found_images) >= max_images:
                    break

                href = link.get('href', '')
                match = re.search(r'\?file=([^&]+)', href)
                if match:
                    filename = unquote(match.group(1).replace('+', ' '))
                    img_url = self._get_fandom_image_by_filename(filename)
                    if img_url and img_url not in existing_urls and is_url_valid_image(img_url):
                        found_images.append({
                            'url': img_url,
                            'page_url': page_url,
                            'variant': variant
                        })
                        existing_urls.add(img_url)

            # Strategy 3: Images in article galleries
            gallery_imgs = soup.find_all('img', class_='pi-image-thumbnail')
            gallery_imgs += soup.find_all('img', attrs={'data-src': True})

            for img in gallery_imgs:
                if len(found_images) >= max_images:
                    break

                src = img.get('data-src') or img.get('src', '')
                img_url = self._clean_fandom_url(src)

                if img_url and img_url not in existing_urls and is_url_valid_image(img_url):
                    found_images.append({
                        'url': img_url,
                        'page_url': page_url,
                        'variant': variant
                    })
                    existing_urls.add(img_url)

        except Exception as e:
            print(f"    Error fetching from Fandom: {e}")

        return found_images[:max_images]

    def _clean_fandom_url(self, url: str) -> Optional[str]:
        """Clean Fandom image URL to get full resolution."""
        return clean_fandom_url(url)

    def _get_fandom_image_by_filename(self, filename: str) -> Optional[str]:
        """Try to construct Fandom image URL from filename."""
        return get_fandom_image_by_filename(filename)

    # =========================================================================
    # Booru methods (Danbooru-style API sites)
    # =========================================================================

    async def find_booru_images_with_tags(
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
        Find images from any booru site using custom tags. Routes to appropriate implementation.

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
        source_name = source['name']

        # Danbooru-style boorus using page scraping (API has 5-tag limit)
        if source_name == 'danbooru':
            return await self._find_danbooru_images_with_tags(source, character_name, tags_template, variant_name, max_images, existing_urls, ip)
        # Check if this is a Danbooru-style API booru
        elif source.get('site_type') == 'booru':
            # Use the Danbooru API method
            return await self._find_booru_images_with_tags(source, character_name, tags_template, variant_name, max_images, existing_urls, ip)
        else:
            # Use HTML scraping method
            return await self.find_booru_scrape_images_with_tags(character_name, tags_template, variant_name, max_images, existing_urls, ip)

    async def _find_booru_images(
        self,
        source: dict,
        character_name: str,
        variant: str,
        max_images: int,
        existing_urls: Set[str]
    ) -> List[Dict]:
        """
        Find images from a Danbooru-style booru site using simple character tag.

        Async wrapper that uses booru image finding logic.
        """
        return await self._find_booru_images_with_tags(
            source, character_name, character_name, variant, max_images, existing_urls, self.ip
        )

    async def _find_booru_images_with_tags(
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

        This wraps the base class method with async I/O and existing_urls tracking.
        """
        # Build tags query
        char_with_ip = f"{character_name.lower()}_({ip})"
        char_tag = self._apply_character_alias(char_with_ip)

        # Substitute placeholders (use char_tag without IP suffix for character_name)
        tags = substitute_tag_placeholders(tags_query, char_tag.replace(f"_({ip})", ""), ip)

        # Use base class JSON fetching with async variant
        api_url = f"{source['base_url']}/posts.json"
        params = {
            'tags': tags,
            'limit': max_images * 2
        }

        cookies = self.source_cookies.get(source['name'], {})
        ctx = f"booru API:{source['short_name']}"
        # Use reduced retries for API calls - fast-fail on server errors
        data = await self._fetch_json_async(api_url, params, cookies, context=ctx, max_retries=1)

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

    # =========================================================================
    # Abstract Method Implementations (async I/O operations)
    # =========================================================================

    def _fetch_page(self, url: str, cookies: Optional[Dict] = None) -> Optional[str]:
        """
        Sync version not supported in async fetcher.
        Use async methods directly instead.
        """
        raise NotImplementedError("Use async methods in AsyncImageFetcher")

    def _fetch_json(self, url: str, params: Optional[Dict] = None,
                    cookies: Optional[Dict] = None) -> Optional[Any]:
        """
        Sync version not supported in async fetcher.
        Use async methods directly instead.
        """
        raise NotImplementedError("Use async methods in AsyncImageFetcher")

    async def _fetch_page_async(self, url: str, cookies: Optional[Dict] = None,
                                context: str = "page") -> Optional[str]:
        """Async version of _fetch_page."""
        headers = get_browser_headers(self.ua_rotator.get_next())
        response = await self._fetch_with_retry(url, headers, cookies=cookies, context=context)
        if response:
            try:
                return await response.text()
            except Exception as e:
                print(f"    Error reading page text: {e}")
        return None

    async def _fetch_json_async(self, url: str, params: Optional[Dict] = None,
                                cookies: Optional[Dict] = None,
                                context: str = "API",
                                max_retries: Optional[int] = None) -> Optional[Any]:
        """Async version of _fetch_json."""
        headers = get_browser_headers(self.ua_rotator.get_next())
        response = await self._fetch_with_retry(url, headers, params, cookies, context=context, max_retries=max_retries)
        if response:
            try:
                return await response.json()
            except Exception as e:
                print(f"    Error parsing JSON: {e}")
        return None

    async def download_image(self, url: str, referer: Optional[str] = None, source_name: Optional[str] = None) -> Tuple[Optional[bytes], Optional[str]]:
        """
        Download image from URL.

        Args:
            url: Image URL
            referer: Optional referer header
            source_name: Optional source name to use cookies if required

        Returns:
            Tuple of (image_data, extension) or (None, None) if failed
        """
        try:
            # Get cookies for this source if needed
            cookies = {}
            if source_name:
                cookies = self.source_cookies.get(source_name, {})

            # Build context string for logging
            ctx = f"download:{source_name}" if source_name else "download"

            headers = get_image_headers(self.ua_rotator.get_next(), referer)
            response = await self._fetch_with_retry(url, headers, cookies=cookies, context=ctx)

            if response and response.status == 200:
                content_type = response.headers.get('Content-Type', '')
                extension = get_image_extension(content_type)

                if not extension:
                    extension = get_extension_from_url(url)

                if extension and extension in config.SUPPORTED_IMAGE_FORMATS:
                    data = await response.read()
                    await response.release()
                    return data, extension

                await response.release()
                print(f"    Unsupported format for {url}")

        except Exception as e:
            print(f"    Error downloading {url}: {e!s}")

        return None, None
