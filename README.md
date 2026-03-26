# Epic Universe Battle

An image battle and tierlist application. Pit images against each other in head-to-head matchups to generate rankings using ELO-style scoring.

## Overview

Epic Universe Battle is a full-stack application for running image comparison battles. Users select a scope (IP, character group, or individual character), and the system presents pairs of images for comparison. Battle results are tracked in a SQLite database with ELO ratings, win/loss stats, and complete battle history.

**Current Status:** Internal development.

## Features

- **Battle Mode**: Head-to-head image comparisons with ELO rating system
- **Gallery View**: Browse all images with filtering by IP, source, character, and variant
- **Leaderboard**: Rankings sorted by win rate and ELO score
- **Undo System**: Reverse recent battles to correct mistakes
- **Flexible Scoping**: Battle at IP level, character group level, or character level
- **Variant Matching**: Optionally constrain battles to same source or variant group
- **Battle History**: Full audit trail of all comparisons
- **Image Fetching**: Automated pipeline for fetching images from various sources

## Tech Stack

| Component | Technology |
|-----------|------------|
| Backend | Python 3.9+, FastAPI |
| Frontend | Jinja2 templates, vanilla JS |
| Database | SQLite |
| Image Serving | Static file serving via FastAPI |

## Project Structure

```
kanto_kompetition/
├── core/                    # Shared utilities and configuration
│   ├── config.py           # Rate limits, constants
│   └── utils.py            # IP sources, variant helpers
├── extractors/             # Image fetching pipeline
│   ├── async_fetcher.py    # Async image downloading
│   ├── async_scrapers.py   # Booru-style site scrapers
│   ├── fetcher.py          # Sync fetcher
│   └── pipeline.py         # Orchestration
├── games/
│   └── arena/              # Battle application
│       ├── app.py          # FastAPI application
│       ├── database.py     # SQLite operations
│       ├── matcher.py      # Matchup generation logic
│       ├── image_index.py  # Image metadata indexing
│       ├── logging_config.py # Centralized logging
│       └── tests/          # pytest test suite (68 tests)
├── cli/                    # Command-line tools
│   ├── fetch_images.py     # Image fetching CLI
│   └── fetch_booru_aliases.py # Fetch character aliases from booru sites
├── Input/                  # Configuration (gitignored)
│   └── ip_sources.json     # Source configuration
├── Output/                 # Downloaded images (gitignored)
└── scripts/                # Migration and utility scripts
```

## Quick Start

### Prerequisites

- Python 3.9+
- pip

### Installation

```bash
# Clone the repository
git clone <repo-url>
cd kanto_kompetition

# Install dependencies
pip install -r requirements.txt

# Initialize the database
python -c "from games.arena.database import init_db; init_db()"
```

### Running the Server

```bash
# Start the FastAPI server
uvicorn games.arena.app:app --reload --port 5000

# Open in browser
# http://localhost:5000
```

### Running Tests

```bash
# Run all tests
pytest games/arena/tests/ -v

# Run with coverage
pytest games/arena/tests/ --cov=games/arena
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/matchup` | POST | Get two images for battle |
| `/api/result` | POST | Submit battle result |
| `/api/undo` | POST | Undo last battle |
| `/api/delete` | POST | Delete an image |
| `/api/leaderboard` | GET | Get ranked images |
| `/api/history` | GET | Get recent battles |
| `/api/stats/image` | GET | Get stats for an image |
| `/api/refresh` | POST | Refresh image index |

## Configuration

The application uses `Input/ip_sources.json` for source configuration. See `Input/ip_sources.example.json` for the expected structure:

```json
{
  "nintendo": {
    "pokemon": {
      "gen_aliases": { "archeus": "8A" },
      "sources": [
        {
          "name": "bulbapedia",
          "short_name": "bulba",
          "site_type": "wiki",
          "priority": 3,
          "base_url": "https://bulbapedia.bulbagarden.net"
        }
      ]
    }
  }
}
```

## Image Fetching CLI

The project includes a CLI for fetching images from various sources:

```bash
# Basic: 1 image from 1 source
python cli/fetch_images.py --ip pokemon 1 1 1

# 2 images from 2 sources, trying all name variants
python cli/fetch_images.py --ip pokemon 2 2 3

# Dry run to preview
python cli/fetch_images.py --ip pokemon 2 2 3 --dry-run
```

### Output Filename Format

```
{character_name}-{source}-{variant}-{count}.{ext}
```

Examples:
- `Goku-dbwiki-1.png` - First image from Dragon Ball Wiki
- `Harry_Potter-hpfandom-portrait-1.jpg` - Image with portrait variant tag

## For AI Agents

See [AGENTS.md](AGENTS.md) for detailed instructions on:
- Finding context in the codebase
- Code standards and conventions
- Safe vs dangerous operations
- How to contribute

## License

Private repository. Not for redistribution.
