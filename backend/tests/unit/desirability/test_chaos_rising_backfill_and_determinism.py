"""Phase 8.2: the Chaos Rising backfill, and determinism proved rather than claimed.

TWO THINGS THIS FILE DEFENDS
----------------------------
1. **The Chaos Rising gap is closed on the source contract, not by softening it.**
   Chaos Rising was the one set of 171 with no ``v2_coverage_cleanup`` component
   row, and it kept a historical v1 row. The fix was to BUILD the missing row.
   The tests below assert that CA7 still refuses the v1 row, that it consumes the
   new exact row, and that absence and duplication remain visible failures. A
   test suite that only checked "Chaos Rising now has CA7" would also pass if
   someone had made the loader fall back to v1, which is the outcome the whole
   contract exists to prevent.

2. **Determinism is two different claims.** Phase 8.1 proved the in-process one
   (build twice from one loaded state) and reported the cross-run one as settled
   without ever executing it. They fail differently: in-process catches impure
   build code; cross-run catches ordering and serialization that is only stable
   within a single interpreter, and it is the only one that can distinguish
   "the source moved" from "the code is nondeterministic".
"""

from __future__ import annotations

import copy

import pytest

from backend.desirability.collector_appeal import COLLECTOR_APPEAL_DIAGNOSTICS_KEY
from backend.desirability.collector_appeal_fingerprint import current_fingerprint
from backend.desirability.collector_appeal_rollout import (
    COMPONENT_TABLE,
    DETERMINISM_IDENTICAL,
    DETERMINISM_NONDETERMINISTIC,
    DETERMINISM_SOURCE_DRIFT,
    DETERMINISM_FORMULA_CHANGED,
    build_full_source_manifest,
    build_update_plan,
    compare_dry_run_artifacts,
    load_source_state,
    normalized_payload_hash,
    rip_consumed_coverage,
)
from backend.desirability.component_source import (
    EXPECTED_COMPOSITE_SCORING_VERSION,
    EXPECTED_HIT_POLICY_VERSION,
    EXPECTED_SCORING_VERSION,
    MISSING_CURRENT_COMPONENT_SOURCE_ROW,
    DUPLICATE_CURRENT_COMPONENT_SOURCE_ROW,
    select_component_source_rows,
)

V1 = "pokemon_card_desirability_hit_policy_v1"

# Production identities, so the fixture describes the real backfill.
CHAOS_SET_ID = "5bdbfae1-3f2e-44e7-b8c9-1035ad45b896"
CHAOS_KEY = "chaosRising"
CHAOS_EXACT_ROW_ID = "6e4cf65f-6846-4e7a-91dd-346550d31dca"
CHAOS_V1_ROW_ID = "23ad1e53-11c0-422e-beed-6ef2afcfcf63"

# The v1 row is OLDER than the new exact row for Chaos Rising specifically, which
# is why "take the newest" happens to work for THIS set and fails for the other
# 170. The tests must not lean on that accident.
CHAOS_V1_BUILT_AT = "2026-06-16T17:03:14.983277+00:00"
CHAOS_EXACT_BUILT_AT = "2026-07-16T16:18:08.108889+00:00"


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

class _Query:
    def __init__(self, rows):
        self._rows = rows
        self._range = (0, len(rows))

    def select(self, *args, **kwargs):
        return self

    def order(self, *args, **kwargs):
        return self

    def range(self, start, end):
        self._range = (start, end)
        return self

    def execute(self):
        start, end = self._range
        return type("R", (), {"data": self._rows[start:end + 1]})()


class _Client:
    def __init__(self, rows):
        self.rows = rows

    def table(self, name):
        assert name == COMPONENT_TABLE
        return _Query(self.rows)


def _rollups():
    return [
        {
            "subject_key": "ref:1",
            "subject_name": "Pikachu",
            "pokemon_reference_id": 1,
            "max_desirability_score": 90.0,
            "rarity_buckets_present": ["premium_chase"],
            "card_count": 2,
        }
    ]


