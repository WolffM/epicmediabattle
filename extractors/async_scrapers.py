"""
Async scraper methods for Booru-style and Danbooru-style imageboard sites.

These are extracted from AsyncImageFetcher to keep the main class focused.
"""

import re
from typing import Dict, List, Optional, Set
from urllib.parse import quote, urljoin

from bs4 import BeautifulSoup

from core.utils import build_booru_search_url
from extractors.base_fetcher import substitute_tag_placeholders


class BooruScraperMixin:
    """Mixin class providing Booru-style imageboard scraping methods."""

    async def find_booru_images_with_tags(
        self,
        character_name: str,
        tags_template: str,
        variant_name: str,
        max_images: int,
        existing_urls: Set[str],
        ip: str = "pokemon",
        base_url: str = "https://example.booru.org"
    ) -> List[Dict]:
        """
        Find images from a Booru-style imageboard using custom tags.

        Args:
            character_name: Base character name (e.g., "Goku")
            tags_template: Tags template with {character_name} and {ip} placeholders
            variant_name: Name of this tag variant (e.g., "action", "portrait")
            max_images: Maximum number of images to find
            existing_urls: Set of URLs already fetched (modified in place)
            ip: IP name for tag substitution (e.g., "dragonball")
            base_url: Base URL of the booru site

        Returns:
            List of image info dicts with keys: url, page_url, variant
        """
        found_images = []

        try:
            # Substitute placeholders into tags template
            tags = substitute_tag_placeholders(tags_template, character_name, ip)
            search_url = self._build_booru_search_url_from_tags(tags, base_url)

            # Get more post URLs than needed to handle duplicates
            post_urls = await self._get_booru_post_urls(search_url, max_images * 3, base_url)

            if not post_urls:
                return []

            for post_url in post_urls:
                if len(found_images) >= max_images:
                    break

                img_url = await self._get_booru_image_from_post(post_url, base_url)

                if img_url and img_url not in existing_urls:
                    found_images.append({
                        'url': img_url,
                        'page_url': post_url,
                        'variant': variant_name
                    })
                    existing_urls.add(img_url)

        except Exception as e:
            print(f"    Error fetching from booru: {e}")

        return found_images[:max_images]

    async def _find_booru_images(
        self,
        character_name: str,
        variant: str,
        max_images: int,
        existing_urls: Set[str],
        base_url: str = "https://example.booru.org"
    ) -> List[Dict]:
        """Find images from a Booru-style site using default tags (legacy method)."""
        default_tags = "{character_name}_({ip}) sort:score ( solo ~ 1girls ) -multiple_girls -multiple_females -male -animated -futanari -comic"
        return await self.find_booru_images_with_tags(
            character_name, default_tags, variant, max_images, existing_urls, base_url=base_url
        )

    def _build_booru_search_url_from_tags(self, tags: str, base_url: str) -> str:
        """Build booru search URL from tags string."""
        return build_booru_search_url(tags, base_url)

    async def _get_booru_post_urls(self, search_url: str, max_posts: int, base_url: str) -> List[str]:
        """Get post URLs from booru search results page."""
        try:
            response = await self._fetch_with_retry(search_url, context="booru search")
            if not response:
                return []

            content = await response.read()
            await response.release()

            soup = BeautifulSoup(content, 'html.parser')

            thumbs = soup.find_all('span', class_='thumb')
            if not thumbs:
                return []

            post_urls = []
            for thumb in thumbs[:max_posts]:
                link = thumb.find('a')
                if link and link.get('href'):
                    post_url = urljoin(base_url, link['href'])
                    post_urls.append(post_url)

            return post_urls

        except Exception as e:
            print(f"    Error getting booru search results: {e}")
            return []

    async def _get_booru_image_from_post(self, post_url: str, base_url: str) -> Optional[str]:
        """Get the full-resolution image URL from a booru post page."""
        try:
            response = await self._fetch_with_retry(post_url, context="booru post")
            if not response:
                return None

            content = await response.read()
            await response.release()

            soup = BeautifulSoup(content, 'html.parser')

            original_link = soup.find('a', string=re.compile(r'Original image', re.IGNORECASE))
            if original_link and original_link.get('href'):
                img_url = original_link['href']
                if not img_url.startswith('http'):
                    img_url = urljoin(base_url, img_url)
                return img_url

            main_img = soup.find('img', id='image')
            if main_img and main_img.get('src'):
                img_url = main_img['src']
                if not img_url.startswith('http'):
                    img_url = urljoin(base_url, img_url)
                return img_url

            return None

        except Exception as e:
            print(f"    Error getting booru image from post: {e}")
            return None


