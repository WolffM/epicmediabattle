"""
Pytest fixtures for arena tests.
"""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest
import pytest_asyncio

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Test data directory
TEST_DATA_DIR = Path(__file__).parent / "test_data"


@pytest.fixture(scope="function")
def test_db(tmp_path):
    """
    Create a fresh test database for each test.
    Sets up the database path, initializes schema, and cleans up after.
    """
    from games.arena import database

    # Create test database path
    db_path = tmp_path / "test.db"

    # Set the database path for testing
    database.set_db_path(db_path)

    # Initialize the schema
    database.init_db()

    yield db_path

    # Cleanup - reset to default path
    database.set_db_path(None)


@pytest.fixture(scope="function")
def test_output_dir(tmp_path):
    """
    Create a temporary output directory with sample images for testing.
    Structure: {tmp}/Output/nintendo/pokemon/1/
    """
    output_dir = tmp_path / "Output"
    pokemon_dir = output_dir / "nintendo" / "pokemon" / "1"
    pokemon_dir.mkdir(parents=True)

    # Create some dummy image files for testing
    sample_images = [
        "Goku-dbwiki-super_saiyan-1.jpg",
        "Goku-dbwiki-base-2.jpg",
        "Goku-dbwiki-ui-1.jpg",
        "Vegeta-dbwiki-ssb-1.jpg",
        "Vegeta-bulba-1.png",
        "Gohan-dbwiki-super_saiyan-1.jpg",
        "Gohan-dbwiki-ui-1.jpg",
        "Trunks-dbwiki-future-1.jpg",
    ]

    for img_name in sample_images:
        img_path = pokemon_dir / img_name
        # Create empty file (just for testing metadata parsing)
        img_path.touch()

    yield output_dir


@pytest.fixture(scope="function")
def test_index(test_output_dir):
    """
    Create an ImageIndex that scans the test output directory.
    """
    from games.arena.image_index import ImageIndex

    index = ImageIndex()
    index.scan(test_output_dir)

    return index


@pytest.fixture(scope="function")
def sample_image_dicts():
    """
    Return sample image dictionaries for matcher testing.
    """
    return [
        {
            "path": "/test/dragonball/saiyans/Goku-dbwiki-super_saiyan-1.jpg",
            "name": "Goku",
            "group_name": "saiyans",
            "source": "dbwiki",
            "variant": "super_saiyan",
            "variant_group": "transformation",
            "ip": "dragonball",
            "filename": "Goku-dbwiki-super_saiyan-1.jpg",
        },
        {
            "path": "/test/dragonball/saiyans/Goku-dbwiki-base-2.jpg",
            "name": "Goku",
            "group_name": "saiyans",
            "source": "dbwiki",
            "variant": "base",
            "variant_group": "transformation",
            "ip": "dragonball",
            "filename": "Goku-dbwiki-base-2.jpg",
        },
        {
            "path": "/test/dragonball/saiyans/Vegeta-dbwiki-ssb-1.jpg",
            "name": "Vegeta",
            "group_name": "saiyans",
            "source": "dbwiki",
            "variant": "ssb",
            "variant_group": "transformation",
            "ip": "dragonball",
            "filename": "Vegeta-dbwiki-ssb-1.jpg",
        },
        {
            "path": "/test/dragonball/saiyans/Gohan-dbwiki-ultimate-1.jpg",
            "name": "Gohan",
            "group_name": "saiyans",
            "source": "dbwiki",
            "variant": "ultimate",
            "variant_group": "transformation",
            "ip": "dragonball",
            "filename": "Gohan-dbwiki-ultimate-1.jpg",
        },
        {
            "path": "/test/dragonball/saiyans/Trunks-dbwiki-future-1.jpg",
            "name": "Trunks",
            "group_name": "saiyans",
            "source": "dbwiki",
            "variant": "future",
            "variant_group": "timeline",
            "ip": "dragonball",
            "filename": "Trunks-dbwiki-future-1.jpg",
        },
        {
            "path": "/test/dragonball/saiyans/Gohan-bulba-1.png",
            "name": "Gohan",
            "group_name": "saiyans",
            "source": "bulba",
            "variant": None,
            "variant_group": None,
            "ip": "dragonball",
            "filename": "Gohan-bulba-1.png",
        },
    ]


# ============================================================================
# API Integration Test Fixtures
# ============================================================================

@pytest_asyncio.fixture
async def api_client(test_db, test_output_dir):
    """
    Async HTTP client for API integration tests.
    Uses httpx with ASGITransport to avoid actual network requests (no 429s).
    """
    from httpx import ASGITransport, AsyncClient

    # Import app after test_db is set up (database path is configured)
    from games.arena import app as app_module

    # Patch OUTPUT_DIR to use test directory
    with patch.object(app_module, 'OUTPUT_DIR', test_output_dir):
        transport = ASGITransport(app=app_module.app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client


@pytest.fixture
def api_test_images(test_output_dir):
    """
    Create actual image files in the test output directory for API tests.
    Returns dict of image paths.
    """
    pokemon_dir = test_output_dir / "nintendo" / "pokemon" / "1"
    pokemon_dir.mkdir(parents=True, exist_ok=True)

    # Create actual files with some content
    images = {
        "winner": pokemon_dir / "Vegeta-dbwiki-ssb-1.jpg",
        "loser": pokemon_dir / "Gohan-dbwiki-ultimate-1.jpg",
        "extra1": pokemon_dir / "Trunks-dbwiki-future-1.jpg",
        "extra2": pokemon_dir / "Goku-dbwiki-super_saiyan-1.jpg",
    }

    for path in images.values():
        path.write_bytes(b"fake image content")

    return {name: str(path) for name, path in images.items()}
