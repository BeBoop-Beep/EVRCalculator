"""Guards for the two set-rebuild correctness defects.

1. Staleness was keyed on config_fingerprint, which hashes only the static
   per-set Python config. Desirability source data could change freely without
   ever invalidating a set row, so scheduled rebuilds skipped every set forever.

2. A set whose cards cannot be classified scored 0.0 on every component, which
   is indistinguishable from a genuinely unappealing set and ranked it as the
   worst product in the catalogue.
"""

from backend.scripts.build_pokemon_set_desirability_component_scores import (
    PARTIAL_COVERAGE_THRESHOLD,
    _normalized_snapshot_ids,
    _source_identity_key,
    _unrankable_sets,
    build_metric_status,
)


def _row(set_id="set-1", fingerprint="cfg-abc", trend_ids=None):
    return {
        "set_id": set_id,
        "config_fingerprint": fingerprint,
        "current_trend_snapshot_ids": trend_ids if trend_ids is not None else [11],
    }


# --- source-version-aware fingerprinting -----------------------------------


def test_changed_trend_snapshot_makes_a_set_stale():
    """The original bug: new Trends data must invalidate the existing row."""
    existing = _source_identity_key(_row(trend_ids=[11]))
    rebuilt = _source_identity_key(_row(trend_ids=[12]))
    assert existing != rebuilt


def test_identical_inputs_are_not_stale():
    """The other half: unchanged inputs must not trigger a pointless rebuild."""
    assert _source_identity_key(_row()) == _source_identity_key(_row())


def test_static_config_change_still_makes_a_set_stale():
    """The pre-existing invalidation path must keep working."""
    assert _source_identity_key(_row(fingerprint="cfg-abc")) != _source_identity_key(
        _row(fingerprint="cfg-xyz")
    )


def test_snapshot_ids_key_identically_across_storage_shapes():
    """Supabase returns jsonb; freshly built rows hold a plain list. If these
    keyed differently, every set would look stale on every run."""
    assert _normalized_snapshot_ids([11, 12]) == _normalized_snapshot_ids("[11, 12]")
    assert _normalized_snapshot_ids([12, 11]) == _normalized_snapshot_ids([11, 12])
    assert _normalized_snapshot_ids(None) == ""


def test_rebuild_changed_selects_only_stale_sets():
    existing_keys = {_source_identity_key(_row("set-1", trend_ids=[11]))}
    unchanged = _row("set-1", trend_ids=[11])
    changed = _row("set-1", trend_ids=[12])

    assert _source_identity_key(unchanged) in existing_keys
    assert _source_identity_key(changed) not in existing_keys


# --- missing data must not become zero -------------------------------------


def _audit(canonical=100, unknown=0, hits=20, linked=20):
    return {
        "canonical_card_count": canonical,
        "unknown_rarity_count": unknown,
        "hit_like_card_count": hits,
        "pokemon_linked_hit_count": linked,
    }


def test_all_unknown_rarity_is_unavailable_not_zero():
    # Renamed in set_metric_status_v2: "..._rarity" -> "..._rarity_mapping", to
    # keep the data-defect codes visibly distinct from unsupported_product_type.
    status = build_metric_status(_audit(canonical=100, unknown=100, hits=0, linked=0))
    assert status["metric_status"] == "unavailable_missing_rarity_mapping"
    assert status["rankable"] is False
    assert status["rarity_coverage_pct"] == 0.0
    assert "unknown rarity" in status["availability_reason"]


def test_no_hit_eligible_cards_on_a_supported_set_is_a_hit_structure_defect():
    """A SUPPORTED set with rarity data but no hit ladder is a defect in its hit
    structure, not a rarity problem.

    set_metric_status_v2 stopped reporting this as unavailable_missing_rarity:
    that diagnosis sent people to fix rarity mappings that were already correct.
    (For a fixed-contents product this branch is now unreachable - product type
    is decided first - so reaching it means a real booster set is broken.)
    """
    status = build_metric_status(_audit(canonical=100, unknown=40, hits=0, linked=0))
    assert status["metric_status"] == "unavailable_no_eligible_hit_structure"
    assert status["rankable"] is False


def test_unlinked_hits_are_reported_as_missing_subject_links():
    status = build_metric_status(_audit(hits=20, linked=0))
    assert status["metric_status"] == "unavailable_missing_subject_links"
    assert status["rankable"] is False


def test_set_with_no_canonical_cards_is_unsupported():
    status = build_metric_status(_audit(canonical=0, hits=0, linked=0))
    assert status["metric_status"] == "unsupported_product_type"
    assert status["rankable"] is False


def test_thin_coverage_is_partial_and_still_rankable():
    status = build_metric_status(_audit(canonical=100, unknown=80, hits=20, linked=20))
    assert status["metric_status"] == "partial"
    assert status["rankable"] is True
    assert status["rarity_coverage_pct"] == 20.0


def test_full_coverage_is_valid():
    status = build_metric_status(_audit())
    assert status["metric_status"] == "valid"
    assert status["availability_reason"] is None
    assert status["rankable"] is True


def test_partial_threshold_boundary_is_valid_not_partial():
    at_threshold = int(100 * PARTIAL_COVERAGE_THRESHOLD)
    status = build_metric_status(
        _audit(canonical=100, unknown=100 - at_threshold, hits=20, linked=20)
    )
    assert status["metric_status"] == "valid"


def test_pull_rate_coverage_is_none_rather_than_fabricated():
    """Pull rates are not resolved at this layer. Reporting a number would be
    fabrication; None correctly says 'not measured here'."""
    assert build_metric_status(_audit())["pull_rate_coverage_pct"] is None


# --- unsupported sets must not be ranked -----------------------------------


def test_unrankable_sets_are_reported_despite_scoring_zero():
    rows = [
        {
            "set_name": "Broken Set",
            "set_canonical_key": "brokenSet",
            "set_desirability_score": 0.0,
            "diagnostics_json": build_metric_status(_audit(canonical=50, unknown=50, hits=0, linked=0)),
        },
        {
            "set_name": "Good Set",
            "set_canonical_key": "goodSet",
            "set_desirability_score": 71.4,
            "diagnostics_json": build_metric_status(_audit()),
        },
    ]
    unrankable = _unrankable_sets(rows)
    assert [row["set_canonical_key"] for row in unrankable] == ["brokenSet"]
    assert unrankable[0]["metric_status"] == "unavailable_missing_rarity_mapping"


def test_a_genuine_zero_stays_rankable():
    """A valid set that simply scores 0.0 is information and must still rank."""
    rows = [
        {
            "set_name": "Genuinely Dull Set",
            "set_canonical_key": "dullSet",
            "set_desirability_score": 0.0,
            "diagnostics_json": build_metric_status(_audit()),
        }
    ]
    assert _unrankable_sets(rows) == []
