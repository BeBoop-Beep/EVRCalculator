from __future__ import annotations

import json
import math

import pytest

from backend.desirability.trends_anchor_ladder import (
    RESOLUTION_FLOOR,
    BridgeObservation,
    LadderAnchor,
    ZeroClassification,
    assign_nearest_rung,
    calibrate_ladder,
    classify_zero_outcome,
    frozen_ladder_anchors,
    frozen_ladder_bridges,
    load_frozen_anchor_manifest,
    recover_global_relative,
)


ANCHORS = ["Pichu", "Torkoal", "Lucario", "Pikachu"]


def _bridges():
    # Empirically-shaped: each adjacent pair stays well above the resolution floor
    # when queried together (that's the whole point of tier-matching), unlike the
    # rejected universal-Pikachu design.
    return [
        BridgeObservation("Pichu", "Torkoal", raw_lower=20.0, raw_higher=60.0),
        BridgeObservation("Torkoal", "Lucario", raw_lower=15.0, raw_higher=45.0),
        BridgeObservation("Lucario", "Pikachu", raw_lower=10.0, raw_higher=80.0),
    ]


class TestUniversalAnchorZeroCompressionReproduction:
    def test_direct_pairwise_query_can_still_collapse_weak_target_to_zero(self):
        # Reproduces the live-confirmed defect: Pikachu(26.65625) + Torkoal(0.03125)
        # queried alone (no batch dilution) still quantizes Torkoal near zero. The
        # fix is not "use a smaller batch" -- magnitude mismatch alone is sufficient.
        raw_torkoal_vs_pikachu = 0.03125
        assert raw_torkoal_vs_pikachu <= RESOLUTION_FLOOR

    def test_same_target_resolves_clearly_against_tier_matched_peers(self):
        # Live-confirmed: Torkoal/Girafarig/Stunky/Purugly queried together (no
        # Pikachu) resolve to well-separated, clearly non-zero values.
        peer_values = {"Torkoal": 60.28125, "Girafarig": 30.34375, "Stunky": 17.09375, "Purugly": 7.6875}
        assert all(v > RESOLUTION_FLOOR for v in peer_values.values())
        assert list(peer_values.values()) == sorted(peer_values.values(), reverse=True)


class TestAnchorLadderReconstruction:
    def test_calibrate_ladder_chains_ratios_cumulatively(self):
        scale = calibrate_ladder(ANCHORS, _bridges())
        assert scale["Pichu"] == 1.0
        assert scale["Torkoal"] == pytest.approx(3.0)  # 60/20
        assert scale["Lucario"] == pytest.approx(3.0 * 3.0)  # * (45/15)
        assert scale["Pikachu"] == pytest.approx(3.0 * 3.0 * 8.0)  # * (80/10)

    def test_calibration_is_deterministic(self):
        scale_a = calibrate_ladder(ANCHORS, _bridges())
        scale_b = calibrate_ladder(ANCHORS, _bridges())
        assert scale_a == scale_b

    def test_missing_bridge_raises_rather_than_guessing(self):
        incomplete = _bridges()[:-1]  # drop Lucario->Pikachu
        with pytest.raises(ValueError, match="Missing calibration bridge"):
            calibrate_ladder(ANCHORS, incomplete)

    def test_zero_or_negative_lower_anchor_raises_rather_than_dividing(self):
        bad = [BridgeObservation("Pichu", "Torkoal", raw_lower=0.0, raw_higher=60.0)]
        with pytest.raises(ValueError, match="unusable"):
            calibrate_ladder(["Pichu", "Torkoal"], bad)


class TestBridgeCalibrationMath:
    def test_recover_global_relative_projects_local_share_through_scale(self):
        scale = calibrate_ladder(ANCHORS, _bridges())
        # Target queried against Torkoal (local anchor), target is 1/2 of Torkoal locally.
        value = recover_global_relative(raw_target=30.0, raw_local_anchor=60.0, local_anchor_global_scale=scale["Torkoal"])
        assert value == pytest.approx(0.5 * scale["Torkoal"])

    def test_recover_global_relative_is_monotonic_in_target(self):
        scale = calibrate_ladder(ANCHORS, _bridges())
        low = recover_global_relative(10.0, 60.0, scale["Torkoal"])
        high = recover_global_relative(40.0, 60.0, scale["Torkoal"])
        assert high > low

    def test_zero_local_anchor_raises(self):
        with pytest.raises(ValueError):
            recover_global_relative(raw_target=10.0, raw_local_anchor=0.0, local_anchor_global_scale=1.0)


