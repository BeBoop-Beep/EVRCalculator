import json

import pytest

from backend.constants.tcg.pokemon.megaEvolutionEra.megaEvolution import SetMegaEvolutionConfig
from backend.constants.tcg.pokemon.scarletAndVioletEra.paldeaEvolved import SetPaldeaEvolvedConfig
from backend.constants.tcg.pokemon.swordAndShieldEra.chillingReign import SetChillingReignConfig
from backend.constants.tcg.pokemon.swordAndShieldEra.evolvingSkies import SetEvolvingSkiesConfig
from backend.simulations.evrSimulator import _should_use_monte_carlo_v2, get_simulation_engine

SWSH7_SOURCE_PROBABILITY = {
    "regular v": 0.1056,
    "regular vmax": 0.0560,
    "full art": 0.0278,
    "alternate art v": 0.0110,
    "alternate art vmax": 0.0030,
    "rainbow rare": 0.0084,
    "gold rare": 0.0091,
}

SWSH7_REQUIRED_BUCKET_KEYS = {
    "rare",
    "holo rare",
    "regular v",
    "regular vmax",
    "full art",
    "alternate art v",
    "alternate art vmax",
    "rainbow rare",
    "gold rare",
}

SWSH7_UNSUPPORTED_SPLIT_BUCKETS = {
    "full art v",
    "full art trainer",
    "rainbow trainer",
    "rainbow vmax",
    "gold secret rare",
}

SWSH6_SOURCE_PROBABILITY = {
    "regular vmax": 1 / 22,
    "full art v": 1 / 47,
    "full art trainer": 1 / 74,
    "rainbow rare": 1 / 83,
    "gold rare": 1 / 96,
    "alternate art v": 1 / 109,
    "alternate art vmax": 1 / 396,
}

SWSH6_SOURCE_ODDS_BY_BUCKET = {
    "regular vmax": "1/22",
    "full art v": "1/47",
    "full art trainer": "1/74",
    "rainbow rare": "1/83",
    "gold rare": "1/96",
    "alternate art v": "1/109",
    "alternate art vmax": "1/396",
}

SWSH6_SOURCE_BUCKET_NAME_BY_BUCKET = {
    "regular vmax": "VMAX",
    "full art v": "Full Art V",
    "full art trainer": "Full Art Trainer",
    "rainbow rare": "Rainbow",
    "gold rare": "Gold",
    "alternate art v": "Full Art Alt",
    "alternate art vmax": "VMAX Alt",
    "holo rare": "dripshop_holo_directional",
    "regular v": "reddit_regular_v_directional",
    "rare": "residual_derived",
}

SWSH6_REQUIRED_BUCKET_KEYS = {
    "rare",
    "holo rare",
    "regular v",
    "regular vmax",
    "full art v",
    "full art trainer",
    "alternate art v",
    "alternate art vmax",
    "rainbow rare",
    "gold rare",
}

SWSH6_UNSUPPORTED_SPLIT_BUCKETS = {
    "rainbow trainer",
    "rainbow vmax",
    "gold secret rare",
}

SWSH6_SOURCE_DIRECT_BUCKETS = set(SWSH6_SOURCE_PROBABILITY.keys())


def _probability_from_source_odds_literal(source_odds):
    text = str(source_odds).strip()
    if text.startswith("1/"):
        denominator = float(text.split("/", 1)[1].replace(",", ""))
        return 1.0 / denominator
    if text.endswith("%"):
        return float(text[:-1]) / 100.0
    if "/" in text:
        numerator_text, denominator_text = text.split("/", 1)
        return float(numerator_text.replace(",", "")) / float(denominator_text.replace(",", ""))
    raise AssertionError(f"Unsupported source odds literal: {source_odds!r}")

SWSH6_SOURCE_FREQUENCY_STATUS_ENUM = {
    "closed_chilling_reign_source_frequency_locked_to_charizardx",
    "closed_chilling_reign_source_frequency_partially_locked_with_provisional_rows",
    "not_closed_chilling_reign_source_lock_failed_mismatch",
    "not_closed_chilling_reign_source_lock_blocked_unsupported_granularity",
}


