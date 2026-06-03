import pytest

from backend.constants.tcg.pokemon.swordAndShieldEra.fusionStrike import SetFusionStrikeConfig
from backend.simulations.slotSchemaOutcomeResolver import apply_slot_schema_outcome_pool_mapping


def test_fusion_strike_runtime_fields_exist():
    assert hasattr(SetFusionStrikeConfig, "SIMULATION_ENGINE")
    assert hasattr(SetFusionStrikeConfig, "SLOT_SCHEMA_RUNTIME_ENABLED")
    assert hasattr(SetFusionStrikeConfig, "REVERSE_SLOT_PROBABILITIES")
    assert hasattr(SetFusionStrikeConfig, "RARE_SLOT_PROBABILITY")
    assert hasattr(SetFusionStrikeConfig, "SLOT_SCHEMA_OUTCOME_POOL_MAPPING")
    assert hasattr(SetFusionStrikeConfig, "SLOT_SCHEMA_SOURCE_CONFIDENCE")


def test_fusion_strike_runtime_is_enabled_for_slot_schema_engine():
    assert SetFusionStrikeConfig.SIMULATION_ENGINE == "slot_schema"
    assert SetFusionStrikeConfig.SLOT_SCHEMA_RUNTIME_ENABLED is True


def test_fusion_strike_reverse_slot_scaffold_matches_standard_swsh_shape():
    reverse_table = SetFusionStrikeConfig.REVERSE_SLOT_PROBABILITIES
    assert set(reverse_table.keys()) == {"slot_1"}
    assert reverse_table["slot_1"] == {"regular reverse": 1.0}


def test_fusion_strike_rare_slot_probability_keys_are_locked_and_exclude_composite_rows():
    table = SetFusionStrikeConfig.RARE_SLOT_PROBABILITY
    expected_keys = {
        "rare",
        "holo rare",
        "regular v",
        "regular vmax",
        "full art pokemon",
        "full art supporter",
        "rainbow rare",
        "gold rare",
        "alternate art v",
        "alternate art vmax",
    }
    forbidden_keys = {
        "alt v or vmax combined",
        "hits per 36 packs",
        "hit rate ultra rare or better",
        "ultra rare",
        "secret rare",
        "rare holo vmax",
        "rare holo v",
    }

    assert set(table.keys()) == expected_keys
    assert forbidden_keys.isdisjoint(set(table.keys()))


def test_fusion_strike_locked_source_backed_probabilities_match_runtime_table():
    table = SetFusionStrikeConfig.RARE_SLOT_PROBABILITY

    assert table["regular v"] == pytest.approx(1 / 7.8, abs=1e-12)
    assert table["regular vmax"] == pytest.approx(1 / 28, abs=1e-12)
    assert table["full art pokemon"] == pytest.approx(1 / 66, abs=1e-12)
    assert table["full art supporter"] == pytest.approx(1 / 72, abs=1e-12)
    assert table["rainbow rare"] == pytest.approx(1 / 126, abs=1e-12)
    assert table["gold rare"] == pytest.approx(1 / 116, abs=1e-12)
    assert table["alternate art v"] == pytest.approx(1 / 137, abs=1e-12)
    assert table["alternate art vmax"] == pytest.approx(1 / 275, abs=1e-12)


def test_fusion_strike_rare_bucket_is_residual_after_non_rare_mass_with_holo_cross_reference():
    table = SetFusionStrikeConfig.RARE_SLOT_PROBABILITY

    assert table["holo rare"] == pytest.approx(1 / 5.6, abs=1e-12)
    non_rare_mass = sum(probability for bucket, probability in table.items() if bucket != "rare")
    assert table["rare"] == pytest.approx(1.0 - non_rare_mass, abs=1e-12)
    assert sum(table.values()) == pytest.approx(1.0, abs=1e-12)
    assert table["rare"] >= 0.0


def test_fusion_strike_outcome_mapping_covers_runtime_buckets_and_excludes_composite_rows():
    mapping = SetFusionStrikeConfig.SLOT_SCHEMA_OUTCOME_POOL_MAPPING
    runtime_keys = set(SetFusionStrikeConfig.RARE_SLOT_PROBABILITY.keys())
    mapping_keys = set(mapping.keys())

    forbidden_mapping_keys = {
        "alt v or vmax combined",
        "hits per 36 packs",
        "hit rate ultra rare or better",
        "ultra rare",
        "secret rare",
    }

    assert runtime_keys == mapping_keys
    assert forbidden_mapping_keys.isdisjoint(mapping_keys)


def test_fusion_strike_mapping_excludes_reverse_variants_for_rare_slot_outcomes():
    mapping = SetFusionStrikeConfig.SLOT_SCHEMA_OUTCOME_POOL_MAPPING

    for outcome_name, details in mapping.items():
        assert details["include_reverse_variants"] is False, outcome_name


def test_fusion_strike_full_art_supporter_mapping_uses_disjoint_number_block_not_name_guess():
    mapping = SetFusionStrikeConfig.SLOT_SCHEMA_OUTCOME_POOL_MAPPING
    supporter_filter = mapping["full art supporter"]["card_filter"]

    assert supporter_filter["card_number_range"] == "258-264"
    assert "name_contains" not in supporter_filter