def _row(
    set_id,
    key,
    score,
    *,
    hit_policy=EXPECTED_HIT_POLICY_VERSION,
    row_id=None,
    built_at="2026-06-14T22:59:34Z",
    config_fingerprint=None,
):
    return {
        "id": row_id or f"row-{set_id}-{hit_policy}",
        "set_id": set_id,
        "set_name": key,
        "set_canonical_key": key,
        "scoring_version": EXPECTED_SCORING_VERSION,
        "hit_policy_version": hit_policy,
        "composite_scoring_version": EXPECTED_COMPOSITE_SCORING_VERSION,
        "fan_popularity_snapshot_id": "2",
        "config_fingerprint": config_fingerprint or f"cfg-{set_id}",
        "set_desirability_score": score,
        "hit_eligible_card_count": 40,
        "scored_hit_eligible_card_count": 40,
        "unique_subject_count": 10,
        "subject_rollups_json": _rollups(),
        "diagnostics_json": {"canonical_cards_seen": 100},
        "built_at": built_at,
        "updated_at": built_at,
    }


def _chaos_v1():
    return _row(CHAOS_SET_ID, CHAOS_KEY, 43.3903, hit_policy=V1,
                row_id=CHAOS_V1_ROW_ID, built_at=CHAOS_V1_BUILT_AT)


def _chaos_exact():
    return _row(CHAOS_SET_ID, CHAOS_KEY, 43.3903, row_id=CHAOS_EXACT_ROW_ID,
                built_at=CHAOS_EXACT_BUILT_AT)


def _other_sets():
    return [
        _row("s1", "evolvingSkies", 70.0),
        _row("s1", "evolvingSkies", 70.0, hit_policy=V1, row_id="row-s1-v1",
             built_at="2027-01-01T00:00:00Z"),
    ]


def _subjects():
    return {
        CHAOS_SET_ID: [{
            "subject_key": "ref:1", "subject_name": "Pikachu", "subject_demand": 90.0,
            "appeal_excess": 0.8,
            "cards": [
                {"card_name": "easy", "pull_probability": 0.1},
                {"card_name": "elite", "pull_probability": 0.001},
            ],
        }],
        "s1": [{
            "subject_key": "ref:1", "subject_name": "Pikachu", "subject_demand": 90.0,
            "appeal_excess": 0.8,
            "cards": [
                {"card_name": "easy", "pull_probability": 0.1},
                {"card_name": "elite", "pull_probability": 0.001},
            ],
        }],
    }


def _plan(rows, subjects=None):
    subjects = _subjects() if subjects is None else subjects
    state = load_source_state(_Client(rows))
    return build_update_plan(
        state,
        subject_builder=lambda set_id: subjects.get(set_id),
        subjects_by_set=subjects,
    ), state


def _artifact(plan, state, generated_at="2026-07-16T00:00:00+00:00"):
    """The subset of the dry-run artifact the cross-run comparison reads."""
    return {
        "generated_at": generated_at,
        "expected_fingerprint": plan["expected_fingerprint"],
        "normalized_payload_hash": plan["normalized_payload_hash"],
        "source_manifest": plan["source_manifest"],
        "counts": plan["counts"],
        "products": list(plan["rows"]),
    }


# ---------------------------------------------------------------------------
# Chaos Rising: the backfilled exact row
# ---------------------------------------------------------------------------

def test_chaos_rising_exact_row_is_selected_over_its_historical_v1_row():
    selection = select_component_source_rows([_chaos_v1(), _chaos_exact()])
    assert selection["counts"]["exact_version_rows_found"] == 1
    assert selection["selected"][CHAOS_SET_ID]["id"] == CHAOS_EXACT_ROW_ID


def test_chaos_rising_v1_row_stays_ignored_even_when_it_is_the_newest():
    """The v1 row must lose on VERSION, not on age.

    If the historical v1 row were ever rebuilt it would become the newest row,
    and a loader that leans on recency would silently switch back to v1.
    """
    newer_v1 = _chaos_v1()
    newer_v1["built_at"] = "2027-01-01T00:00:00Z"
    newer_v1["updated_at"] = newer_v1["built_at"]

    selection = select_component_source_rows([newer_v1, _chaos_exact()])
    assert selection["selected"][CHAOS_SET_ID]["id"] == CHAOS_EXACT_ROW_ID