@pytest.mark.parametrize("bucket,source_probability", list(SWSH7_SOURCE_PROBABILITY.items()))
def test_swsh7_source_frequency_lock_exact_match(bucket, source_probability):
    active_probability = SetEvolvingSkiesConfig.RARE_SLOT_PROBABILITY[bucket]
    absolute_delta = abs(active_probability - source_probability)

    assert active_probability == pytest.approx(source_probability, abs=1e-12)
    assert absolute_delta == pytest.approx(0.0, abs=1e-12)


def test_swsh7_source_level_bucket_contract_is_locked_and_unsupported_splits_are_absent():
    active_keys = set(SetEvolvingSkiesConfig.RARE_SLOT_PROBABILITY.keys())

    assert active_keys == SWSH7_REQUIRED_BUCKET_KEYS
    assert SWSH7_UNSUPPORTED_SPLIT_BUCKETS.isdisjoint(active_keys)


def test_swsh7_holo_and_rare_contracts_remain_explicitly_non_direct():
    rare_slot_table = SetEvolvingSkiesConfig.RARE_SLOT_PROBABILITY
    source_audit = SetEvolvingSkiesConfig.EVOLVING_SKIES_PULL_RATE_SOURCE_AUDIT
    draft_audit = SetEvolvingSkiesConfig.EVOLVING_SKIES_RARE_SLOT_PROBABILITY_DRAFT_AUDIT

    assert "holo_rare_secondary_directional" in draft_audit["source_rows_used_with_assumptions"]
    assert source_audit["rare_slot_probability_readiness"]["rare_is_residual_capable"] is True
    assert source_audit["rare_slot_probability_readiness"]["rare_requires_direct_source_row"] is False

    non_rare_mass = sum(value for key, value in rare_slot_table.items() if key != "rare")
    assert rare_slot_table["rare"] == pytest.approx(1.0 - non_rare_mass, abs=1e-12)


def _has_swsh6_charizardx_source_values() -> bool:
    source_fragments = {
        "source_notes": getattr(SetChillingReignConfig, "CHILLING_REIGN_PULL_RATE_SOURCE_NOTES", {}),
        "source_audit": getattr(SetChillingReignConfig, "CHILLING_REIGN_RARE_SLOT_COVERAGE_AUDIT", {}),
        "draft_audit": getattr(SetChillingReignConfig, "CHILLING_REIGN_RARE_SLOT_PROBABILITY_DRAFT_AUDIT", {}),
    }
    blob = json.dumps(source_fragments, sort_keys=True).lower()
    return "charizardx" in blob or "charizard x" in blob


def _resolve_swsh6_source_rows_for_charizardx():
    if not _has_swsh6_charizardx_source_values():
        return {}

    draft_audit = getattr(
        SetChillingReignConfig,
        "CHILLING_REIGN_RARE_SLOT_PROBABILITY_DRAFT_AUDIT",
        {},
    )

    resolved_rows = {}
    for row in draft_audit.get("source_rows_used", {}).values():
        normalized_bucket = row.get("normalized_bucket")
        probability = row.get("probability")
        if isinstance(normalized_bucket, str) and isinstance(probability, (int, float)):
            resolved_rows[normalized_bucket] = float(probability)

    for row in draft_audit.get("source_rows_used_with_assumptions", {}).values():
        normalized_bucket = row.get("normalized_bucket")
        probability = row.get("probability")
        if isinstance(normalized_bucket, str) and isinstance(probability, (int, float)):
            resolved_rows[normalized_bucket] = float(probability)

    return resolved_rows


