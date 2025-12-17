"""
Tests for the restructured arena config.
Validates that IP_SOURCES contains gen_aliases and sources.
Variant groups are now calculated dynamically from tag_variants.
"""

import sys
from pathlib import Path

import pytest

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


class TestIPSourcesStructure:
    """Test the IP_SOURCES JSON structure (with universe hierarchy)."""

    def test_ip_sources_has_nintendo_universe(self):
        """IP_SOURCES should contain 'nintendo' universe with 'pokemon' IP."""
        from core.utils import IP_SOURCES

        assert "nintendo" in IP_SOURCES
        assert isinstance(IP_SOURCES["nintendo"], dict)
        assert "pokemon" in IP_SOURCES["nintendo"]
        assert isinstance(IP_SOURCES["nintendo"]["pokemon"], dict)

    def test_pokemon_has_gen_aliases(self):
        """Pokemon config should have gen_aliases."""
        from core.utils import IP_SOURCES

        pokemon = IP_SOURCES["nintendo"]["pokemon"]
        assert "gen_aliases" in pokemon
        assert isinstance(pokemon["gen_aliases"], dict)

    def test_pokemon_has_sources(self):
        """Pokemon config should have sources list."""
        from core.utils import IP_SOURCES

        pokemon = IP_SOURCES["nintendo"]["pokemon"]
        assert "sources" in pokemon
        assert isinstance(pokemon["sources"], list)
        assert len(pokemon["sources"]) > 0


class TestGenAliases:
    """Test generation alias functionality."""

    def test_get_gen_aliases_pokemon(self):
        """get_gen_aliases should return pokemon gen aliases."""
        from core.utils import get_gen_aliases

        aliases = get_gen_aliases("pokemon")
        assert isinstance(aliases, dict)
        assert "archeus" in aliases
        assert aliases["archeus"] == "8A"

    def test_get_gen_aliases_unknown_ip(self):
        """get_gen_aliases should return empty dict for unknown IP."""
        from core.utils import get_gen_aliases

        aliases = get_gen_aliases("unknown_ip")
        assert aliases == {}

    def test_gen_aliases_backwards_compat(self):
        """GEN_ALIASES module-level variable should work."""
        from core.utils import GEN_ALIASES

        assert isinstance(GEN_ALIASES, dict)
        assert "archeus" in GEN_ALIASES
        assert GEN_ALIASES["archeus"] == "8A"


class TestVariantGroups:
    """Test variant group functionality (calculated from tag_variants)."""

    def test_get_variant_groups_pokemon(self):
        """get_variant_groups should return pokemon variant groups."""
        from core.utils import get_variant_groups

        groups = get_variant_groups("pokemon")
        assert isinstance(groups, dict)
        assert "AI" in groups
        assert "artist" in groups
        assert "niche" in groups

    def test_variant_groups_contain_variants(self):
        """Each variant group should contain variant names."""
        from core.utils import get_variant_groups

        groups = get_variant_groups("pokemon")

        assert "AIBest" in groups["AI"]
        assert "AIRecent" in groups["AI"]
        assert "artistTop" in groups["artist"]
        assert "solo" in groups["niche"]

    def test_get_variant_groups_unknown_ip(self):
        """get_variant_groups should return empty dict for unknown IP."""
        from core.utils import get_variant_groups

        groups = get_variant_groups("unknown_ip")
        assert groups == {}

    def test_variant_groups_backwards_compat(self):
        """VARIANT_GROUPS module-level variable should work."""
        from core.utils import VARIANT_GROUPS

        assert isinstance(VARIANT_GROUPS, dict)
        assert "AI" in VARIANT_GROUPS