def test_chaos_rising_produces_ca7_from_its_exact_row():
    plan, _ = _plan([_chaos_v1(), _chaos_exact()])
    row = next(r for r in plan["rows"] if r["set_id"] == CHAOS_SET_ID)

    block = row["proposed_diagnostics"][COLLECTOR_APPEAL_DIAGNOSTICS_KEY]
    assert block["available"] is True
    assert block["value"] is not None
    assert block["unavailable_reason"] is None
    # The block must certify the row it was actually computed from.
    assert row["source_identity"]["component_row_id"] == CHAOS_EXACT_ROW_ID
    assert row["source_identity"]["hit_policy_version"] == EXPECTED_HIT_POLICY_VERSION


def test_chaos_rising_is_absent_from_the_missing_cohort_once_its_row_exists():
    plan, _ = _plan([_chaos_v1(), _chaos_exact()] + _other_sets())
    assert plan["unavailable_sources"] == []
    coverage = rip_consumed_coverage(plan)
    assert not any(
        entry["reason"] == MISSING_CURRENT_COMPONENT_SOURCE_ROW
        for entry in coverage["unavailable"]
    )


def test_without_its_exact_row_chaos_rising_is_reported_missing_not_served_from_v1():
    """The pre-backfill state. The gap must stay visible, never be back-filled."""
    plan, _ = _plan([_chaos_v1()])

    assert [entry["set_id"] for entry in plan["unavailable_sources"]] == [CHAOS_SET_ID]
    entry = plan["unavailable_sources"][0]
    assert entry["reason"] == MISSING_CURRENT_COMPONENT_SOURCE_ROW
    assert [v["hit_policy_version"] for v in entry["available_versions"]] == [V1]
    # And no row was planned off the v1 data.
    assert not any(row["set_id"] == CHAOS_SET_ID for row in plan["rows"])


def test_duplicate_exact_chaos_rows_fail_visibly_rather_than_picking_one():
    first = _chaos_exact()
    second = _chaos_exact()
    second["id"] = "duplicate-row"
    second["config_fingerprint"] = "cfg-different"

    selection = select_component_source_rows([first, second])
    assert selection["counts"]["sets_with_duplicate_exact_version_rows"] == 1
    assert CHAOS_SET_ID not in selection["selected"]
    assert selection["duplicates"][0]["reason"] == DUPLICATE_CURRENT_COMPONENT_SOURCE_ROW

    plan, _ = _plan([first, second])
    assert not any(row["set_id"] == CHAOS_SET_ID for row in plan["rows"])
    assert [entry["set_id"] for entry in plan["duplicate_sources"]] == [CHAOS_SET_ID]


# ---------------------------------------------------------------------------
# The backfill's effect on the approval tokens
# ---------------------------------------------------------------------------

def test_adding_the_chaos_exact_row_changes_the_source_and_payload_hashes():
    """A new source row MUST invalidate the old approval tokens.

    Chaos Rising's numeric score is identical in both rows (43.3903), so a
    manifest that hashed only set_id + built_at + score could miss this
    entirely - and an approval token that cannot see a new input is decoration.
    """
    before_plan, before_state = _plan([_chaos_v1()] + _other_sets())
    after_plan, after_state = _plan([_chaos_v1(), _chaos_exact()] + _other_sets())

    before = build_full_source_manifest(before_state, _subjects())
    after = build_full_source_manifest(after_state, _subjects())

    assert before["manifest_hash"] != after["manifest_hash"]
    assert (before["parts"]["component_rows"]["manifest_hash"]
            != after["parts"]["component_rows"]["manifest_hash"])
    assert (before_plan["normalized_payload_hash"]
            != after_plan["normalized_payload_hash"])


def test_adding_the_chaos_exact_row_does_not_change_the_formula_fingerprint():
    """Inputs moved; the RULES did not. The two identities must not be conflated."""
    before_plan, _ = _plan([_chaos_v1()] + _other_sets())
    after_plan, _ = _plan([_chaos_v1(), _chaos_exact()] + _other_sets())

    assert before_plan["expected_fingerprint"] == after_plan["expected_fingerprint"]
    assert after_plan["expected_fingerprint"] == current_fingerprint()


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------

def test_independent_runs_of_an_unchanged_source_are_byte_equivalent():
    rows = [_chaos_v1(), _chaos_exact()] + _other_sets()
    first_plan, first_state = _plan(copy.deepcopy(rows))
    second_plan, second_state = _plan(copy.deepcopy(rows))

    comparison = compare_dry_run_artifacts(
        _artifact(first_plan, first_state, generated_at="2026-07-16T06:31:19+00:00"),
        _artifact(second_plan, second_state, generated_at="2026-07-16T16:39:57+00:00"),
    )
    assert comparison["verdict"] == DETERMINISM_IDENTICAL
    assert comparison["deterministic"] is True
    assert all(check["match"] for check in comparison["checks"]["component_manifest_parts"].values())


