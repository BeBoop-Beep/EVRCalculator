from backend.constants.tcg.pokemon.megaEvolutionEra.megaEvolution import SetMegaEvolutionConfig
from backend.constants.tcg.pokemon.scarletAndVioletEra.paldeaEvolved import SetPaldeaEvolvedConfig
from backend.constants.tcg.pokemon.swordAndShieldEra.chillingReign import SetChillingReignConfig
from backend.constants.tcg.pokemon.swordAndShieldEra.evolvingSkies import SetEvolvingSkiesConfig
from backend.scripts.audit_swsh_slot_schema_readiness import (
    FINAL_ALLOWED_BUCKETS,
    SetConfigMeta,
    _analyze_set_rows,
    _extract_complete_bucket_classification_audit,
    discover_swsh_set_configs,
    run_readiness_audit,
    split_swsh_targets,
)
from backend.simulations.evrSimulator import get_simulation_engine


def _make_meta() -> SetConfigMeta:
    return SetConfigMeta(
        set_key="testSet",
        class_name="TestSetConfig",
        set_name="Test Set",
        set_id="swsh-test",
        printed_total=100,
        total=120,
        simulation_engine="slot_schema",
        slot_schema_runtime_enabled=False,
        has_rare_slot_probability=False,
        has_reverse_slot_probabilities=True,
        reverse_slot_probability_shape="slots=slot_1",
        standard_pack_shape=True,
        pack_shape_reason="standard",
        source_confidence_status="",
        source_confidence_runtime_ready=False,
        source_confidence_probability_ready=False,
    )


def _meta_from_config(config_cls, set_key: str) -> SetConfigMeta:
    source_confidence = getattr(config_cls, "SLOT_SCHEMA_SOURCE_CONFIDENCE", {})
    if not isinstance(source_confidence, dict):
        source_confidence = {}

    reverse_table = getattr(config_cls, "REVERSE_SLOT_PROBABILITIES", None)
    reverse_shape = "missing"
    if isinstance(reverse_table, dict):
        reverse_shape = f"slots={','.join(sorted(str(k) for k in reverse_table.keys()))}"

    return SetConfigMeta(
        set_key=set_key,
        class_name=config_cls.__name__,
        set_name=str(getattr(config_cls, "SET_NAME", set_key)),
        set_id=str(getattr(config_cls, "SET_ID", "")),
        printed_total=getattr(config_cls, "PRINTED_TOTAL", None),
        total=getattr(config_cls, "TOTAL", None),
        simulation_engine=str(getattr(config_cls, "SIMULATION_ENGINE", "v2")),
        slot_schema_runtime_enabled=bool(getattr(config_cls, "SLOT_SCHEMA_RUNTIME_ENABLED", False)),
        has_rare_slot_probability=hasattr(config_cls, "RARE_SLOT_PROBABILITY"),
        has_reverse_slot_probabilities=isinstance(reverse_table, dict),
        reverse_slot_probability_shape=reverse_shape,
        standard_pack_shape=True,
        pack_shape_reason="standard",
        source_confidence_status=str(source_confidence.get("status", "")),
        source_confidence_runtime_ready=(
            bool(source_confidence["runtime_ready"]) if "runtime_ready" in source_confidence else None
        ),
        source_confidence_probability_ready=(
            bool(source_confidence["rare_slot_probability_ready"])
            if "rare_slot_probability_ready" in source_confidence
            else None
        ),
    )


def test_standard_swsh_target_discovery_excludes_special_sets():
    split = split_swsh_targets(discover_swsh_set_configs())
    included_ids = {row["set_id"] for row in split["included"]}
    excluded_ids = {row["set_id"] for row in split["excluded"]}

    assert "swsh1" in included_ids
    assert "swsh12" in included_ids

    assert "cel25" in excluded_ids
    assert "swsh45" in excluded_ids
    assert "swsh12pt5" in excluded_ids
    assert "pgo" in excluded_ids


def test_chilling_reign_and_evolving_skies_are_intentionally_enabled_in_discovery():
    by_id = {row.set_id: row for row in discover_swsh_set_configs()}

    assert by_id["swsh6"].slot_schema_runtime_enabled is True
    assert by_id["swsh7"].slot_schema_runtime_enabled is True
    assert by_id["swsh6"].has_rare_slot_probability is True
    assert by_id["swsh7"].has_rare_slot_probability is True

    # Scope guardrail: do not bulk-enable other SWSH sets.
    assert by_id["swsh1"].slot_schema_runtime_enabled is False
    assert by_id["swsh1"].has_rare_slot_probability is False


