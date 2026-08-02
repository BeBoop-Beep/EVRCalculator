"""Reviewed image-source mappings for historical TCGplayer-only Pokemon catalogs.

These catalogs have an authoritative TCGplayer identity and no Pokemon API set of
their own. A mapping here says only "these API sets are where card images may be
read from" - it never claims the API id is the catalog's identity.
"""

import pytest

from backend.constants.tcg.pokemon import historical_catalog_image_sources as sources


def test_the_three_outcomes_are_named_exactly_as_specified():
    assert sources.ONE_TO_ONE == "one_to_one_api_match"
    assert sources.PARENT_OR_MULTI == "multi_or_parent_api_mapping_required"
    assert sources.NO_EQUIVALENT == "no_api_equivalent"


@pytest.mark.parametrize(
    "canonical_key,api_set_id",
    [
        ("expedition", "ecard1"),
        ("wotcPromo", "basep"),
        ("diamondAndPearlPromos", "dpp"),
        ("swshSwordAndShieldPromoCards", "swshp"),
    ],
)
def test_confirmed_one_to_one_catalogs_resolve_to_their_reviewed_api_set(canonical_key, api_set_id):
    mapping = sources.resolve(canonical_key=canonical_key)

    assert mapping is not None
    assert mapping.match_kind == sources.ONE_TO_ONE
    assert mapping.api_set_ids == (api_set_id,)


def test_a_mapping_can_be_looked_up_by_tcgplayer_source_set_id():
    by_key = sources.resolve(canonical_key="expedition")
    by_provider_id = sources.resolve(tcgplayer_set_id="1375")

    assert by_provider_id is by_key
    assert by_key.tcgplayer_set_id == "1375"


def test_subset_and_variant_catalogs_are_parent_mappings_not_one_to_one():
    # RC subsets live inside their parent set; Shadowless is a print variant of Base.
    for key, parent in (
        ("legendaryTreasuresRadiantCollection", "bw11"),
        ("generationsRadiantCollection", "g1"),
        ("baseSetShadowless", "base1"),
    ):
        mapping = sources.resolve(canonical_key=key)
        assert mapping.match_kind == sources.PARENT_OR_MULTI, key
        assert mapping.api_set_ids == (parent,), key


def test_api_set_ids_is_always_a_tuple_so_multi_set_sources_are_supported():
    for mapping in sources.REVIEWED_IMAGE_SOURCES.values():
        assert isinstance(mapping.api_set_ids, tuple), mapping.canonical_key
        assert mapping.api_set_ids, mapping.canonical_key
        assert all(isinstance(value, str) and value.strip() for value in mapping.api_set_ids)


@pytest.mark.parametrize(
    "canonical_key",
    [
        "battleAcademy",
        "battleAcademy2022",
        "battleAcademy2024",
        "worldChampionshipDecks",
        "deckExclusives",
        "blisterExclusives",
        "alternateArtPromos",
        "firstPartnerPack",
    ],
)
def test_mixed_catalogs_are_explicitly_refused_and_never_mapped(canonical_key):
    assert sources.resolve(canonical_key=canonical_key) is None

    refusal = sources.refusal_reason(canonical_key)
    assert refusal, f"{canonical_key} must carry an explicit reason, not a silent miss"
    assert "mixed" in refusal.lower() or "multiple" in refusal.lower()


@pytest.mark.parametrize(
    "canonical_key",
    [
        "xyTrainerKitLatiasAndLatios",
        "bwTrainerKitExcadrillAndZoroark",
        "hgssTrainerKitGyaradosAndRaichu",
        "smTrainerKitLycanrocAndAlolanRaichu",
        "trickOrTradeBOOsterBundle2023",
        "mcdonaldSPromos2023",
    ],
)
def test_catalogs_with_no_api_set_at_all_stay_unmapped(canonical_key):
    assert sources.resolve(canonical_key=canonical_key) is None


def test_classification_reports_no_api_equivalent_for_unmapped_catalogs():
    assert sources.classify("battleAcademy") == sources.NO_EQUIVALENT
    assert sources.classify("xyTrainerKitLatiasAndLatios") == sources.NO_EQUIVALENT
    assert sources.classify("expedition") == sources.ONE_TO_ONE
    assert sources.classify("baseSetShadowless") == sources.PARENT_OR_MULTI


def test_every_reviewed_mapping_carries_strategy_and_count_evidence():
    for mapping in sources.REVIEWED_IMAGE_SOURCES.values():
        assert mapping.strategy, mapping.canonical_key
        assert mapping.evidence, mapping.canonical_key
        # Reviewed counts are recorded so a later drift is visible in the report.
        assert mapping.reviewed_internal_card_count >= 0
        assert mapping.reviewed_api_card_count >= 0


def test_a_mapping_never_exposes_itself_as_a_pokemon_api_set_identity():
    # The registry must not offer anything that could be written into SET_ID /
    # sets.pokemon_api_set_id: image sources are not identities.
    for mapping in sources.REVIEWED_IMAGE_SOURCES.values():
        assert not hasattr(mapping, "set_id")
        assert not hasattr(mapping, "pokemon_api_set_id")
    assert not hasattr(sources, "SET_ID_OVERRIDES")


@pytest.mark.parametrize(
    "canonical_key,internal_count,api_count",
    [
        # Pinned from the live Pokemon API catalog + live internal card counts at
        # review time. A mismatch here means the mapping needs re-verification.
        ("expedition", 165, 165),
        ("wotcPromo", 69, 53),
        ("diamondAndPearlPromos", 60, 56),
        ("swshSwordAndShieldPromoCards", 341, 304),
        ("svScarletAndVioletPromoCards", 280, 196),
        ("sveScarletAndVioletEnergies", 40, 8),
        ("baseSetShadowless", 102, 102),
        ("generationsRadiantCollection", 32, 117),
        ("legendaryTreasuresRadiantCollection", 25, 140),
    ],
)
def test_reviewed_counts_are_pinned_to_the_verified_live_values(
    canonical_key, internal_count, api_count
):
    mapping = sources.resolve(canonical_key=canonical_key)

    assert mapping.reviewed_internal_card_count == internal_count
    assert mapping.reviewed_api_card_count == api_count


def test_registry_keys_and_provider_ids_are_internally_consistent():
    seen_provider_ids = set()
    for key, mapping in sources.REVIEWED_IMAGE_SOURCES.items():
        assert key == mapping.canonical_key
        assert mapping.tcgplayer_set_id.isdigit()
        assert mapping.tcgplayer_set_id not in seen_provider_ids
        seen_provider_ids.add(mapping.tcgplayer_set_id)
        assert mapping.match_kind in {sources.ONE_TO_ONE, sources.PARENT_OR_MULTI}
