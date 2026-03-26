"""
API integration tests for Arena endpoints.

Uses httpx AsyncClient with ASGITransport to test FastAPI endpoints
without making actual network requests (avoids 429 rate limits).
"""

import sys
from pathlib import Path

import pytest

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


class TestMatchupAPI:
    """Test matchup generation endpoints."""

    @pytest.mark.asyncio
    async def test_post_matchup_returns_two_images(self, api_client, test_output_dir):
        """POST /api/matchup should return two different images."""
        response = await api_client.post("/api/matchup", json={
            "scope_level": "ip",
            "scope_ip": "pokemon"
        })

        assert response.status_code == 200
        data = response.json()

        assert "img1" in data
        assert "img2" in data
        assert data["img1"]["path"] != data["img2"]["path"]
        assert data["img1"]["ip"] == "pokemon"
        assert data["img2"]["ip"] == "pokemon"


class TestBattleResultAPI:
    """Test battle result logging endpoints."""

    @pytest.mark.asyncio
    async def test_post_result_logs_battle(self, api_client, test_output_dir):
        """POST /api/result should log battle and return next matchup."""
        # First get a matchup
        matchup_response = await api_client.post("/api/matchup", json={
            "scope_level": "ip",
            "scope_ip": "pokemon"
        })
        assert matchup_response.status_code == 200
        matchup = matchup_response.json()

        # Submit result
        response = await api_client.post("/api/result", json={
            "winner_path": matchup["img1"]["path"],
            "loser_path": matchup["img2"]["path"],
            "scope_level": "ip",
            "scope_ip": "pokemon"
        })

        assert response.status_code == 200
        data = response.json()

        assert "battle_id" in data
        assert data["battle_id"] is not None
        # Should return next matchup
        assert "next" in data

    @pytest.mark.asyncio
    async def test_post_result_updates_stats(self, api_client, test_output_dir):
        """Battle result should update win/loss stats for images."""
        # Get a matchup
        matchup_response = await api_client.post("/api/matchup", json={
            "scope_level": "ip",
            "scope_ip": "pokemon"
        })
        matchup = matchup_response.json()
        winner_path = matchup["img1"]["path"]
        loser_path = matchup["img2"]["path"]

        # Submit result
        await api_client.post("/api/result", json={
            "winner_path": winner_path,
            "loser_path": loser_path,
            "scope_level": "ip",
            "scope_ip": "pokemon"
        })

        # Check stats via API
        winner_stats = await api_client.get(f"/api/stats/image?path={winner_path}")
        loser_stats = await api_client.get(f"/api/stats/image?path={loser_path}")

        assert winner_stats.status_code == 200
        assert loser_stats.status_code == 200

        winner_data = winner_stats.json()
        loser_data = loser_stats.json()

        assert winner_data["wins"] >= 1
        assert loser_data["losses"] >= 1


class TestUndoAPI:
    """Test battle undo functionality."""

    @pytest.mark.asyncio
    async def test_undo_reverses_battle(self, api_client, test_output_dir):
        """POST /api/undo should reverse a battle and restore stats."""
        # Get a matchup and log a battle
        matchup_response = await api_client.post("/api/matchup", json={
            "scope_level": "ip",
            "scope_ip": "pokemon"
        })
        matchup = matchup_response.json()

        result_response = await api_client.post("/api/result", json={
            "winner_path": matchup["img1"]["path"],
            "loser_path": matchup["img2"]["path"],
            "scope_level": "ip",
            "scope_ip": "pokemon"
        })
        result = result_response.json()
        battle_id = result["battle_id"]

        # Undo the battle
        undo_response = await api_client.post("/api/undo", json={
            "battle_id": battle_id
        })

        assert undo_response.status_code == 200
        undo_data = undo_response.json()

        assert undo_data["success"] is True
        assert undo_data["battle_id"] == battle_id

    @pytest.mark.asyncio
    async def test_undo_nonexistent_returns_404(self, api_client, test_db):
        """POST /api/undo with invalid battle_id should return 404."""
        response = await api_client.post("/api/undo", json={
            "battle_id": "nonexistent-battle-id"
        })

        assert response.status_code == 404


