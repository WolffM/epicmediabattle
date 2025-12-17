"""
FastAPI Arena application.
Run with: uvicorn app:app --reload --port 5000
Or: python app.py
"""

import sys
from pathlib import Path
from typing import Optional

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# Add parent paths for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from games.arena import database, matcher
from games.arena.admin_routes import router as admin_router
from games.arena.image_index import get_index, refresh_index
from games.arena.logging_config import get_logger
from games.arena.models import (
    BattleResult,
    BulkDeleteRequest,
    DeleteRequest,
    MatchupRequest,
    MergeRequest,
    UndoRequest,
)
from games.arena.path_utils import (
    add_stats_to_matchup,
    extract_matchup_kwargs,
    find_image_by_path,
    find_images_by_paths,
    validate_path_in_output,
)
from games.arena.server_utils import kill_existing_server

# Get logger from centralized config (also initializes logging)
logger = get_logger(__name__)

# Setup paths
BASE_DIR = Path(__file__).parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"
OUTPUT_DIR = BASE_DIR.parent.parent / "Output"

# Create app
app = FastAPI(title="Kanto Kompetition Arena")

# Mount static files and include routers
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.include_router(admin_router)

# Setup templates
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


# ============================================================================
# HTML Routes
# ============================================================================

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Main setup page."""
    idx = get_index()
    return templates.TemplateResponse("index.html", {
        "request": request,
        "universes": idx.get_universes(),
        "ips": idx.get_ips()
    })


@app.get("/gallery", response_class=HTMLResponse)
async def gallery_page(request: Request):
    """Gallery page with card view of all images."""
    idx = get_index()
    return templates.TemplateResponse("gallery.html", {
        "request": request,
        "universes": idx.get_universes(),
        "ips": idx.get_ips()
    })


@app.get("/battle", response_class=HTMLResponse)
async def battle_page(
    request: Request,
    scope_level: str,
    scope_ip: str,
    scope_universe: Optional[str] = None,
    scope_group: Optional[str] = None,
    scope_character: Optional[str] = None,
    scope_source: Optional[str] = None,
    scope_variant: Optional[str] = None,
    match_source: bool = False,
    match_variant: bool = False,
    match_variant_group: bool = False
):
    """Battle page with two images."""
    logger.info(f"=== /battle page: level={scope_level}, universe={scope_universe}, ip={scope_ip}, group={scope_group} ===")

    matchup = matcher.get_matchup(
        scope_level=scope_level, scope_ip=scope_ip, scope_group=scope_group,
        scope_character=scope_character, scope_source=scope_source,
        scope_variant=scope_variant, match_source=match_source,
        match_variant=match_variant, match_variant_group=match_variant_group,
        scope_universe=scope_universe
    )

    if not matchup:
        return templates.TemplateResponse("error.html", {
            "request": request,
            "message": "Not enough images for a matchup with the selected criteria."
        })

    img1, img2 = matchup
    img1['stats'] = database.get_image_stats(img1['path'])
    img2['stats'] = database.get_image_stats(img2['path'])

    return templates.TemplateResponse("battle.html", {
        "request": request, "img1": img1, "img2": img2,
        "scope_level": scope_level, "scope_universe": scope_universe or "",
        "scope_ip": scope_ip, "scope_group": scope_group or "",
        "scope_character": scope_character or "", "scope_source": scope_source or "",
        "scope_variant": scope_variant or "", "match_source": match_source,
        "match_variant": match_variant, "match_variant_group": match_variant_group
    })


# ============================================================================
# API Routes
# ============================================================================

@app.get("/api/gallery/images")
async def get_gallery_images():
    """Get all images with stats for gallery view."""
    idx = get_index()
    return [
        {**img.to_dict(), 'stats': database.get_image_stats(img.path)}
        for img in idx.images
    ]


@app.get("/api/options")
async def get_options(
    scope_universe: Optional[str] = None,
    scope_ip: Optional[str] = None,
    scope_group: Optional[str] = None,
    scope_character: Optional[str] = None,
    scope_source: Optional[str] = None
):
    """Get cascading dropdown options."""
    return JSONResponse(matcher.get_scope_options(
        scope_universe=scope_universe, scope_ip=scope_ip,
        scope_group=scope_group, scope_character=scope_character,
        scope_source=scope_source
    ))


@app.post("/api/matchup")
async def get_new_matchup(req: MatchupRequest):
    """Get a new random matchup."""
    matchup = matcher.get_matchup(**extract_matchup_kwargs(req))
    if not matchup:
        raise HTTPException(status_code=404, detail="No valid matchup found")
    img1, img2 = matchup
    add_stats_to_matchup(img1, img2, database.get_image_stats)
    return {"img1": img1, "img2": img2}


@app.post("/api/result")
async def log_result(result: BattleResult):
    """Log a battle result and return next matchup."""
    logger.info(f"=== /api/result: winner={result.winner_path}, loser={result.loser_path} ===")

    index = get_index()
    images = find_images_by_paths(index, [result.winner_path, result.loser_path])
    winner, loser = images[result.winner_path], images[result.loser_path]

    if not winner or not loser:
        raise HTTPException(status_code=400, detail="Invalid image paths")

    scope = {
        'scope_level': result.scope_level, 'scope_universe': result.scope_universe,
        'scope_ip': result.scope_ip, 'scope_group': result.scope_group,
        'scope_character': result.scope_character, 'scope_source': result.scope_source,
        'scope_variant': result.scope_variant, 'match_source': result.match_source,
        'match_variant': result.match_variant
    }
    battle_id = database.log_battle(scope, winner, loser)

    next_matchup = matcher.get_matchup(**extract_matchup_kwargs(result))
    if not next_matchup:
        return {"battle_id": battle_id, "next": None}

    img1, img2 = next_matchup
    add_stats_to_matchup(img1, img2, database.get_image_stats)
    return {"battle_id": battle_id, "next": {"img1": img1, "img2": img2}}


@app.post("/api/undo")
async def undo_battle(req: UndoRequest):
    """Undo a battle and return the matchup to restore."""
    result = database.undo_battle(req.battle_id)
    if not result:
        raise HTTPException(status_code=404, detail="Battle not found")

    winner, loser = result['winner'], result['loser']
    if winner and loser:
        index = get_index()
        images = find_images_by_paths(index, [winner['path'], loser['path']])
        img1_data, img2_data = images[winner['path']], images[loser['path']]
        matchup = {"img1": img1_data, "img2": img2_data} if img1_data and img2_data else None
        return {"success": True, "battle_id": req.battle_id, "matchup": matchup}

    return {"success": True, "battle_id": req.battle_id, "matchup": None}


@app.post("/api/delete")
async def delete_image(req: DeleteRequest):
    """Delete an image file (no contest - no battle record)."""
    logger.info(f"=== /api/delete: {req.delete_path} ===")
    delete_path = Path(req.delete_path)

    if not delete_path.exists():
        raise HTTPException(status_code=404, detail="Image not found")
    if not validate_path_in_output(delete_path, OUTPUT_DIR):
        raise HTTPException(status_code=403, detail="Access denied")

    index = get_index()
    deleted_image = find_image_by_path(index, req.delete_path)
    if deleted_image:
        database.log_deletion(deleted_image)

    try:
        delete_path.unlink()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete: {e!s}") from e

    refresh_index()

    # Try to keep the surviving image in the matchup
    next_matchup = matcher.get_matchup_with_image(
        keep_path=req.keep_path, **extract_matchup_kwargs(req)
    )
    if not next_matchup:
        next_matchup = matcher.get_matchup(**extract_matchup_kwargs(req))

    if not next_matchup:
        return {"success": True, "next": None}

    img1, img2 = next_matchup
    return {"success": True, "next": {"img1": img1, "img2": img2}}


@app.post("/api/gallery/delete-bulk")
async def delete_bulk(req: BulkDeleteRequest):
    """Bulk delete multiple images."""
    logger.info(f"=== /api/gallery/delete-bulk: {len(req.paths)} paths ===")
    deleted, errors = 0, []
    index = get_index()

    for path in req.paths:
        file_path = Path(path)
        if not file_path.exists():
            errors.append(f"Not found: {path}")
            continue
        if not validate_path_in_output(file_path, OUTPUT_DIR):
            errors.append(f"Access denied: {path}")
            continue

        deleted_image = find_image_by_path(index, path)
        if deleted_image:
            database.log_deletion(deleted_image)

        try:
            file_path.unlink()
            deleted += 1
        except Exception as e:
            errors.append(f"Failed to delete {path}: {e!s}")

    refresh_index()
    return {"deleted": deleted, "errors": errors if errors else None}


@app.post("/api/gallery/merge")
async def merge_images(req: MergeRequest):
    """Merge duplicate images - combine battle records and delete duplicates."""
    logger.info(f"=== /api/gallery/merge: {len(req.paths)} paths ===")

    if len(req.paths) < 2:
        raise HTTPException(status_code=400, detail="Need at least 2 images to merge")

    index = get_index()
    images_info = []

    for path in req.paths:
        file_path = Path(path)
        if not file_path.exists():
            raise HTTPException(status_code=404, detail=f"Image not found: {path}")
        if not validate_path_in_output(file_path, OUTPUT_DIR):
            raise HTTPException(status_code=403, detail=f"Access denied: {path}")

        img_dict = find_image_by_path(index, path)
        if img_dict:
            try:
                from PIL import Image
                with Image.open(path) as pil_img:
                    img_dict['resolution'] = pil_img.width * pil_img.height
            except Exception:
                img_dict['resolution'] = 0
            img_dict['created'] = file_path.stat().st_ctime
            images_info.append(img_dict)

    if len(images_info) != len(req.paths):
        raise HTTPException(status_code=404, detail="Some images not found in index")

    # Select surviving image: highest resolution, then oldest
    images_info.sort(key=lambda x: (-x['resolution'], x['created']))
    surviving, duplicates = images_info[0], images_info[1:]

    duplicate_paths = [img['path'] for img in duplicates]
    merge_result = database.merge_images(surviving['path'], duplicate_paths)

    for dup in duplicates:
        database.log_deletion(dup)
        try:
            Path(dup['path']).unlink()
        except Exception as e:
            logger.error(f"Failed to delete duplicate {dup['path']}: {e}")

    refresh_index()
    return {
        "surviving_path": surviving['path'],
        "duplicates_deleted": len(duplicates),
        "battles_merged": merge_result['battles_merged']
    }


@app.get("/api/stats/image")
async def get_image_stats(path: str):
    """Get stats for a specific image."""
    return database.get_image_stats(path)


@app.get("/api/stats/character")
async def get_character_stats(name: str, group: Optional[str] = None):
    """Get stats for a character."""
    return database.get_character_stats(name, group)


@app.get("/api/leaderboard")
async def get_leaderboard(
    scope_universe: Optional[str] = None,
    scope_ip: Optional[str] = None,
    scope_group: Optional[str] = None,
    limit: int = 20
):
    """Get image leaderboard."""
    return database.get_leaderboard(
        scope_universe=scope_universe, scope_ip=scope_ip,
        scope_group=scope_group, limit=limit
    )


@app.get("/api/history")
async def get_history(limit: int = 50):
    """Get recent battle history."""
    return database.get_recent_battles(limit)


@app.get("/api/stats/deletions")
async def get_deletion_stats(group_by: str = "variant"):
    """Get deletion statistics grouped by variant, source, or name."""
    return database.get_deletion_stats(group_by)


@app.get("/api/deletions")
async def get_deletions(limit: int = 100):
    """Get detailed deletion records."""
    return database.get_deletion_details(limit)


@app.post("/api/refresh")
async def refresh():
    """Refresh the image index."""
    idx = refresh_index()
    return {"count": len(idx.images)}


# ============================================================================
# Image serving
# ============================================================================

@app.get("/images/{path:path}")
async def serve_image(path: str):
    """Serve images from the Output directory."""
    full_path = OUTPUT_DIR / path
    if not full_path.exists():
        raise HTTPException(status_code=404, detail="Image not found")
    try:
        full_path.resolve().relative_to(OUTPUT_DIR.resolve())
    except ValueError as e:
        raise HTTPException(status_code=403, detail="Access denied") from e
    return FileResponse(str(full_path))


# ============================================================================
# Main
# ============================================================================


def run_server(host: str = "127.0.0.1", port: int = 5000):
    """Start the Arena server."""
    if kill_existing_server(port):
        import time
        time.sleep(0.5)

    print("Starting Arena server...")
    print(f"Output directory: {OUTPUT_DIR}")

    STATIC_DIR.mkdir(exist_ok=True)
    TEMPLATES_DIR.mkdir(exist_ok=True)

    idx = get_index()
    print(f"Indexed {len(idx.images)} images")

    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    run_server()