def test_batch_audit_does_not_enable_runtime_or_add_rare_slot_probability(monkeypatch, tmp_path):
    before_chilling_runtime = SetChillingReignConfig.SLOT_SCHEMA_RUNTIME_ENABLED
    before_evs_runtime = SetEvolvingSkiesConfig.SLOT_SCHEMA_RUNTIME_ENABLED
    before_chilling_has_rare = hasattr(SetChillingReignConfig, "RARE_SLOT_PROBABILITY")
    before_evs_has_rare = hasattr(SetEvolvingSkiesConfig, "RARE_SLOT_PROBABILITY")

    monkeypatch.setattr(
        "backend.scripts.audit_swsh_slot_schema_readiness._get_supabase_client",
        lambda: (None, "test-no-db"),
    )

    run_readiness_audit(
        json_output_path=tmp_path / "matrix.json",
        markdown_output_path=tmp_path / "matrix.md",
    )

    assert SetChillingReignConfig.SLOT_SCHEMA_RUNTIME_ENABLED is before_chilling_runtime
    assert SetEvolvingSkiesConfig.SLOT_SCHEMA_RUNTIME_ENABLED is before_evs_runtime
    assert hasattr(SetChillingReignConfig, "RARE_SLOT_PROBABILITY") is before_chilling_has_rare
    assert hasattr(SetEvolvingSkiesConfig, "RARE_SLOT_PROBABILITY") is before_evs_has_rare


def test_bucket_classification_uses_normalized_bucket_names_and_reverse_policies():
    meta = _make_meta()

    cards = [
        {"id": "c1", "rarity": "Rare", "name": "A", "card_number": "10", "set_name": "Test", "supertype": "Pokemon", "subtypes": ["Basic"]},
        {"id": "c2", "rarity": "Holo Rare", "name": "B", "card_number": "11", "set_name": "Test", "supertype": "Pokemon", "subtypes": ["Basic"]},
        {"id": "c3", "rarity": "Ultra Rare", "name": "Hero V", "card_number": "50", "set_name": "Test", "supertype": "Pokemon", "subtypes": ["Basic", "V"]},
        {"id": "c4", "rarity": "Secret Rare", "name": "Hero VMAX", "card_number": "110", "set_name": "Test", "supertype": "Pokemon", "subtypes": ["VMAX"]},
    ]

    variants = [
        {"id": "v1", "card_id": "c1", "printing_type": "non-holo", "special_type": None, "edition": None},
        {"id": "v2", "card_id": "c2", "printing_type": "holo", "special_type": None, "edition": None},
        {"id": "v3", "card_id": "c3", "printing_type": "holo", "special_type": None, "edition": None},
        {"id": "v4", "card_id": "c4", "printing_type": "reverse-holo", "special_type": "Alternate Art Secret", "edition": None},
    ]

    result = _analyze_set_rows(meta, "candidate_standard", "test", cards, variants, market_rows=[])

    assert set(result["bucket_counts"].keys()).issubset(FINAL_ALLOWED_BUCKETS)
    assert "ultra rare" not in result["bucket_counts"]
    assert "secret rare" not in result["bucket_counts"]

    assert result["counts"]["reverse_holo_in_rare_slot_count"] == 1
    assert result["counts"]["eligible_non_reverse_rare_family_variants"] == 3
    assert "rare is residual-capable" in result["notes"]


def test_sets_with_unmapped_or_overlap_are_not_runtime_ready_candidates():
    meta = _make_meta()

    cards = [
        {"id": "c1", "rarity": "Ultra Rare", "name": "Ambiguous V Full Art", "card_number": "40", "set_name": "Test", "supertype": "Pokemon", "subtypes": ["V"]},
        {"id": "c2", "rarity": "Secret Rare", "name": "Unknown Secret", "card_number": "99", "set_name": "Test", "supertype": "Pokemon", "subtypes": []},
    ]
    variants = [
        {"id": "v1", "card_id": "c1", "printing_type": "holo", "special_type": "full art", "edition": None},
        {"id": "v2", "card_id": "c2", "printing_type": "holo", "special_type": None, "edition": None},
    ]

    result = _analyze_set_rows(meta, "candidate_standard", "test", cards, variants, market_rows=[])

    assert result["counts"]["eligible_non_reverse_rare_family_variants"] == 2
    assert result["counts"]["mapped_variants"] < result["counts"]["eligible_non_reverse_rare_family_variants"]
    assert result["runtime_ready_candidate"] is False


