"""
Tests for matcher logic.
Validates matchup selection with the new config structure,
especially variant_group matching.
"""

import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


class TestDeprecatedVariants:
    """Test deprecated variant detection from new config structure."""

    def test_get_deprecated_variants(self):
        """get_deprecated_variants should find deprecated from sources."""
        from games.arena.matcher import get_deprecated_variants

        deprecated = get_deprecated_variants()
        assert isinstance(deprecated, set)
        # Check for deprecated variants defined in config
        assert "outdated" in deprecated
        assert "legacy" in deprecated

    def test_normalize_variant_deprecated(self):
        """Deprecated variants should normalize to __base__."""
        from games.arena.matcher import get_deprecated_variants, normalize_variant

        deprecated = get_deprecated_variants()

        assert normalize_variant("outdated", deprecated) == "__base__"
        assert normalize_variant("legacy", deprecated) == "__base__"

    def test_normalize_variant_regular(self):
        """Regular variants should normalize to themselves."""
        from games.arena.matcher import get_deprecated_variants, normalize_variant

        deprecated = get_deprecated_variants()

        assert normalize_variant("artistA", deprecated) == "artistA"
        assert normalize_variant("AIBest", deprecated) == "AIBest"
        assert normalize_variant("solo", deprecated) == "solo"

    def test_normalize_variant_none(self):
        """None variant should normalize to __base__."""
        from games.arena.matcher import normalize_variant

        assert normalize_variant(None) == "__base__"


class TestVariantToGroupLookup:
    """Test that matcher uses variant_to_group correctly."""

    def test_get_variant_to_group_integration(self):
        """Matcher should use get_variant_to_group from utils."""
        from core.utils import get_variant_to_group

        v2g = get_variant_to_group("pokemon")

        # Verify the lookup works as expected
        assert v2g.get("artistA") == "artist"
        assert v2g.get("AIBest") == "AI"
        assert v2g.get("solo") == "niche"
        assert v2g.get("unknown") is None


class TestConstrainedMatchupGrouping:
    """Test that constrained matchups group by variant_group correctly."""

    def test_group_by_variant_group(self, sample_image_dicts, test_db):
        """When match_variant_group=True, images should be grouped by variant_group."""
        from games.arena.matcher import _get_constrained_matchup

        # Get a matchup with match_variant_group=True
        result = _get_constrained_matchup(
            sample_image_dicts,
            match_source=False,
            match_variant=False,
            match_variant_group=True
        )

        if result:
            img1, img2 = result
            # Both images should have the same variant_group
            assert img1["variant_group"] == img2["variant_group"]

    def test_group_by_source_and_variant_group(self, sample_image_dicts, test_db):
        """When match_source and match_variant_group, both should match."""
        from games.arena.matcher import _get_constrained_matchup

        # Filter to just dbwiki images
        dbwiki_images = [img for img in sample_image_dicts if img["source"] == "dbwiki"]

        result = _get_constrained_matchup(
            dbwiki_images,
            match_source=True,
            match_variant=False,
            match_variant_group=True
        )

        if result:
            img1, img2 = result
            assert img1["source"] == img2["source"]
            assert img1["variant_group"] == img2["variant_group"]

    def test_variant_takes_precedence_over_variant_group(self, sample_image_dicts, test_db):
        """When both match_variant and match_variant_group are True, match_variant wins."""
        from games.arena.matcher import _get_constrained_matchup

        # Create images with same variant_group but different variants
        images = [
            {**sample_image_dicts[0], "variant": "artistA", "variant_group": "artist"},
            {**sample_image_dicts[1], "variant": "artistB", "variant_group": "artist"},
        ]

        result = _get_constrained_matchup(
            images,
            match_source=False,
            match_variant=True,
            match_variant_group=True  # Should be ignored
        )

        # Should return None because no two images have same variant
        assert result is None


class TestMatchupWithDatabase:
    """Test matchup functions that interact with the database."""

    def test_get_matchup_basic(self, test_db, sample_image_dicts):
        """Basic matchup should work with test database."""
        from games.arena import matcher

        # Mock the image index to return our sample data
        class MockIndex:
            def get_images(self, **kwargs):
                return sample_image_dicts

        # Temporarily replace get_index
        original_get_index = matcher.get_index
        matcher.get_index = lambda: MockIndex()  # type: ignore[assignment,return-value]

        try:
            result = matcher.get_matchup(
                scope_level="ip",
                scope_ip="dragonball"
            )

            if result:
                img1, img2 = result
                assert img1["ip"] == "dragonball"
                assert img2["ip"] == "dragonball"
                # Different images
                assert img1["path"] != img2["path"]
        finally:
            matcher.get_index = original_get_index

    def test_get_matchup_with_variant_group(self, test_db, sample_image_dicts):
        """Matchup with match_variant_group should return same group."""
        from games.arena import matcher

        # Only include images with variant_group
        images_with_group = [
            img for img in sample_image_dicts
            if img["variant_group"] is not None
        ]

        class MockIndex:
            def get_images(self, **kwargs):
                return images_with_group

        original_get_index = matcher.get_index
        matcher.get_index = lambda: MockIndex()  # type: ignore[assignment,return-value]

        try:
            result = matcher.get_matchup(
                scope_level="ip",
                scope_ip="dragonball",
                match_variant_group=True
            )

            if result:
                img1, img2 = result
                assert img1["variant_group"] == img2["variant_group"]
        finally:
            matcher.get_index = original_get_index