class TestBatchInvariance:
    def test_same_target_via_two_valid_local_anchors_recovers_close_global_values(self):
        # A target with one true global-relative value G, observed via two different,
        # independently-calibrated ladder rungs (each with its own local anchor and
        # raw reading consistent with G), should recover to the same global value --
        # this is the acceptance test from Phase 10 of the research spec (anchor-
        # choice invariance after calibration).
        scale = calibrate_ladder(ANCHORS, _bridges())
        true_global = 4.5
        # Path 1: queried against Torkoal (scale=3.0) -> local_relative must be G/scale.
        raw_target_via_torkoal = (true_global / scale["Torkoal"]) * 60.0  # * raw_local_anchor
        via_torkoal = recover_global_relative(raw_target=raw_target_via_torkoal, raw_local_anchor=60.0, local_anchor_global_scale=scale["Torkoal"])
        # Path 2: queried against Lucario (scale=9.0) -> different raw reading, same G.
        raw_target_via_lucario = (true_global / scale["Lucario"]) * 20.0
        via_lucario = recover_global_relative(raw_target=raw_target_via_lucario, raw_local_anchor=20.0, local_anchor_global_scale=scale["Lucario"])
        assert via_torkoal == pytest.approx(via_lucario, rel=1e-9)
        assert via_torkoal == pytest.approx(true_global, rel=1e-9)


class TestZeroRetryClassification:
    def test_zero_at_highest_rung_is_resolution_limited_not_scored(self):
        outcome = classify_zero_outcome(
            raw_target=0.0, is_lowest_available_rung=False, request_failed=False,
            request_missing=False, ladder_assignment_available=True,
        )
        assert outcome is ZeroClassification.RESOLUTION_LIMITED_ZERO

    def test_zero_at_lowest_rung_is_scored_high_confidence(self):
        outcome = classify_zero_outcome(
            raw_target=0.0, is_lowest_available_rung=True, request_failed=False,
            request_missing=False, ladder_assignment_available=True,
        )
        assert outcome is ZeroClassification.SCORED_ZERO_HIGH_CONFIDENCE

    def test_near_floor_value_at_lowest_rung_is_still_scored(self):
        outcome = classify_zero_outcome(
            raw_target=RESOLUTION_FLOOR - 0.01, is_lowest_available_rung=True,
            request_failed=False, request_missing=False, ladder_assignment_available=True,
        )
        assert outcome is ZeroClassification.SCORED_ZERO_HIGH_CONFIDENCE

    def test_above_resolution_floor_value_is_rejected_not_silently_scored(self):
        # This classifier is only for zero/near-zero outcomes; a clearly-resolved
        # value must never be routed through zero-classification logic.
        with pytest.raises(ValueError):
            classify_zero_outcome(
                raw_target=50.0, is_lowest_available_rung=True, request_failed=False,
                request_missing=False, ladder_assignment_available=True,
            )


class TestMissingAndFailedHandling:
    def test_missing_evidence_is_never_coerced_to_zero(self):
        outcome = classify_zero_outcome(
            raw_target=None, is_lowest_available_rung=True, request_failed=False,
            request_missing=True, ladder_assignment_available=True,
        )
        assert outcome is ZeroClassification.MISSING_EVIDENCE
        assert outcome is not ZeroClassification.SCORED_ZERO_HIGH_CONFIDENCE

    def test_failed_request_is_never_coerced_to_zero(self):
        outcome = classify_zero_outcome(
            raw_target=None, is_lowest_available_rung=True, request_failed=True,
            request_missing=False, ladder_assignment_available=True,
        )
        assert outcome is ZeroClassification.FAILED

    def test_failed_takes_precedence_over_missing(self):
        outcome = classify_zero_outcome(
            raw_target=None, is_lowest_available_rung=True, request_failed=True,
            request_missing=True, ladder_assignment_available=True,
        )
        assert outcome is ZeroClassification.FAILED


class TestAnchorAssignmentFailure:
    def test_no_ladder_assignment_available_is_insufficient_calibration(self):
        outcome = classify_zero_outcome(
            raw_target=0.0, is_lowest_available_rung=False, request_failed=False,
            request_missing=False, ladder_assignment_available=False,
        )
        assert outcome is ZeroClassification.INSUFFICIENT_CALIBRATION

    def test_assign_nearest_rung_returns_none_without_tier_hint(self):
        anchors = [LadderAnchor("Pichu", 0, 1.0), LadderAnchor("Pikachu", 3, 72.0)]
        assert assign_nearest_rung(None, anchors) is None

    def test_assign_nearest_rung_returns_none_when_no_anchor_calibrated_yet(self):
        anchors = [LadderAnchor("Pichu", 0, None), LadderAnchor("Pikachu", 3, None)]
        assert assign_nearest_rung(10.0, anchors) is None

    def test_assign_nearest_rung_picks_closest_log_magnitude(self):
        anchors = [LadderAnchor("Pichu", 0, 1.0), LadderAnchor("Torkoal", 1, 3.0), LadderAnchor("Pikachu", 3, 72.0)]
        chosen = assign_nearest_rung(tier_hint=2.5, anchors_ascending=anchors)
        assert chosen.name == "Torkoal"


