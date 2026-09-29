from pathlib import Path

import pytest

from backend.scripts.build_pokemon_collector_appeal_v8_anchor25 import (
    ALPHA,
    ANCHOR_METHOD,
    MODEL_VERSION,
    apply_combined_headroom_lift,
    calibrated_subject,
    component_diagnostic_rows,
    realized_combined_headroom_fraction,
    tie_percentiles,
)


def test_v8_identity_and_alpha_are_frozen():
    assert MODEL_VERSION == "pokemon_collector_appeal_v8_anchor25_cross_domain_v1"
    assert ALPHA == 0.25
    assert ANCHOR_METHOD == "trainer_tie_midrank_percentile_to_pokemon_empirical_quantile_v1"


def test_calibration_changes_only_trainers():
    assert calibrated_subject(original=80.0, anchor=60.0, domain="trainer") == 75.0
    assert calibrated_subject(original=80.0, anchor=60.0, domain="pokemon") == 80.0
    assert calibrated_subject(original=80.0, anchor=60.0, domain="neutral_functional") == 80.0


def test_tie_midrank_percentiles_are_stable():
    pct = tie_percentiles({"a": 1.0, "b": 1.0, "c": 3.0})
    assert pct["a"] == pct["b"]
    assert pct["a"] < pct["c"]


def test_builder_does_not_promote_or_change_current_pointer():
    source = Path("backend/scripts/build_pokemon_collector_appeal_v8_anchor25.py").read_text(encoding="utf-8").lower()
    assert "promote_pokemon_collector" not in source
    assert "select_pokemon_collector_appeal_current" not in source
    assert "pokemon_collector_appeal_current" in source  # read-only baseline binding
    assert "--write-stage" in source


def test_default_execution_is_not_write_stage():
    source = Path("backend/scripts/build_pokemon_collector_appeal_v8_anchor25.py").read_text(encoding="utf-8")
    assert 'parser.add_argument("--write-stage", action="store_true")' in source
    assert "if args.write_stage:" in source


def test_validated_candidate_preserves_exact_realized_v7_headroom_fraction():
    fraction = realized_combined_headroom_fraction(subject_v7=40.0, card_score_v7=55.0)
    assert fraction == pytest.approx(0.25)
    assert apply_combined_headroom_lift(40.0, fraction) == pytest.approx(55.0)
    # ANCHOR25 changes only the Trainer subject and carries forward the exact
    # realized V7 downstream headroom fraction.
    subject_v8 = calibrated_subject(original=40.0, anchor=80.0, domain="trainer")
    assert subject_v8 == pytest.approx(50.0)
    assert apply_combined_headroom_lift(subject_v8, fraction) == pytest.approx(62.5)


def test_invalid_v7_combined_fraction_is_rejected():
    with pytest.raises(RuntimeError, match="V8_INVALID_V7_COMBINED_LIFT_FRACTION"):
        realized_combined_headroom_fraction(subject_v7=50.0, card_score_v7=110.0)


def test_builder_does_not_recompute_unvalidated_post_calibration_lift_decomposition():
    source = Path("backend/scripts/build_pokemon_collector_appeal_v8_anchor25.py").read_text(encoding="utf-8")
    assert '"downstreamLiftMode": "preserve_exact_v7_realized_combined_headroom_fraction"' in source
    assert '"artist_lift": None' in source
    assert '"playability_lift": None' in source
    assert '"combined_lift": combined_fraction' in source
    assert "playabilityArtistDecomposition" in source


def test_default_frozen_cutover_is_offline_until_live_or_write_is_requested():
    source = Path("backend/scripts/build_pokemon_collector_appeal_v8_anchor25.py").read_text(encoding="utf-8")
    assert "if args.live_rebuild or args.write_stage:" in source
    assert "built = build_frozen_cutover()" in source


def test_v8_set_component_diagnostics_do_not_invent_playability_artist_decomposition():
    rows = component_diagnostic_rows([
        {
            "model_run_id": "run",
            "set_id": "set",
            "subject_baseline_score": 75.0,
            "subject_policy": "trainer",
            "playability_score": 42.0,
            "artist_recognition_score": 91.0,
            "collector_card_appeal_score": 82.0,
        }
    ])
    assert rows[0]["subject_baseline_score"] == 75.0
    assert rows[0]["subject_policy"] == "trainer"
    assert rows[0]["playability_score"] is None
    assert rows[0]["artist_recognition_score"] is None
    assert rows[0]["collector_card_appeal_score"] == 82.0