def _build_swsh6_charizardx_comparison_table():
    source_rows = _resolve_swsh6_source_rows_for_charizardx()
    active_rows = SetChillingReignConfig.RARE_SLOT_PROBABILITY
    draft_audit = getattr(
        SetChillingReignConfig,
        "CHILLING_REIGN_RARE_SLOT_PROBABILITY_DRAFT_AUDIT",
        {},
    )
    unsupported_splits = set(draft_audit.get("unsupported_split_rows", {}).keys())
    provisional_buckets = {
        row.get("normalized_bucket")
        for row in draft_audit.get("source_rows_used_with_assumptions", {}).values()
        if isinstance(row, dict) and isinstance(row.get("normalized_bucket"), str)
    }

    comparison = []
    for bucket in sorted(active_rows.keys()):
        active_probability = float(active_rows[bucket])
        source_probability = source_rows.get(bucket)
        absolute_delta = None if source_probability is None else abs(active_probability - source_probability)

        if bucket in unsupported_splits:
            granularity_status = "UNSUPPORTED_SPLIT"
            notes = "Legacy split removed in favor of broader source bucket"
        elif bucket == "rare":
            granularity_status = "SOURCE_DERIVED_RESIDUAL"
            notes = "Residual bucket; no direct source row required"
        elif bucket in provisional_buckets:
            granularity_status = "PROVISIONAL_DIRECTIONAL"
            notes = "Directional provisional row; awaiting direct source row"
        elif source_probability is None:
            granularity_status = "MISSING_SOURCE"
            notes = "No direct/provisional source row available"
        else:
            granularity_status = "SOURCE_DIRECT"
            notes = "Directly source-locked from user-provided row"

        source_odds = SWSH6_SOURCE_ODDS_BY_BUCKET.get(bucket)
        source_bucket_name = SWSH6_SOURCE_BUCKET_NAME_BY_BUCKET.get(bucket)
        pass_fail = "PASS" if absolute_delta is None or absolute_delta <= 1e-12 else "FAIL"
        comparison.append(
            {
                "bucket": bucket,
                "source_bucket_name": source_bucket_name,
                "source_probability": source_probability,
                "source_odds": source_odds,
                "active_probability": active_probability,
                "absolute_delta": absolute_delta,
                "source_granularity_status": granularity_status,
                "notes": notes,
                "pass_fail": pass_fail,
            }
        )
    return comparison


def _resolve_swsh6_source_frequency_status() -> str:
    source_rows = _resolve_swsh6_source_rows_for_charizardx()
    active_rows = SetChillingReignConfig.RARE_SLOT_PROBABILITY
    active_keys = set(active_rows.keys())

    if not _has_swsh6_charizardx_source_values():
        return "not_closed_chilling_reign_source_lock_blocked_unsupported_granularity"

    if not SWSH6_UNSUPPORTED_SPLIT_BUCKETS.isdisjoint(active_keys):
        return "not_closed_chilling_reign_source_lock_blocked_unsupported_granularity"

    missing_rows = [bucket for bucket in SWSH6_SOURCE_DIRECT_BUCKETS if bucket not in source_rows]
    if missing_rows:
        return "not_closed_chilling_reign_source_lock_failed_mismatch"

    for bucket, source_probability in SWSH6_SOURCE_PROBABILITY.items():
        active_probability = active_rows[bucket]
        if abs(float(active_probability) - float(source_probability)) > 1e-12:
            return "not_closed_chilling_reign_source_lock_failed_mismatch"

    provisional_buckets = {"holo rare", "regular v"}
    if provisional_buckets.issubset(active_keys):
        return "closed_chilling_reign_source_frequency_partially_locked_with_provisional_rows"

    return "closed_chilling_reign_source_frequency_locked_to_charizardx"


def test_swsh6_source_frequency_lock_status_is_partially_locked_with_provisional_rows():
    status = _resolve_swsh6_source_frequency_status()

    assert status in SWSH6_SOURCE_FREQUENCY_STATUS_ENUM
    assert _has_swsh6_charizardx_source_values() is True
    assert status == "closed_chilling_reign_source_frequency_partially_locked_with_provisional_rows"


def test_swsh6_active_runtime_bucket_granularity_matches_charizardx_source_shape():
    active_keys = set(SetChillingReignConfig.RARE_SLOT_PROBABILITY.keys())

    assert active_keys == SWSH6_REQUIRED_BUCKET_KEYS
    assert SWSH6_UNSUPPORTED_SPLIT_BUCKETS.isdisjoint(active_keys)


@pytest.mark.parametrize("bucket,source_probability", list(SWSH6_SOURCE_PROBABILITY.items()))
def test_swsh6_source_locked_buckets_match_user_provided_charizardx_rows_exactly(bucket, source_probability):
    active_probability = SetChillingReignConfig.RARE_SLOT_PROBABILITY[bucket]
    absolute_delta = abs(active_probability - source_probability)

    assert active_probability == pytest.approx(source_probability, abs=1e-12)
    assert absolute_delta == pytest.approx(0.0, abs=1e-12)