class TestVariantToGroup:
    """Test variant-to-group reverse lookup."""

    def test_get_variant_to_group_pokemon(self):
        """get_variant_to_group should map variants to group names."""
        from core.utils import get_variant_to_group

        v2g = get_variant_to_group("pokemon")
        assert isinstance(v2g, dict)

        # AI variants
        assert v2g["AIBest"] == "AI"
        assert v2g["AIRecent"] == "AI"

        # Artist variants
        assert v2g["artistTop"] == "artist"
        assert v2g["artistA"] == "artist"
        assert v2g["artistB"] == "artist"

        # Niche variants
        assert v2g["solo"] == "niche"
        assert v2g["action"] == "niche"
        assert v2g["costume"] == "niche"

    def test_get_variant_to_group_unknown_ip(self):
        """get_variant_to_group should return empty dict for unknown IP."""
        from core.utils import get_variant_to_group

        v2g = get_variant_to_group("unknown_ip")
        assert v2g == {}

    def test_variant_to_group_via_utils(self):
        """get_variant_to_group should be accessible via core.utils."""
        from core.utils import get_variant_to_group

        v2g = get_variant_to_group("pokemon")
        assert v2g["AIBest"] == "AI"


class TestSources:
    """Test source configuration."""

    def test_get_sources_pokemon(self):
        """get_sources should return sorted list of sources."""
        from core.utils import get_sources

        sources = get_sources("pokemon")
        assert isinstance(sources, list)
        assert len(sources) >= 1  # At least one source configured

    def test_sources_sorted_by_priority(self):
        """Sources should be sorted by priority (ascending)."""
        from core.utils import get_sources

        sources = get_sources("pokemon")
        priorities = [s["priority"] for s in sources]
        assert priorities == sorted(priorities)

    def test_sources_have_required_fields(self):
        """Each source should have name, short_name, priority."""
        from core.utils import get_sources

        sources = get_sources("pokemon")
        for source in sources:
            assert "name" in source
            assert "short_name" in source
            assert "priority" in source

    def test_get_sources_unknown_ip_raises(self):
        """get_sources should raise ValueError for unknown IP."""
        from core.utils import get_sources

        with pytest.raises(ValueError) as exc_info:
            get_sources("unknown_ip")
        assert "unknown_ip" in str(exc_info.value)

    def test_booru_source_has_tag_variants(self):
        """Booru-type sources should have tag_variants if configured."""
        from core.utils import get_sources, has_tag_variants

        sources = get_sources("pokemon")
        booru_sources = [s for s in sources if s.get("site_type") == "booru"]

        # Skip if no booru sources configured
        if not booru_sources:
            return

        booru = booru_sources[0]
        if has_tag_variants(booru):
            assert "tag_variants" in booru
            assert len(booru["tag_variants"]) > 0

    def test_tag_variants_have_required_fields(self):
        """Tag variants should have required fields."""
        from core.utils import get_sources, get_tag_variants, has_tag_variants

        sources = get_sources("pokemon")

        for source in sources:
            if has_tag_variants(source):
                tag_variants = get_tag_variants(source)
                for tv in tag_variants:
                    assert "variant_name" in tv
                    # variant_group is optional but recommended


class TestDeprecatedVariants:
    """Test deprecated variants handling."""

    def test_deprecated_tag_variants_structure(self):
        """Deprecated tag variants should have correct structure if present."""
        from core.utils import get_sources, has_tag_variants

        sources = get_sources("pokemon")

        for source in sources:
            if has_tag_variants(source) and "deprecated_tag_variants" in source:
                deprecated = source["deprecated_tag_variants"]
                assert isinstance(deprecated, list)
                for dep in deprecated:
                    assert "variant_name" in dep

    def test_deprecated_variants_are_separate(self):
        """Deprecated variants should not be in active tag_variants."""
        from core.utils import get_sources, get_tag_variants, has_tag_variants

        sources = get_sources("pokemon")

        for source in sources:
            if has_tag_variants(source) and "deprecated_tag_variants" in source:
                active_names = [tv["variant_name"] for tv in get_tag_variants(source)]
                deprecated_names = [d["variant_name"] for d in source["deprecated_tag_variants"]]

                # No overlap between active and deprecated
                overlap = set(active_names) & set(deprecated_names)
                assert len(overlap) == 0, f"Overlap found: {overlap}"