def test_row_input_order_does_not_affect_any_hash():
    """The DB may return rows in any order; the hashes must not care."""
    rows = [_chaos_v1(), _chaos_exact()] + _other_sets()
    forward_plan, forward_state = _plan(copy.deepcopy(rows))
    reversed_plan, reversed_state = _plan(list(reversed(copy.deepcopy(rows))))

    assert (forward_plan["normalized_payload_hash"]
            == reversed_plan["normalized_payload_hash"])
    assert (build_full_source_manifest(forward_state, _subjects())["manifest_hash"]
            == build_full_source_manifest(reversed_state, _subjects())["manifest_hash"])


def test_volatile_timestamps_do_not_reach_the_approval_hashes():
    rows = [_chaos_v1(), _chaos_exact()] + _other_sets()
    plan, state = _plan(rows)

    early = _artifact(plan, state, generated_at="2020-01-01T00:00:00+00:00")
    late = _artifact(plan, state, generated_at="2030-12-31T23:59:59+00:00")
    comparison = compare_dry_run_artifacts(early, late)

    assert comparison["verdict"] == DETERMINISM_IDENTICAL
    assert comparison["volatile_fields_observed_differing"] == ["generated_at"]
    assert "generated_at" in comparison["volatile_fields_excluded_from_hashes"]


def test_a_changed_source_is_reported_as_drift_not_as_nondeterminism():
    """The distinction Phase 8.1 could not make.

    Both cases show "the payload hash differs". Only one is a bug. Collapsing
    them is how a real nondeterminism defect gets excused as "the DB changed".
    """
    before_plan, before_state = _plan([_chaos_v1()] + _other_sets())
    after_plan, after_state = _plan([_chaos_v1(), _chaos_exact()] + _other_sets())

    comparison = compare_dry_run_artifacts(
        _artifact(before_plan, before_state), _artifact(after_plan, after_state)
    )
    assert comparison["verdict"] == DETERMINISM_SOURCE_DRIFT
    assert comparison["deterministic"] is False
    assert "component_rows" in comparison["drifted_manifest_parts"]
    assert "inputs changed" in comparison["interpretation"]


def test_an_unchanged_source_with_a_moved_payload_is_reported_as_nondeterminism():
    rows = [_chaos_v1(), _chaos_exact()] + _other_sets()
    plan, state = _plan(rows)
    baseline = _artifact(plan, state)

    tampered = copy.deepcopy(baseline)
    tampered["normalized_payload_hash"] = "0" * 64  # same source, different output

    comparison = compare_dry_run_artifacts(baseline, tampered)
    assert comparison["verdict"] == DETERMINISM_NONDETERMINISTIC
    assert comparison["deterministic"] is False
    assert "blocker" in comparison["interpretation"]


def test_a_moved_formula_fingerprint_outranks_every_other_verdict():
    rows = [_chaos_v1(), _chaos_exact()] + _other_sets()
    plan, state = _plan(rows)
    baseline = _artifact(plan, state)

    tampered = copy.deepcopy(baseline)
    tampered["expected_fingerprint"] = "deadbeef"

    comparison = compare_dry_run_artifacts(baseline, tampered)
    assert comparison["verdict"] == DETERMINISM_FORMULA_CHANGED
    assert comparison["checks"]["formula_fingerprint"]["match"] is False


def test_a_reordered_write_target_list_is_not_deterministic():
    """Same rows, different emission order. The set being equal is not enough."""
    rows = [_chaos_v1(), _chaos_exact()] + _other_sets()
    plan, state = _plan(rows)
    baseline = _artifact(plan, state)

    shuffled = copy.deepcopy(baseline)
    shuffled["products"] = list(reversed(shuffled["products"]))

    # Stated, not assumed: with fewer than two targets a reversal is a no-op and
    # this test would pass while checking nothing.
    assert len([row for row in baseline["products"] if row["would_update"]]) > 1

    comparison = compare_dry_run_artifacts(baseline, shuffled)
    assert comparison["checks"]["row_ordering_and_serialization"]["match"] is False
    assert comparison["deterministic"] is False