def test_swsh6_direct_source_rows_are_literal_source_locked_and_match_runtime_probabilities():
    draft_audit = SetChillingReignConfig.CHILLING_REIGN_RARE_SLOT_PROBABILITY_DRAFT_AUDIT
    source_rows = draft_audit["source_rows_used"]
    runtime_table = SetChillingReignConfig.RARE_SLOT_PROBABILITY

    expected_labels = {
        "regular vmax": "VMAX",
        "full art v": "Full Art V",
        "full art trainer": "Full Art Trainer",
        "alternate art v": "Full Art Alt",
        "alternate art vmax": "VMAX Alt",
        "rainbow rare": "Rainbow",
        "gold rare": "Gold",
    }

    seen_buckets = set()
    for source_label, row in source_rows.items():
        bucket = row["normalized_bucket"]
        if bucket not in expected_labels:
            continue
        seen_buckets.add(bucket)
        assert source_label == expected_labels[bucket]

        source_odds = row["source_odds"]
        expected_probability = _probability_from_source_odds_literal(source_odds)
        assert row["probability"] == pytest.approx(expected_probability)
        assert runtime_table[bucket] == pytest.approx(expected_probability)

    assert seen_buckets == set(expected_labels.keys())
    assert source_rows["VMAX Alt"]["source_odds"] == "1/396"
    assert runtime_table["alternate art vmax"] == pytest.approx(1 / 396)
    assert source_rows["VMAX Alt"]["source_odds"] != "1/454"
    assert runtime_table["alternate art vmax"] != pytest.approx(1 / 454)


def test_swsh7_direct_source_rows_are_literal_source_locked_and_match_runtime_probabilities():
    draft_audit = SetEvolvingSkiesConfig.EVOLVING_SKIES_RARE_SLOT_PROBABILITY_DRAFT_AUDIT
    runtime_table = SetEvolvingSkiesConfig.RARE_SLOT_PROBABILITY

    expected_rows = {
        "Normal Pokemon V": ("regular v", "10.56%"),
        "Normal Pokemon VMAX": ("regular vmax", "5.60%"),
        "Full-Art": ("full art", "2.78%"),
        "Alt-Art Pokemon V": ("alternate art v", "1.10%"),
        "Alt-Art Pokemon VMAX": ("alternate art vmax", "0.30%"),
        "Rainbow Rare": ("rainbow rare", "0.84%"),
        "Gold Rare": ("gold rare", "0.91%"),
    }

    source_rows = draft_audit["source_rows_used"]
    for source_label, (bucket, literal_odds) in expected_rows.items():
        row = source_rows[source_label]
        assert row["normalized_bucket"] == bucket
        assert row["source_odds"] == literal_odds
        expected_probability = _probability_from_source_odds_literal(literal_odds)
        assert row["probability"] == pytest.approx(expected_probability)
        assert runtime_table[bucket] == pytest.approx(expected_probability)


def test_swsh5_direct_reference_rows_are_source_locked_to_reddit_and_pricedex_is_secondary_only():
    from backend.constants.tcg.pokemon.swordAndShieldEra.battleStyles import SetBattleStylesConfig

    sources = {
        row["source_id"]: row
        for row in SetBattleStylesConfig.BATTLE_STYLES_PULL_RATE_REFERENCE_SOURCES
    }
    evidence_rows = SetBattleStylesConfig.BATTLE_STYLES_PULL_RATE_REFERENCE_BUCKET_EVIDENCE
    runtime_table = SetBattleStylesConfig.RARE_SLOT_PROBABILITY

    reddit_source = sources["battle_styles_community_pack_study"]
    assert reddit_source["source_url"] == "https://www.reddit.com/r/PokemonTCG/comments/mx0gvz/battle_styles_pull_data_after_almost_20000_packs/"
    assert reddit_source["source_type"] == "community_aggregation"

    for row in evidence_rows:
        if row["source_status"] != "SOURCE_DIRECT" or not row.get("used_in_runtime"):
            continue
        bucket = row["normalized_bucket"]
        expected_probability = _probability_from_source_odds_literal(row["odds_display"])
        assert row["source_ids"] == ["battle_styles_community_pack_study"]
        assert runtime_table[bucket] == pytest.approx(expected_probability)

    pricedex_rows = [
        row
        for row in evidence_rows
        if "battle_styles_thepricedex_cross_reference_2026_05" in (row.get("source_ids") or [])
    ]
    assert pricedex_rows
    assert all(row["source_status"] == "SECONDARY_INDEX_ONLY" for row in pricedex_rows)
    assert all(row["source_status"] != "SOURCE_DIRECT" for row in pricedex_rows)


