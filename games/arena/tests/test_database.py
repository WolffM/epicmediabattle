"""
Tests for database module functions.

These tests cover all database functions to ensure the split into
database.py, database_stats.py, and database_merge.py doesn't break anything.
"""



class TestDatabaseCore:
    """Tests for core database functions (schema, connection, battle logging)."""

    def test_init_db_creates_tables(self, test_db):
        """init_db should create all required tables."""
        from games.arena import database

        conn = database.get_connection()
        cursor = conn.cursor()

        # Check battles table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='battles'")
        assert cursor.fetchone() is not None

        # Check deletions table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='deletions'")
        assert cursor.fetchone() is not None

        # Check image_stats table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='image_stats'")
        assert cursor.fetchone() is not None

        conn.close()

    def test_log_battle_returns_battle_id(self, test_db):
        """log_battle should return a unique battle_id."""
        from games.arena import database

        scope = {
            "scope_level": "ip",
            "scope_ip": "pokemon",
            "scope_group": None,
            "scope_character": None,
            "scope_source": None,
            "scope_variant": None,
            "match_source": False,
            "match_variant": False,
        }

        winner = {
            "path": "/test/winner.jpg",
            "name": "Winner",
            "group_name": "1",
            "source": "dbwiki",
            "variant": "solo",
            "ip": "pokemon",
        }

        loser = {
            "path": "/test/loser.jpg",
            "name": "Loser",
            "group_name": "1",
            "source": "dbwiki",
            "variant": "solo",
            "ip": "pokemon",
        }

        battle_id = database.log_battle(scope, winner, loser)
        assert battle_id is not None
        assert len(battle_id) > 0

    def test_log_battle_creates_two_records(self, test_db):
        """log_battle should create one win and one loss record."""
        from games.arena import database

        scope = {
            "scope_level": "ip",
            "scope_ip": "pokemon",
            "scope_group": None,
            "scope_character": None,
            "scope_source": None,
            "scope_variant": None,
            "match_source": False,
            "match_variant": False,
        }

        winner = {
            "path": "/test/winner.jpg",
            "name": "Winner",
            "group_name": "1",
            "source": "dbwiki",
            "variant": "solo",
            "ip": "pokemon",
        }

        loser = {
            "path": "/test/loser.jpg",
            "name": "Loser",
            "group_name": "1",
            "source": "dbwiki",
            "variant": "solo",
            "ip": "pokemon",
        }

        battle_id = database.log_battle(scope, winner, loser)

        conn = database.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT result FROM battles WHERE battle_id = ?", (battle_id,))
        results = [row['result'] for row in cursor.fetchall()]
        conn.close()

        assert len(results) == 2
        assert 'win' in results
        assert 'loss' in results

    def test_undo_battle_removes_records(self, test_db):
        """undo_battle should remove both battle records."""
        from games.arena import database

        scope = {
            "scope_level": "ip",
            "scope_ip": "pokemon",
            "scope_group": None,
            "scope_character": None,
            "scope_source": None,
            "scope_variant": None,
            "match_source": False,
            "match_variant": False,
        }

        winner = {"path": "/test/winner.jpg", "name": "Winner", "group_name": "1", "source": "dbwiki", "variant": "solo", "ip": "pokemon"}
        loser = {"path": "/test/loser.jpg", "name": "Loser", "group_name": "1", "source": "dbwiki", "variant": "solo", "ip": "pokemon"}

        battle_id = database.log_battle(scope, winner, loser)
        result = database.undo_battle(battle_id)

        assert result is not None
        assert "winner" in result
        assert "loser" in result

        # Verify records are deleted
        conn = database.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM battles WHERE battle_id = ?", (battle_id,))
        count = cursor.fetchone()[0]
        conn.close()

        assert count == 0

    def test_undo_battle_nonexistent_returns_none(self, test_db):
        """undo_battle with invalid battle_id should return None."""
        from games.arena import database

        result = database.undo_battle("nonexistent-battle-id")
        assert result is None

    def test_get_recent_battles(self, test_db):
        """get_recent_battles should return recent battle records."""
        from games.arena import database

        scope = {"scope_level": "ip", "scope_ip": "pokemon", "scope_group": None, "scope_character": None, "scope_source": None, "scope_variant": None, "match_source": False, "match_variant": False}
        winner = {"path": "/test/winner.jpg", "name": "Winner", "group_name": "1", "source": "dbwiki", "variant": "solo", "ip": "pokemon"}
        loser = {"path": "/test/loser.jpg", "name": "Loser", "group_name": "1", "source": "dbwiki", "variant": "solo", "ip": "pokemon"}

        # Log a battle
        database.log_battle(scope, winner, loser)

        recent = database.get_recent_battles(limit=10)
        assert len(recent) > 0
        # get_recent_battles returns {'battle_id', 'timestamp', 'scope_level', 'winner', 'loser'}
        assert 'winner' in recent[0]
        assert 'loser' in recent[0]
        assert recent[0]['winner']['path'] == winner['path']