class TestDeleteAPI:
    """Test image deletion endpoints."""

    @pytest.mark.asyncio
    async def test_delete_removes_file(self, api_client, api_test_images, test_output_dir):
        """POST /api/delete should physically remove the file."""
        # Refresh index to include our test images
        await api_client.post("/api/refresh")

        # Get the file path that exists
        file_path = api_test_images["extra1"]
        keep_path = api_test_images["winner"]

        # Verify file exists
        assert Path(file_path).exists()

        # Delete it
        response = await api_client.post("/api/delete", json={
            "delete_path": file_path,
            "keep_path": keep_path,
            "scope_level": "ip",
            "scope_ip": "pokemon"
        })

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

        # Verify file is gone
        assert not Path(file_path).exists()

    @pytest.mark.asyncio
    async def test_delete_nonexistent_returns_404(self, api_client, test_db, test_output_dir):
        """POST /api/delete with nonexistent path should return 404."""
        response = await api_client.post("/api/delete", json={
            "delete_path": "/nonexistent/path.jpg",
            "keep_path": "/some/other/path.jpg",
            "scope_level": "ip",
            "scope_ip": "pokemon"
        })

        assert response.status_code == 404


class TestBulkDeleteAPI:
    """Test bulk deletion endpoint."""

    @pytest.mark.asyncio
    async def test_bulk_delete_removes_files(self, api_client, api_test_images, test_output_dir):
        """POST /api/gallery/delete-bulk should delete multiple files."""
        await api_client.post("/api/refresh")

        paths_to_delete = [api_test_images["extra1"], api_test_images["extra2"]]

        # Verify files exist
        for path in paths_to_delete:
            assert Path(path).exists()

        response = await api_client.post("/api/gallery/delete-bulk", json={
            "paths": paths_to_delete
        })

        assert response.status_code == 200
        data = response.json()

        assert data["deleted"] == 2
        assert data["errors"] is None

        # Verify files are gone
        for path in paths_to_delete:
            assert not Path(path).exists()


class TestLeaderboardAPI:
    """Test leaderboard and stats endpoints."""

    @pytest.mark.asyncio
    async def test_get_leaderboard(self, api_client, test_output_dir):
        """GET /api/leaderboard should return sorted images by win rate."""
        # First log some battles to have leaderboard data
        matchup_response = await api_client.post("/api/matchup", json={
            "scope_level": "ip",
            "scope_ip": "pokemon"
        })
        matchup = matchup_response.json()

        # Log multiple battles (need at least 3 for leaderboard)
        for _ in range(5):
            await api_client.post("/api/result", json={
                "winner_path": matchup["img1"]["path"],
                "loser_path": matchup["img2"]["path"],
                "scope_level": "ip",
                "scope_ip": "pokemon"
            })

        # Get leaderboard
        response = await api_client.get("/api/leaderboard?scope_ip=pokemon&limit=10")

        assert response.status_code == 200
        data = response.json()

        assert isinstance(data, list)
        if len(data) > 0:
            # First entry should have highest win rate
            assert "win_rate" in data[0]
            assert "path" in data[0]


class TestHistoryAPI:
    """Test battle history endpoint."""

    @pytest.mark.asyncio
    async def test_get_history(self, api_client, test_output_dir):
        """GET /api/history should return recent battles."""
        # Log a battle first
        matchup_response = await api_client.post("/api/matchup", json={
            "scope_level": "ip",
            "scope_ip": "pokemon"
        })
        matchup = matchup_response.json()

        await api_client.post("/api/result", json={
            "winner_path": matchup["img1"]["path"],
            "loser_path": matchup["img2"]["path"],
            "scope_level": "ip",
            "scope_ip": "pokemon"
        })

        # Get history
        response = await api_client.get("/api/history?limit=10")

        assert response.status_code == 200
        data = response.json()

        assert isinstance(data, list)
        assert len(data) >= 1

        # Check structure
        battle = data[0]
        assert "battle_id" in battle
        assert "winner" in battle
        assert "loser" in battle