def test_swsh6_charizardx_comparison_table_is_complete_and_non_divergent_for_supported_rows():
    status = _resolve_swsh6_source_frequency_status()
    comparison_table = _build_swsh6_charizardx_comparison_table()

    assert status == "closed_chilling_reign_source_frequency_partially_locked_with_provisional_rows"
    assert comparison_table

    by_bucket = {row["bucket"]: row for row in comparison_table}
    assert by_bucket["regular vmax"]["source_bucket_name"] == "VMAX"
    assert by_bucket["rainbow rare"]["source_bucket_name"] == "Rainbow"
    assert by_bucket["gold rare"]["source_bucket_name"] == "Gold"

    for bucket in SWSH6_SOURCE_DIRECT_BUCKETS:
        row = by_bucket[bucket]
        assert row["source_granularity_status"] == "SOURCE_DIRECT"
        assert row["absolute_delta"] == pytest.approx(0.0, abs=1e-12)
        assert row["pass_fail"] == "PASS"

    assert by_bucket["rare"]["source_granularity_status"] == "SOURCE_DERIVED_RESIDUAL"
    assert by_bucket["holo rare"]["source_granularity_status"] == "PROVISIONAL_DIRECTIONAL"
    assert by_bucket["regular v"]["source_granularity_status"] == "PROVISIONAL_DIRECTIONAL"


def test_swsh6_rare_residual_math_remains_exact_after_charizardx_patch():
    rare_slot_table = SetChillingReignConfig.RARE_SLOT_PROBABILITY
    non_rare_mass = sum(value for key, value in rare_slot_table.items() if key != "rare")

    assert rare_slot_table["rare"] == pytest.approx(1.0 - non_rare_mass, abs=1e-12)


def test_swsh6_source_audit_metadata_exposes_expected_source_labels_and_aliases():
    draft_audit = SetChillingReignConfig.CHILLING_REIGN_RARE_SLOT_PROBABILITY_DRAFT_AUDIT
    source_notes = SetChillingReignConfig.CHILLING_REIGN_PULL_RATE_SOURCE_NOTES

    assert draft_audit["source_label"] == "User-provided CharizardX posting transcription"
    assert source_notes["source"] == "PokemonTCG_Deals / CharmanderHelps Chilling Reign pull-rate post"
    assert source_notes["historical_label"] == "Previously labeled CharizardX/user-provided transcription."
    assert "PokemonTCG_Deals" in source_notes["source_aliases"]
    assert "@CharmanderHelps" in source_notes["source_aliases"]
    assert "CharizardX" in source_notes["source_aliases"]
    assert "CharmanderHelps/X" in source_notes["source_aliases"]


def test_swsh6_explicitly_removes_unsupported_rainbow_and_gold_split_rows():
    active_keys = set(SetChillingReignConfig.RARE_SLOT_PROBABILITY.keys())
    draft_audit = SetChillingReignConfig.CHILLING_REIGN_RARE_SLOT_PROBABILITY_DRAFT_AUDIT

    assert "rainbow rare" in active_keys
    assert "gold rare" in active_keys
    assert "rainbow trainer" not in active_keys
    assert "rainbow vmax" not in active_keys
    assert "gold secret rare" not in active_keys

    unsupported = draft_audit.get("unsupported_split_rows", {})
    assert unsupported.get("rainbow trainer") == "UNSUPPORTED_SPLIT"
    assert unsupported.get("rainbow vmax") == "UNSUPPORTED_SPLIT"
    assert unsupported.get("gold secret rare") == "UNSUPPORTED_SPLIT"


def test_sv_and_mega_routing_remain_unchanged_by_swsh_frequency_lock():
    assert _should_use_monte_carlo_v2(SetPaldeaEvolvedConfig) is True
    assert _should_use_monte_carlo_v2(SetMegaEvolutionConfig) is True
    assert get_simulation_engine(SetPaldeaEvolvedConfig) == "v2"
    assert get_simulation_engine(SetMegaEvolutionConfig) == "v2"