class TestDatabaseStats:
    """Tests for image stats functions."""

    def test_get_image_stats_after_battles(self, test_db):
        """get_image_stats returns correct win/loss counts."""
        from games.arena import database

        scope = {"scope_level": "ip", "scope_ip": "pokemon", "scope_group": None, "scope_character": None, "scope_source": None, "scope_variant": None, "match_source": False, "match_variant": False}
        winner = {"path": "/test/winner.jpg", "name": "Winner", "group_name": "1", "source": "dbwiki", "variant": "solo", "ip": "pokemon"}
        loser = {"path": "/test/loser.jpg", "name": "Loser", "group_name": "1", "source": "dbwiki", "variant": "solo", "ip": "pokemon"}

        # Log 3 battles
        for _ in range(3):
            database.log_battle(scope, winner, loser)

        winner_stats = database.get_image_stats(winner["path"])
        assert winner_stats['wins'] == 3
        assert winner_stats['losses'] == 0
        assert winner_stats['total_battles'] == 3

        loser_stats = database.get_image_stats(loser["path"])
        assert loser_stats['wins'] == 0
        assert loser_stats['losses'] == 3
        assert loser_stats['total_battles'] == 3

    def test_get_all_image_stats(self, test_db):
        """get_all_image_stats returns stats for multiple images."""
        from games.arena import database

        scope = {"scope_level": "ip", "scope_ip": "pokemon", "scope_group": None, "scope_character": None, "scope_source": None, "scope_variant": None, "match_source": False, "match_variant": False}
        img1 = {"path": "/test/img1.jpg", "name": "Img1", "group_name": "1", "source": "dbwiki", "variant": "solo", "ip": "pokemon"}
        img2 = {"path": "/test/img2.jpg", "name": "Img2", "group_name": "1", "source": "dbwiki", "variant": "solo", "ip": "pokemon"}

        database.log_battle(scope, img1, img2)

        stats = database.get_all_image_stats([img1["path"], img2["path"]])

        assert img1["path"] in stats
        assert img2["path"] in stats
        assert stats[img1["path"]]['wins'] == 1
        assert stats[img2["path"]]['losses'] == 1

    def test_get_all_image_battle_counts(self, test_db):
        """get_all_image_battle_counts returns total battle counts."""
        from games.arena import database

        scope = {"scope_level": "ip", "scope_ip": "pokemon", "scope_group": None, "scope_character": None, "scope_source": None, "scope_variant": None, "match_source": False, "match_variant": False}
        img1 = {"path": "/test/img1.jpg", "name": "Img1", "group_name": "1", "source": "dbwiki", "variant": "solo", "ip": "pokemon"}
        img2 = {"path": "/test/img2.jpg", "name": "Img2", "group_name": "1", "source": "dbwiki", "variant": "solo", "ip": "pokemon"}

        # Log 2 battles
        database.log_battle(scope, img1, img2)
        database.log_battle(scope, img2, img1)

        counts = database.get_all_image_battle_counts([img1["path"], img2["path"]])

        assert counts[img1["path"]] == 2
        assert counts[img2["path"]] == 2

    def test_get_leaderboard(self, test_db):
        """get_leaderboard returns images sorted by win rate."""
        from games.arena import database

        scope = {"scope_level": "ip", "scope_ip": "pokemon", "scope_group": None, "scope_character": None, "scope_source": None, "scope_variant": None, "match_source": False, "match_variant": False}
        winner = {"path": "/test/winner.jpg", "name": "Winner", "group_name": "1", "source": "dbwiki", "variant": "solo", "ip": "pokemon"}
        loser = {"path": "/test/loser.jpg", "name": "Loser", "group_name": "1", "source": "dbwiki", "variant": "solo", "ip": "pokemon"}

        # Log 5 battles (winner wins all) - need at least 3 for leaderboard
        for _ in range(5):
            database.log_battle(scope, winner, loser)

        # get_leaderboard requires at least 3 battles (hardcoded)
        leaderboard = database.get_leaderboard(limit=10)

        assert len(leaderboard) >= 1
        # Winner should be first with 100% win rate
        top = leaderboard[0]
        assert top['path'] == winner["path"]
        assert top['win_rate'] == 1.0  # Stored as decimal 0-1, not percentage