def test_dedicated_complete_bucket_audit_overrides_generic_classifier_for_chilling_reign():
    meta = _meta_from_config(SetChillingReignConfig, "chillingReign")
    dedicated = _extract_complete_bucket_classification_audit(SetChillingReignConfig)

    assert dedicated is not None
    assert dedicated["audit_attribute"] == "CHILLING_REIGN_BUCKET_CLASSIFICATION_AUDIT"

    result = _analyze_set_rows(
        meta,
        "candidate_standard",
        "mainline Sword & Shield set id",
        cards=[],
        variants=[],
        market_rows=[],
        dedicated_bucket_audit=dedicated,
    )

    assert result["bucket_classification_status"] == "bucket_classification_ready"
    assert result["mapping_confidence"] == "high"
    assert result["counts"]["eligible_non_reverse_rare_family_variants"] == 144
    assert result["counts"]["mapped_variants"] == 144
    assert result["counts"]["unmapped_variants"] == 0
    assert result["counts"]["overlapping_variants"] == 0
    assert result["probability_readiness"] in {
        "probability_ready_candidate",
        "base_non_rare_rows_missing",
        "partial_high_rarity_rows_only",
    }
    assert result["recommended_next_action"] in {
        "already_blocked_probability_only",
        "ready_for_probability_modeling_if_rates_provided",
    }
    assert result["dedicated_bucket_classification_audit_used"] is True


def test_dedicated_complete_bucket_audit_overrides_generic_classifier_for_evolving_skies():
    meta = _meta_from_config(SetEvolvingSkiesConfig, "evolvingSkies")
    dedicated = _extract_complete_bucket_classification_audit(SetEvolvingSkiesConfig)

    assert dedicated is not None
    assert dedicated["audit_attribute"] == "EVOLVING_SKIES_BUCKET_CLASSIFICATION_AUDIT"

    result = _analyze_set_rows(
        meta,
        "candidate_standard",
        "mainline Sword & Shield set id",
        cards=[],
        variants=[],
        market_rows=[],
        dedicated_bucket_audit=dedicated,
    )

    assert result["bucket_classification_status"] == "bucket_classification_ready"
    assert result["mapping_confidence"] == "high"
    assert result["counts"]["eligible_non_reverse_rare_family_variants"] == 144
    assert result["counts"]["mapped_variants"] == 144
    assert result["counts"]["unmapped_variants"] == 0
    assert result["counts"]["overlapping_variants"] == 0
    assert result["probability_readiness"] == "probability_ready_candidate"
    assert result["recommended_next_action"] in {
        "already_blocked_probability_only",
        "ready_for_probability_modeling_if_rates_provided",
    }
    assert result["dedicated_bucket_classification_audit_used"] is True


def test_generic_classifier_fallback_still_used_when_no_dedicated_audit():
    meta = _make_meta()

    cards = [
        {"id": "c1", "rarity": "Ultra Rare", "name": "Ambiguous V Full Art", "card_number": "40", "set_name": "Test", "supertype": "Pokemon", "subtypes": ["V"]},
        {"id": "c2", "rarity": "Secret Rare", "name": "Unknown Secret", "card_number": "99", "set_name": "Test", "supertype": "Pokemon", "subtypes": []},
    ]
    variants = [
        {"id": "v1", "card_id": "c1", "printing_type": "holo", "special_type": "full art", "edition": None},
        {"id": "v2", "card_id": "c2", "printing_type": "holo", "special_type": None, "edition": None},
    ]

    result = _analyze_set_rows(
        meta,
        "candidate_standard",
        "test",
        cards,
        variants,
        market_rows=[],
        dedicated_bucket_audit=None,
    )

    assert result["dedicated_bucket_classification_audit_used"] is False
    assert result["bucket_classification_status"] != "bucket_classification_ready"
    assert result["counts"]["mapped_variants"] < result["counts"]["eligible_non_reverse_rare_family_variants"]


def test_sv_and_mega_routing_remains_v2():
    assert get_simulation_engine(SetPaldeaEvolvedConfig) == "v2"
    assert get_simulation_engine(SetMegaEvolutionConfig) == "v2"