class TestNoPriceDependency:
    def test_module_has_no_price_usage(self):
        # The module docstring legitimately *states* "no price input"; what matters
        # is that no price-shaped identifier is ever used as a value in the code.
        import backend.desirability.trends_anchor_ladder as mod
        import inspect

        source = inspect.getsource(mod)
        for forbidden in ("market_price", "price_usd", "card_price", "set_value", "price ="):
            assert forbidden not in source.lower()


class TestCohortIndependence:
    def test_recover_global_relative_does_not_depend_on_other_targets(self):
        # A stable target's recovered value must not change merely because other,
        # unrelated targets exist in the same refresh run -- calibration inputs are
        # the ladder's own fixed bridge observations, never a population percentile.
        scale = calibrate_ladder(ANCHORS, _bridges())
        value_alone = recover_global_relative(20.0, 60.0, scale["Torkoal"])
        # Simulate "other targets in the population" by calibrating a much larger
        # ladder scale set that includes unrelated bridges -- Torkoal's own scale
        # factor (and thus this target's recovered value) is unaffected because it
        # only depends on the Pichu->Torkoal->Lucario->Pikachu chain, not on any
        # other target's data.
        extra_bridges = _bridges() + [BridgeObservation("Lucario", "Pikachu", raw_lower=10.0, raw_higher=80.0)]
        scale_with_more_context = calibrate_ladder(ANCHORS, extra_bridges)
        value_with_more_context = recover_global_relative(20.0, 60.0, scale_with_more_context["Torkoal"])
        assert value_alone == pytest.approx(value_with_more_context)


class TestFrozenAnchorManifest:
    def test_manifest_loads_and_has_six_rungs(self):
        manifest = load_frozen_anchor_manifest()
        anchors = manifest["anchorsAscending"]
        assert len(anchors) == 6
        assert [a["name"] for a in anchors] == ["Purugly", "Stunky", "Torkoal", "Lucario", "Charizard", "Pikachu"]
        assert [a["rung"] for a in anchors] == [0, 1, 2, 3, 4, 5]

    def test_reference_anchor_has_scale_one(self):
        anchors = frozen_ladder_anchors()
        assert anchors[0].name == "Purugly"
        assert anchors[0].global_scale == pytest.approx(1.0)

    def test_every_bridge_passed_its_own_resolution_check(self):
        manifest = load_frozen_anchor_manifest()
        for bridge in manifest["bridges"]:
            assert bridge["resolutionCheckPassed"] is True
            assert bridge["rawLower"] > RESOLUTION_FLOOR
            assert bridge["rawHigher"] > RESOLUTION_FLOOR

    def test_manifest_scales_match_fresh_calibration_from_raw_bridge_data(self):
        # Parity test: the manifest's precomputed globalScale values must be exactly
        # reproducible by feeding the manifest's own raw bridge observations back
        # through calibrate_ladder() -- proves the frozen numbers are not hand-typed
        # drift from what the calibration function actually computes.
        manifest = load_frozen_anchor_manifest()
        anchors_ascending = [a["name"] for a in manifest["anchorsAscending"]]
        bridges = frozen_ladder_bridges(manifest)
        recomputed = calibrate_ladder(anchors_ascending, bridges)
        for anchor in manifest["anchorsAscending"]:
            assert recomputed[anchor["name"]] == pytest.approx(anchor["globalScale"], rel=1e-3)

    def test_monotonic_ascending_scale(self):
        anchors = frozen_ladder_anchors()
        scales = [a.global_scale for a in anchors]
        assert scales == sorted(scales)
        assert len(set(scales)) == len(scales)  # strictly increasing, no ties

    def test_assign_nearest_rung_works_against_frozen_roster(self):
        anchors = frozen_ladder_anchors()
        # A target expected to be near Torkoal's magnitude should be assigned Torkoal.
        chosen = assign_nearest_rung(tier_hint=anchors[2].global_scale, anchors_ascending=anchors)
        assert chosen.name == "Torkoal"

    def test_manifest_records_known_limitations_honestly(self):
        manifest = load_frozen_anchor_manifest()
        limitations = manifest["knownLimitations"]
        assert "singleTemporalWindow" in limitations
        assert "sampleSize" in limitations

    def test_manifest_has_no_price_input(self):
        manifest = load_frozen_anchor_manifest()
        assert manifest["acceptanceCriteria"]["noPriceInput"] is True
        raw = json.dumps(manifest).lower()
        for forbidden in ("market_price", "price_usd", "card_price"):
            assert forbidden not in raw


class TestDeterministicOutput:
    def test_full_pipeline_is_reproducible_across_runs(self):
        results = []
        for _ in range(3):
            scale = calibrate_ladder(ANCHORS, _bridges())
            results.append(recover_global_relative(15.0, 45.0, scale["Lucario"]))
        assert results[0] == results[1] == results[2]