class TestDatabaseDeletions:
    """Tests for deletion tracking functions."""

    def test_get_deletion_stats(self, test_db):
        """get_deletion_stats should return grouped deletion counts."""
        from games.arena import database

        # Log some deletions
        for i in range(3):
            image = {
                "path": f"/test/deleted{i}.jpg",
                "name": f"Deleted{i}",
                "group_name": "1",
                "source": "dbwiki",
                "variant": "solo",
                "ip": "pokemon",
                "universe": "nintendo",
            }
            database.log_deletion(image)

        stats = database.get_deletion_stats(group_by='variant')
        assert len(stats) > 0

    def test_get_deletion_details(self, test_db):
        """get_deletion_details should return recent deletion records."""
        from games.arena import database

        image = {
            "path": "/test/deleted.jpg",
            "name": "Deleted",
            "group_name": "1",
            "source": "dbwiki",
            "variant": "solo",
            "ip": "pokemon",
            "universe": "nintendo",
        }

        database.log_deletion(image)

        details = database.get_deletion_details(limit=10)
        assert len(details) == 1
        assert details[0]['path'] == image['path']


class TestDatabaseMerge:
    """Tests for merge and backfill functions."""

    def test_merge_images_consolidates_stats(self, test_db):
        """merge_images should consolidate battle records to surviving path."""
        from games.arena import database

        scope = {"scope_level": "ip", "scope_ip": "pokemon", "scope_group": None, "scope_character": None, "scope_source": None, "scope_variant": None, "match_source": False, "match_variant": False}

        # Create images with different paths
        img1 = {"path": "/test/original.jpg", "name": "Image", "group_name": "1", "source": "dbwiki", "variant": "solo", "ip": "pokemon"}
        img2 = {"path": "/test/duplicate.jpg", "name": "Image", "group_name": "1", "source": "dbwiki", "variant": "solo", "ip": "pokemon"}
        opponent = {"path": "/test/opponent.jpg", "name": "Opponent", "group_name": "1", "source": "dbwiki", "variant": "solo", "ip": "pokemon"}

        # Log battles for both images
        database.log_battle(scope, img1, opponent)  # img1 wins
        database.log_battle(scope, img2, opponent)  # img2 wins

        # Merge img2 into img1
        result = database.merge_images(img1["path"], [img2["path"]])

        assert result['battles_merged'] > 0
        assert result['surviving_path'] == img1["path"]

        # Verify all battles now point to surviving path
        conn = database.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM battles WHERE path = ?", (img2["path"],))
        duplicate_count = cursor.fetchone()[0]
        conn.close()

        assert duplicate_count == 0  # All records should be migrated

    def test_backfill_image_stats(self, test_db):
        """backfill_image_stats should rebuild stats from battles table."""
        from games.arena import database

        scope = {"scope_level": "ip", "scope_ip": "pokemon", "scope_group": None, "scope_character": None, "scope_source": None, "scope_variant": None, "match_source": False, "match_variant": False}
        winner = {"path": "/test/winner.jpg", "name": "Winner", "group_name": "1", "source": "dbwiki", "variant": "solo", "ip": "pokemon"}
        loser = {"path": "/test/loser.jpg", "name": "Loser", "group_name": "1", "source": "dbwiki", "variant": "solo", "ip": "pokemon"}

        # Log a battle
        database.log_battle(scope, winner, loser)

        # Clear image_stats
        conn = database.get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM image_stats")
        conn.commit()
        conn.close()

        # Backfill
        count = database.backfill_image_stats()
        assert count > 0

        # Verify stats are restored
        stats = database.get_image_stats(winner["path"])
        assert stats['wins'] > 0
