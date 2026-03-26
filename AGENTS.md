# AI Agent Guidelines

Instructions for AI agents working on this codebase. Follow these guidelines to maintain code quality and avoid breaking changes.

## Finding Context

### Key Entry Points

| What you're looking for | Where to find it |
|------------------------|------------------|
| API endpoints | `games/arena/app.py` |
| Database operations | `games/arena/database.py` |
| Matchup logic | `games/arena/matcher.py` |
| Image metadata parsing | `games/arena/image_index.py` |
| IP/source configuration | `core/utils.py` → loads `Input/ip_sources.json` |
| Rate limits & constants | `core/config.py` |
| Image fetching | `extractors/async_fetcher.py`, `extractors/async_scrapers.py` |
| Tests | `games/arena/tests/` |

### Search Strategies

1. **For API changes**: Start with `games/arena/app.py`, then trace to database/matcher
2. **For battle logic**: Start with `games/arena/matcher.py`
3. **For database schema**: Check `games/arena/database.py` → `init_db()` function
4. **For configuration**: Check `core/utils.py` for `IP_SOURCES`, `get_variant_groups()`, etc.
5. **For tests**: Mirror structure in `games/arena/tests/test_*.py`

### File Naming Conventions

- `test_*.py` - Test files (pytest)
- `*_utils.py` - Utility/helper functions
- `conftest.py` - Pytest fixtures

## Code Standards

### Python Style

- **Python version**: 3.11+
- **Type hints**: Use for function signatures
- **Docstrings**: Google style for public functions
- **Imports**: stdlib → third-party → local (separated by blank lines)
- **Line length**: 100 characters max
- **Formatting**: Follow existing patterns in the file

### Testing Standards

- **Framework**: pytest with pytest-asyncio for async tests
- **Fixtures**: Define in `conftest.py`
- **Naming**: `test_<function>_<scenario>`
- **API tests**: Use `httpx.AsyncClient` with `ASGITransport` (not real HTTP)

Example test:
```python
@pytest.mark.asyncio
async def test_post_matchup_returns_two_images(self, api_client, test_output_dir):
    """POST /api/matchup should return two different images."""
    response = await api_client.post("/api/matchup", json={
        "scope_level": "ip",
        "scope_ip": "dragonball"
    })
    assert response.status_code == 200
    data = response.json()
    assert data["img1"]["path"] != data["img2"]["path"]
```

### Database Conventions

- Use parameterized queries (never string interpolation)
- Always call `init_db()` before operations
- Use `get_db_path()` to get the current database path
- Transactions: use `conn.commit()` explicitly

## Safe Operations

These operations are safe and can be done without special consideration:

| Operation | Notes |
|-----------|-------|
| Reading any file | Safe |
| Running tests | `pytest games/arena/tests/ -v` |
| Adding new tests | Add to appropriate `test_*.py` file |
| Adding new API endpoints | Add to `app.py`, follow existing patterns |
| Refactoring internal functions | Ensure tests pass |
| Updating docstrings/comments | Safe |
| Adding logging | Use `games/arena/logging_config.py` |

## Dangerous Operations

These operations require extra care:

| Operation | Risk | Mitigation |
|-----------|------|------------|
| Modifying database schema | Data loss | Create migration script in `scripts/` |
| Renaming functions/classes | Import breaks | Search all files, update imports |
| Changing `ip_sources.json` structure | Config breaks | Update `core/utils.py` accessors |
| Deleting files from `Output/` | Irreversible | Confirm with user first |
| Modifying `database.py` | Data corruption | Run full test suite |
| Changing filename parsing | Index breaks | Test with real files |

### Before Dangerous Operations

1. **Run the test suite**: `pytest games/arena/tests/ -v`
2. **Search for usages**: Use grep/glob to find all references
3. **Create a backup**: For database changes, copy `arena.db` first
4. **Test incrementally**: Make small changes, verify each step

## Contributing Guidelines

### Adding a New Feature