class DanbooruScraperMixin:
    """Mixin class providing Danbooru-style imageboard scraping methods."""

    async def _find_danbooru_images_with_tags(
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
        Find images from a Danbooru-style booru using page scraping (API has 5-tag limit).

        Danbooru limits complex queries, so we use simple character+order tags only
        and fetch more results to compensate.
        """
        found_images = []

        try:
            # Build simple tags - just character and ordering
            # Danbooru doesn't allow complex queries, so we use simple tags only
            char_with_ip = f"{character_name.lower()}_({ip})"
            char_tag = self._apply_character_alias(char_with_ip)

            # Extract metatags (order:, age:, etc) from template - these are allowed
            metatags = []
            for part in tags_template.split():
                if ':' in part and not part.startswith('-') and not part.startswith('('):
                    # This is a metatag like order:score or age:<10days
                    metatags.append(part)

            # Build simple search: character + metatags only
            simple_tags = char_tag
            if metatags:
                simple_tags = f"{char_tag} {' '.join(metatags)}"

            # Build search URL
            search_url = f"{source['base_url']}/posts?tags={quote(simple_tags)}"

            # Get cookies for this booru
            cookies = self.source_cookies.get(source['name'], {})
            ctx = f"danbooru:{source['short_name']}"

            # Fetch search page
            html = await self._fetch_page_async(search_url, cookies=cookies, context=ctx)
            if not html:
                return []

            # Parse post URLs from search results
            post_urls = self._parse_danbooru_search_results(html, source['base_url'])

            if not post_urls:
                return []

            # Fetch images from each post
            for post_url in post_urls[:max_images * 3]:  # Get more than needed since we can't filter via query
                if len(found_images) >= max_images:
                    break

                img_url = await self._get_danbooru_image_from_post(post_url, source, cookies)

                if img_url and img_url not in existing_urls:
                    found_images.append({
                        'url': img_url,
                        'page_url': post_url,
                        'variant': variant_name,
                        'source': source['name']  # Pass source name for cookie handling during download
                    })
                    existing_urls.add(img_url)

        except Exception as e:
            print(f"    Error fetching from Danbooru-style booru: {e}")

        return found_images[:max_images]

    def _parse_danbooru_search_results(self, html: str, base_url: str) -> List[str]:
        """Parse post URLs from Danbooru-style booru search results page."""
        soup = BeautifulSoup(html, 'html.parser')
        post_urls = []

        # Danbooru uses article tags with data-id for posts
        articles = soup.find_all('article', attrs={'data-id': True})
        for article in articles:
            post_id = article.get('data-id')
            if post_id:
                post_urls.append(f"{base_url}/posts/{post_id}")

        # Also try to find direct post links if article parsing fails
        if not post_urls:
            links = soup.find_all('a', href=re.compile(r'/posts/\d+'))
            for link in links:
                href = link.get('href', '')
                if href and '/posts/' in href:
                    post_url = urljoin(base_url, href)
                    if post_url not in post_urls:
                        post_urls.append(post_url)

        return post_urls

    async def _get_danbooru_image_from_post(self, post_url: str, source: dict, cookies: Dict) -> Optional[str]:
        """Get the full-resolution image URL from a Danbooru-style booru post page."""
        try:
            ctx = f"danbooru post:{source['short_name']}"
            html = await self._fetch_page_async(post_url, cookies=cookies, context=ctx)
            if not html:
                return None

            soup = BeautifulSoup(html, 'html.parser')

            # Method 1: Look for link with /original/ in href (most reliable)
            size_link = soup.find('a', href=re.compile(r'/original/'))
            if size_link and size_link.get('href'):
                href = size_link['href']
                # Skip download links, prefer direct image
                if 'download=' not in href:
                    return urljoin(source['base_url'], href)

            # Method 2: Look for image tag with full URL
            img = soup.find('img', id='image')
            if img and img.get('src'):
                return urljoin(source['base_url'], img['src'])

            # Method 3: Look for picture source (Danbooru sometimes uses picture tags)
            picture = soup.find('picture')
            if picture:
                source_tag = picture.find('source')
                if source_tag and source_tag.get('srcset'):
                    return urljoin(source['base_url'], source_tag['srcset'].split()[0])
                img = picture.find('img')
                if img and img.get('src'):
                    return urljoin(source['base_url'], img['src'])

            # Method 4: Look in post content section
            content = soup.find('section', id='content')
            if content:
                img = content.find('img')
                if img and img.get('src'):
                    return urljoin(source['base_url'], img['src'])

            return None

        except Exception as e:
            print(f"    Error getting Danbooru image from post: {e}")
            return None
