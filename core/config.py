"""
Configuration for image fetching system.
IP-agnostic design to support multiple franchises.

This file contains fetching-related settings only.
For other configurations, see:
  - Input/ip_sources.json: IP source data (edit this for sources/variants)
  - core/utils.py: Path utilities, URL helpers, and IP source functions
"""

import os

# Import BASE_DIR, OUTPUT_DIR and IP-related functions for use in this module
# Re-export get_sources and get_characters so extractors can import from config
from core.utils import (  # noqa: F401
    BASE_DIR,
    DEFAULT_GROUP,
    INPUT_DIR,
    OUTPUT_DIR,
    get_characters,
    get_input_file,
    get_ip_output_dir,
    get_output_dir,
    get_source_variants,
    get_sources,
    get_tag_variants,
    get_universe_for_ip,
    has_tag_variants,
    ip_has_groups,
    resolve_ip_alias,
)

# =============================================================================
# Fetching Settings
# =============================================================================

# Request settings
REQUEST_TIMEOUT = 15  # seconds
REQUEST_DELAY = 1.0  # seconds between requests to be respectful (sync mode)
MAX_RETRIES = 3
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

# Rate limiting per domain (seconds between requests)
RATE_LIMITS = {
    "bulbapedia.bulbagarden.net": 1.0,
    "archives.bulbagarden.net": 0.5,
    "pokemon.fandom.com": 1.0,
    "static.wikia.nocookie.net": 0.5,
    # Booru sites - configure in ip_sources.json
    "booru.example.com": 2.0,
}

# Retry/backoff settings
BACKOFF_BASE = 1.0  # Base delay for exponential backoff (seconds)
BACKOFF_MAX = 30.0  # Maximum backoff delay (seconds)
BACKOFF_JITTER = 0.1  # Random jitter factor (+/- 10%)

# Async settings
MAX_CONCURRENT_PER_SOURCE = 3  # Max concurrent requests per source
MAX_CONCURRENT_TOTAL = 10  # Max total concurrent requests

# Image settings - only these formats are accepted
SUPPORTED_IMAGE_FORMATS = [".png", ".jpg", ".jpeg", ".webp"]

# Logging
LOG_FILE = os.path.join(BASE_DIR, "fetch.log")
VERBOSE = True