1. **Understand existing patterns**: Read related code first
2. **Add tests first**: Write failing tests for the new behavior
3. **Implement the feature**: Make tests pass
4. **Run full suite**: Ensure no regressions
5. **Update documentation**: If adding API endpoints, update README

### Fixing a Bug

1. **Reproduce the bug**: Write a failing test
2. **Fix the code**: Make the test pass
3. **Check for related bugs**: Search for similar patterns
4. **Run full suite**: Ensure no regressions

### Refactoring

1. **Don't change behavior**: Tests should pass without modification
2. **Small commits**: One logical change per commit
3. **Run tests frequently**: After each significant change

## File Structure Reference

```
kanto_kompetition/
├── core/                       # Shared utilities
│   ├── config.py              # Constants, rate limits
│   └── utils.py               # IP_SOURCES, variant helpers
├── extractors/                 # Image fetching
│   ├── async_fetcher.py       # Async download logic
│   ├── async_scrapers.py      # Site-specific scrapers
│   ├── base_fetcher.py        # Base class
│   ├── fetcher.py             # Sync fetcher
│   └── pipeline.py            # Orchestration
├── games/arena/                # Battle application
│   ├── app.py                 # FastAPI routes
│   ├── database.py            # SQLite operations
│   ├── database_stats.py      # Stats queries
│   ├── database_merge.py      # DB merging tools
│   ├── matcher.py             # Matchup generation
│   ├── image_index.py         # Image metadata
│   ├── logging_config.py      # Centralized logging
│   ├── models.py              # Pydantic models
│   ├── admin_routes.py        # Admin endpoints
│   ├── analysis/              # Reporting tools
│   │   ├── queries.py
│   │   ├── reports.py
│   │   └── formatters.py
│   └── tests/                 # Test suite
│       ├── conftest.py        # Fixtures
│       ├── test_api.py        # API integration tests
│       ├── test_database.py   # Database unit tests
│       ├── test_matcher.py    # Matcher unit tests
│       ├── test_image_index.py
│       └── test_config.py
├── cli/                       # Command-line tools
│   └── fetch_images.py        # Image fetching CLI
├── scripts/                   # Migration scripts
│   ├── migrate_filenames.py
│   ├── migrate_duplicates.py
│   └── backfill_battle_variants.py
├── Input/                     # Configuration (gitignored)
│   └── ip_sources.json
├── Output/                    # Images (gitignored)
├── README.md                  # Project overview
└── AGENTS.md                  # This file
```

## Common Patterns

### Adding an API Endpoint

```python
# In app.py
@app.post("/api/new-endpoint")
async def new_endpoint(request: NewRequest):
    """Description of what this endpoint does."""
    # Validate input
    # Call database/matcher functions
    # Return response
    return {"success": True, "data": result}
```

### Adding a Database Function

```python
# In database.py
def new_db_function(param: str) -> dict:
    """Description of what this function does."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT ... WHERE param = ?", (param,))
    result = cursor.fetchone()
    conn.close()
    return dict(result) if result else None
```

### Adding a Test

```python
# In test_*.py
class TestNewFeature:
    """Tests for new feature."""

    def test_basic_case(self, test_db):
        """Test the basic happy path."""
        result = some_function()
        assert result is not None

    def test_edge_case(self, test_db):
        """Test an edge case."""
        with pytest.raises(ValueError):
            some_function(invalid_input)
```

## Logging

Use the centralized logging configuration:

```python
from games.arena.logging_config import get_logger

logger = get_logger(__name__)

# Usage
logger.debug("Detailed info for debugging")
logger.info("Normal operation info")
logger.warning("Something unexpected but not critical")
logger.error("Something went wrong")
```

Logs are written to:
- `arena.log` - All logs (DEBUG level)
- `arena_summary.log` - High-level actions only (INFO level)

## Questions?

If something is unclear:
1. Check existing code for patterns
2. Run the tests to understand expected behavior
3. Read the docstrings
4. Check the [Public Release Roadmap](.claude/plans/recursive-weaving-globe.md) for planned changes
