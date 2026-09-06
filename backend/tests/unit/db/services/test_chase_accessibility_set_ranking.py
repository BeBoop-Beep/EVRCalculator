"""Chase Accessibility SET-LEVEL ranking authority tests.

Covers the UI-4 backend acceptance criteria: unique-set ranking, duplicate
product-row invariance, run/version/mass authority gating, deterministic tie
handling, and no-N+1 batch loading.
"""

from __future__ import annotations

from backend.db.services.chase_accessibility_set_ranking import (
    compute_chase_accessibility_set_ranks,
    load_chase_accessibility_set_authority,
    project_chase_accessibility_for_set,
)
from backend.desirability.chase_accessibility import (
    CHASE_ACCESSIBILITY_VERSION,
    MIN_MAPPED_HC_MASS,
    STATUS_NO_PULL_MODEL,
    STATUS_READY,
)


def _row(set_id, accessibility, *, run_id="run-1", status=STATUS_READY,
         version=CHASE_ACCESSIBILITY_VERSION, mass=0.995, chase_depth=12.0):
    return {
        "set_id": set_id,
        "calculation_run_id": run_id,
        "accessibility": accessibility,
        "status": status,
        "version": version,
        "mapped_hc_mass": mass,
        "chase_depth": chase_depth,
    }


# A. unique-set ranking is correct
def test_ranks_unique_sets_by_descending_accessibility():
    rows = {
        "set-a": _row("set-a", 0.01),
        "set-b": _row("set-b", 0.05),
        "set-c": _row("set-c", 0.03),
    }
    ranks = compute_chase_accessibility_set_ranks(rows, ["set-a", "set-b", "set-c"])
    assert ranks["set-b"] == {"setRank": 1, "setCohortSize": 3}
    assert ranks["set-c"] == {"setRank": 2, "setCohortSize": 3}
    assert ranks["set-a"] == {"setRank": 3, "setCohortSize": 3}


# D. higher raw ranks above lower raw
def test_higher_value_ranks_above_lower_value():
    rows = {"hi": _row("hi", 0.9), "lo": _row("lo", 0.1)}
    ranks = compute_chase_accessibility_set_ranks(rows, ["hi", "lo"])
    assert ranks["hi"]["setRank"] < ranks["lo"]["setRank"]


# B & C. duplicate product rows don't alter Chase set rank / all products
# from the same set inherit identical value+rank.
def test_duplicate_products_in_same_set_do_not_distort_ranking_or_projection():
    rows = {
        "set-a": _row("set-a", 0.02),
        "set-b": _row("set-b", 0.04),
    }
    # Set A has 5 duplicated product rows, Set B has 1 - ranking must still be
    # computed over UNIQUE set_ids, never per-product-row.
    eligible_set_ids = ["set-a"] * 5 + ["set-b"]
    ranks = compute_chase_accessibility_set_ranks(rows, eligible_set_ids)
    assert ranks["set-b"] == {"setRank": 1, "setCohortSize": 2}
    assert ranks["set-a"] == {"setRank": 2, "setCohortSize": 2}

    projections = [
        project_chase_accessibility_for_set("set-a", rows_by_set_id=rows, rank_by_set_id=ranks)
        for _ in range(5)
    ]
    assert all(projection == projections[0] for projection in projections)
    assert projections[0]["setRank"] == 2
    assert projections[0]["setCohortSize"] == 2


# E. unavailable/stale Chase rows are excluded from ranking
def test_unavailable_status_excluded_from_ranking():
    rows = {
        "ready-set": _row("ready-set", 0.02),
        "no-model-set": _row("no-model-set", None, status=STATUS_NO_PULL_MODEL, mass=None),
    }
    ranks = compute_chase_accessibility_set_ranks(rows, ["ready-set", "no-model-set"])
    assert "no-model-set" not in ranks
    assert ranks["ready-set"] == {"setRank": 1, "setCohortSize": 1}


# F. wrong calculation run fails authority
def test_wrong_calculation_run_excluded():
    rows = {"set-a": _row("set-a", 0.02, run_id="run-old")}
    ranks = compute_chase_accessibility_set_ranks(
        rows, ["set-a"], expected_run_by_set={"set-a": "run-new"},
    )
    assert ranks == {}


def test_matching_calculation_run_included():
    rows = {"set-a": _row("set-a", 0.02, run_id="run-new")}
    ranks = compute_chase_accessibility_set_ranks(
        rows, ["set-a"], expected_run_by_set={"set-a": "run-new"},
    )
    assert ranks["set-a"]["setRank"] == 1


# G. mapped mass below threshold fails authority
def test_mapped_mass_below_threshold_excluded():
    rows = {"set-a": _row("set-a", 0.02, mass=MIN_MAPPED_HC_MASS - 0.01)}
    ranks = compute_chase_accessibility_set_ranks(rows, ["set-a"])
    assert ranks == {}


def test_wrong_model_version_excluded():
    rows = {"set-a": _row("set-a", 0.02, version="chase_accessibility_v0_old")}
    ranks = compute_chase_accessibility_set_ranks(rows, ["set-a"])
    assert ranks == {}


# H. deterministic tie handling - exact ties break on set_id ascending, and
# every set still gets a unique sequential rank (no shared/competition rank).
def test_exact_ties_break_deterministically_on_set_id():
    rows = {
        "set-z": _row("set-z", 0.05),
        "set-a": _row("set-a", 0.05),
        "set-m": _row("set-m", 0.05),
    }
    ranks = compute_chase_accessibility_set_ranks(rows, ["set-z", "set-a", "set-m"])
    assert ranks["set-a"]["setRank"] == 1
    assert ranks["set-m"]["setRank"] == 2
    assert ranks["set-z"]["setRank"] == 3
    assert {r["setRank"] for r in ranks.values()} == {1, 2, 3}


def test_projection_for_ineligible_set_has_null_rank_but_may_carry_value_none():
    rows = {}
    ranks = {}
    projection = project_chase_accessibility_for_set(
        "unknown-set", rows_by_set_id=rows, rank_by_set_id=ranks,
    )
    assert projection["setRank"] is None
    assert projection["setCohortSize"] is None
    assert projection["value"] is None


class _FakeResponse:
    def __init__(self, data):
        self.data = data


class _FakeQuery:
    def __init__(self, rows):
        self._rows = rows

    def select(self, *_args, **_kwargs):
        return self

    def in_(self, *_args, **_kwargs):
        return self

    def order(self, *_args, **_kwargs):
        return self

    def range(self, *_args, **_kwargs):
        return self

    def execute(self):
        return _FakeResponse(self._rows)


class _FakeClient:
    """Counts table() calls so a test can assert no N+1 reads."""

    def __init__(self, rows):
        self._rows = rows
        self.table_calls = 0

    def table(self, _name):
        self.table_calls += 1
        return _FakeQuery(self._rows)


# J. no N+1 reads - one query for an arbitrarily large cohort.
def test_batch_authority_load_issues_exactly_one_query_for_whole_cohort():
    rows = [_row(f"set-{i}", 0.01 * i) for i in range(1, 26)]
    client = _FakeClient(rows)
    result = load_chase_accessibility_set_authority(
        set_ids=[row["set_id"] for row in rows], client=client,
    )
    assert client.table_calls == 1
    assert len(result["rankBySetId"]) == 25
    assert result["rankBySetId"][f"set-25"]["setRank"] == 1  # largest value ranks #1