def test_fusion_strike_full_art_pools_are_disjoint_for_inspected_245_264_rows():
    inspected_rows = [
        {"card_number": "245/264", "name": "Celebi V (Alternate Full Art)", "rarity": "Ultra Rare", "printing_type": "holo"},
        {"card_number": "246/264", "name": "Tsareena V (Full Art)", "rarity": "Ultra Rare", "printing_type": "holo"},
        {"card_number": "247/264", "name": "Chandelure V (Full Art)", "rarity": "Ultra Rare", "printing_type": "holo"},
        {"card_number": "248/264", "name": "Crabominable V (Full Art)", "rarity": "Ultra Rare", "printing_type": "holo"},
        {"card_number": "249/264", "name": "Boltund V (Full Art)", "rarity": "Ultra Rare", "printing_type": "holo"},
        {"card_number": "250/264", "name": "Mew V (Full Art)", "rarity": "Ultra Rare", "printing_type": "holo"},
        {"card_number": "251/264", "name": "Mew V (Alternate Full Art)", "rarity": "Ultra Rare", "printing_type": "holo"},
        {"card_number": "252/264", "name": "Sandaconda V (Alternate Full Art)", "rarity": "Ultra Rare", "printing_type": "holo"},
        {"card_number": "253/264", "name": "Hoopa V (Full Art)", "rarity": "Ultra Rare", "printing_type": "holo"},
        {"card_number": "254/264", "name": "Genesect V (Full Art)", "rarity": "Ultra Rare", "printing_type": "holo"},
        {"card_number": "255/264", "name": "Genesect V (Alternate Full Art)", "rarity": "Ultra Rare", "printing_type": "holo"},
        {"card_number": "256/264", "name": "Greedent V (Full Art)", "rarity": "Ultra Rare", "printing_type": "holo"},
        {"card_number": "257/264", "name": "Greedent V (Alternate Full Art)", "rarity": "Ultra Rare", "printing_type": "holo"},
        {"card_number": "258/264", "name": "Chili & Cilan & Cress (Full Art)", "rarity": "Ultra Rare", "printing_type": "holo"},
        {"card_number": "259/264", "name": "Dancer (Full Art)", "rarity": "Ultra Rare", "printing_type": "holo"},
        {"card_number": "260/264", "name": "Elesa's Sparkle (Full Art)", "rarity": "Ultra Rare", "printing_type": "holo"},
        {"card_number": "261/264", "name": "Schoolboy (Full Art)", "rarity": "Ultra Rare", "printing_type": "holo"},
        {"card_number": "262/264", "name": "Schoolgirl (Full Art)", "rarity": "Ultra Rare", "printing_type": "holo"},
        {"card_number": "263/264", "name": "Shauna (Full Art)", "rarity": "Ultra Rare", "printing_type": "holo"},
        {"card_number": "264/264", "name": "Sidney (Full Art)", "rarity": "Ultra Rare", "printing_type": "holo"},
    ]

    dataframe = __import__("pandas").DataFrame(inspected_rows)
    pools = apply_slot_schema_outcome_pool_mapping(SetFusionStrikeConfig, dataframe, allow_empty_pools=True)

    full_art_pokemon = set(pools["full art pokemon"]["name"].tolist())
    full_art_supporters = set(pools["full art supporter"]["name"].tolist())
    alternate_art_v = set(pools["alternate art v"]["name"].tolist())

    assert full_art_pokemon == {
        "Tsareena V (Full Art)",
        "Chandelure V (Full Art)",
        "Crabominable V (Full Art)",
        "Boltund V (Full Art)",
        "Mew V (Full Art)",
        "Hoopa V (Full Art)",
        "Genesect V (Full Art)",
        "Greedent V (Full Art)",
    }
    assert full_art_supporters == {
        "Chili & Cilan & Cress (Full Art)",
        "Dancer (Full Art)",
        "Elesa's Sparkle (Full Art)",
        "Schoolboy (Full Art)",
        "Schoolgirl (Full Art)",
        "Shauna (Full Art)",
        "Sidney (Full Art)",
    }
    assert alternate_art_v == {
        "Celebi V (Alternate Full Art)",
        "Mew V (Alternate Full Art)",
        "Sandaconda V (Alternate Full Art)",
        "Genesect V (Alternate Full Art)",
        "Greedent V (Alternate Full Art)",
    }
    assert full_art_pokemon.isdisjoint(full_art_supporters)
    assert full_art_pokemon.isdisjoint(alternate_art_v)
    assert full_art_supporters.isdisjoint(alternate_art_v)


def test_fusion_strike_source_confidence_contains_required_caveats():
    confidence = SetFusionStrikeConfig.SLOT_SCHEMA_SOURCE_CONFIDENCE

    assert confidence["runtime_ready"] is True
    assert confidence["pool_mapping_ready"] is True
    assert confidence["source_model"] == "best_available_empirical"

    caveat = confidence.get("source_caveat", "").lower()
    assert "not official pokemon" in caveat
    assert "public empirical samples" in caveat
    assert "thepricedex" in caveat
    assert "cross-reference/index-only" in caveat
    assert "alt-art" in caveat
