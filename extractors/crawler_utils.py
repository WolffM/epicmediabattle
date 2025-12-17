"""
Crawler utility functions for protection and rate limiting.
"""

import asyncio
import random
import time
from typing import ClassVar, Dict, List, Optional
from urllib.parse import urlparse


class RateLimiter:
    """
    Per-domain rate limiter to prevent overwhelming servers.
    Thread-safe for use with asyncio.
    """

    def __init__(self, default_delay: float = 1.0):
        """
        Initialize rate limiter.

        Args:
            default_delay: Default delay between requests to same domain (seconds)
        """
        self.default_delay = default_delay
        self.domain_delays: Dict[str, float] = {}
        self.last_request: Dict[str, float] = {}
        self._lock = asyncio.Lock()

    def set_domain_delay(self, domain: str, delay: float) -> None:
        """Set custom delay for a specific domain."""
        self.domain_delays[domain] = delay

    def get_delay(self, domain: str) -> float:
        """Get the delay for a domain."""
        return self.domain_delays.get(domain, self.default_delay)

    async def wait(self, url: str) -> None:
        """
        Wait if necessary before making a request to the given URL.

        Args:
            url: URL to make request to
        """
        domain = urlparse(url).netloc

        async with self._lock:
            now = time.time()
            last = self.last_request.get(domain, 0)
            delay = self.get_delay(domain)

            elapsed = now - last
            if elapsed < delay:
                wait_time = delay - elapsed
                await asyncio.sleep(wait_time)

            self.last_request[domain] = time.time()

    def wait_sync(self, url: str) -> None:
        """
        Synchronous version of wait for non-async code.

        Args:
            url: URL to make request to
        """
        domain = urlparse(url).netloc

        now = time.time()
        last = self.last_request.get(domain, 0)
        delay = self.get_delay(domain)

        elapsed = now - last
        if elapsed < delay:
            wait_time = delay - elapsed
            time.sleep(wait_time)

        self.last_request[domain] = time.time()


class ExponentialBackoff:
    """
    Exponential backoff with jitter for retry logic.
    """

    def __init__(
        self,
        base: float = 1.0,
        max_delay: float = 30.0,
        max_retries: int = 3,
        jitter: float = 0.1
    ):
        """
        Initialize backoff calculator.

        Args:
            base: Base delay in seconds
            max_delay: Maximum delay cap
            max_retries: Maximum number of retries
            jitter: Random jitter factor (0.1 = +/- 10%)
        """
        self.base = base
        self.max_delay = max_delay
        self.max_retries = max_retries
        self.jitter = jitter

    def get_delay(self, attempt: int) -> float:
        """
        Calculate delay for a given attempt number.

        Args:
            attempt: Attempt number (0-indexed)

        Returns:
            Delay in seconds with jitter applied
        """
        # Exponential: base * 2^attempt
        delay = self.base * (2 ** attempt)

        # Apply jitter
        jitter_range = delay * self.jitter
        delay += random.uniform(-jitter_range, jitter_range)

        # Cap at max
        return min(delay, self.max_delay)

    def should_retry(self, attempt: int) -> bool:
        """Check if we should retry after this attempt."""
        return attempt < self.max_retries

    async def wait(self, attempt: int) -> None:
        """Wait for the appropriate backoff time."""
        if attempt > 0:
            delay = self.get_delay(attempt - 1)
            await asyncio.sleep(delay)

    def wait_sync(self, attempt: int) -> None:
        """Synchronous version of wait."""
        if attempt > 0:
            delay = self.get_delay(attempt - 1)
            time.sleep(delay)


class UserAgentRotator:
    """
    Rotate through a pool of User-Agent strings.
    """

    # Common browser User-Agents
    DEFAULT_AGENTS: ClassVar[List[str]] = [
        # Chrome on Windows
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
        # Chrome on Mac
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        # Firefox on Windows
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
        # Firefox on Mac
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:121.0) Gecko/20100101 Firefox/121.0",
        # Safari on Mac
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
        # Edge on Windows
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
    ]

    def __init__(self, agents: Optional[list] = None):
        """
        Initialize with optional custom agent list.

        Args:
            agents: List of User-Agent strings (uses defaults if None)
        """
        self.agents = agents or self.DEFAULT_AGENTS
        self._index = 0

    def get_random(self) -> str:
        """Get a random User-Agent."""
        return random.choice(self.agents)

    def get_next(self) -> str:
        """Get the next User-Agent in rotation."""
        agent = self.agents[self._index]
        self._index = (self._index + 1) % len(self.agents)
        return agent


def get_browser_headers(user_agent: Optional[str] = None) -> Dict[str, str]:
    """
    Get realistic browser headers.

    Args:
        user_agent: Optional User-Agent string (generates random if None)

    Returns:
        Dict of HTTP headers
    """
    if user_agent is None:
        user_agent = UserAgentRotator().get_random()

    return {
        "User-Agent": user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Cache-Control": "max-age=0",
    }


def get_image_headers(user_agent: Optional[str] = None, referer: Optional[str] = None) -> Dict[str, str]:
    """
    Get headers optimized for image downloads.

    Args:
        user_agent: Optional User-Agent string
        referer: Optional Referer header

    Returns:
        Dict of HTTP headers
    """
    if user_agent is None:
        user_agent = UserAgentRotator().get_random()

    headers = {
        "User-Agent": user_agent,
        "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "DNT": "1",
        "Connection": "keep-alive",
    }

    if referer:
        headers["Referer"] = referer

    return headers
