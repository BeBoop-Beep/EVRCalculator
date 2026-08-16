"""Stage 1.6: deferred Collector Appeal, batch finalization, comparison scope.

The behaviours pinned here are architectural, not numeric. No formula is
exercised for its value; what is exercised is WHERE work happens (once, in the
batch) versus where it must not happen (in every per-set simulation process),
and WHICH rows a finalization is allowed to touch.
"""

from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

from backend.db.repositories import sealed_product_results_repository as repo
from backend.db.services import sealed_product_rip_finalization_service as finalizer
from backend.db.services import sealed_product_rip_service as service
from backend.db.services.opening_simulation_gate import (
    OpeningSetSimulationStatus,
    OpeningSimulationFreshnessReport,
    STATUS_CURRENT,
    STATUS_STALE,
)
from backend.desirability.collector_appeal import COLLECTOR_APPEAL_V4_VERSION
from backend.desirability.scoring_config import OVERALL_RIP_V8_VERSION
from backend.domain.pokemon import sealed_product_comparison_scope as scope

REPO_ROOT = Path(__file__).resolve().parents[4]
RUNS = 20_000


def _pack_vector(n: int = RUNS) -> np.ndarray:
    rng = np.random.default_rng(20260815)
    base = rng.lognormal(mean=0.5, sigma=0.9, size=n)
    hits = rng.random(n) < 0.01
    base[hits] += rng.lognormal(mean=3.5, sigma=0.8, size=int(hits.sum()))
    return np.round(base, 4)


def _snapshot(products):
    return {"products": products}


_PRODUCTS = [
    {
        "sealedProductId": "101",
        "name": "A Booster Box",
        "productFamily": "booster_box",
        "currentPrice": 140.0,
    },
    {
        "sealedProductId": "102",
        "name": "A Booster Bundle",
        "productFamily": "booster_bundle",
        "currentPrice": 26.0,
    },
]


def _run_stage1(captured=None, **overrides):
    def _persist(rows):
        if captured is not None:
            captured.extend(rows)
        return rows

    kwargs = {
        "sim_results": {"distribution": _pack_vector()},
        "set_id": "set-uuid",
        "canonical_set_key": "setA",
        "calculation_run_id": "run-uuid",
        "read_snapshot_fn": lambda _sid: _snapshot(_PRODUCTS),
        "persist_fn": _persist,
    }
    kwargs.update(overrides)
    return service.run_stage1_sealed_product_rip(**kwargs)


# ---------------------------------------------------------------------------
# 1-3. Per-set Stage 1 no longer builds Collector Appeal
# ---------------------------------------------------------------------------

def test_per_set_stage1_never_builds_the_collector_appeal_bundle():
    with patch(
        "backend.db.services.collector_appeal_service.get_collector_appeal_bundle"
    ) as bundle, patch(
        "backend.db.services.collector_appeal_service.get_collector_appeal"
    ) as single:
        summary = _run_stage1()

    assert bundle.call_count == 0
    assert single.call_count == 0
    assert summary["status"] == "ok"


def test_per_set_stage1_persists_full_financial_rip_without_collector_appeal():
    captured = []
    _run_stage1(captured=captured)

    assert len(captured) == 2
    for row in captured:
        assert row["financial_rip_v3_score"] is not None
        assert row["financial_rip_v3_rankable"] is True
        assert isinstance(row["financial_rip_v3_payload"], dict)
        assert row["expected_value"] is not None
        assert row["product_market_cost"] > 0
        # Appeal-dependent half: explicitly absent, never a placeholder.
        assert row["collector_appeal_score"] is None
        assert row["collector_appeal_version"] is None
        assert row["overall_rip_score"] is None
        assert row["overall_rip_rankable"] is False
        # The canonical unavailable Overall RIP object, not NULL and not a guess.
        assert row["overall_rip_version"] == OVERALL_RIP_V8_VERSION
        assert row["overall_rip_payload"]["status"] == "unavailable_missing_input"
        assert "collector_appeal_v4" in row["overall_rip_payload"]["missingInputs"]


def test_pending_enrichment_state_is_explicit_and_a_named_constant():
    summary = _run_stage1()
    assert summary["collectorAppealStatus"] == service.COLLECTOR_APPEAL_STATUS_PENDING
    assert service.COLLECTOR_APPEAL_STATUS_PENDING == "pending_batch_enrichment"
    assert summary["collectorAppealAvailable"] is False


def test_an_explicit_collector_appeal_fn_is_still_honoured():
    """Deferral is the DEFAULT, not a removal of the capability."""
    appeal = {
        "score": 62.0,
        "version": COLLECTOR_APPEAL_V4_VERSION,
        "available": True,
        "status": service.COLLECTOR_APPEAL_STATUS_AVAILABLE,
        "reason": None,
    }
    captured = []
    summary = _run_stage1(captured=captured, collector_appeal_fn=lambda _sid: appeal)
    assert summary["collectorAppealStatus"] == service.COLLECTOR_APPEAL_STATUS_AVAILABLE
    assert captured[0]["collector_appeal_score"] == 62.0
    assert captured[0]["overall_rip_score"] is not None


# ---------------------------------------------------------------------------
# Finalizer harness
# ---------------------------------------------------------------------------

def _status(key, set_id, run_id, status=STATUS_CURRENT):
    return OpeningSetSimulationStatus(
        canonical_key=key,
        set_id=set_id,
        set_name=key,
        status=status,
        calculation_run_id=run_id,
    )


def _row(row_id, set_id, run_id, *, financial=71.0, family="booster_box", pack_count=36):
    return {
        "id": row_id,
        "calculation_run_id": run_id,
        "sealed_product_id": f"sku-{row_id}",
        "set_id": set_id,
        "product_family": family,
        "pack_count": pack_count,
        "financial_rip_v3_score": financial,
        "financial_rip_v3_rankable": True,
        "collector_appeal_score": None,
        "overall_rip_score": None,
    }


def _bundle(payload_by_set):
    return {
        "payloads": {
            set_id: {"collectorAppeal": {"score": score, "version": COLLECTOR_APPEAL_V4_VERSION}}
            if score is not None
            else {"collectorAppeal": {"score": None, "version": None}}
            for set_id, score in payload_by_set.items()
        },
        "identity": {"collectorAppealVersion": COLLECTOR_APPEAL_V4_VERSION},
    }


class _Recorder:
    """Counts bundle builds and records every enrichment write."""

    def __init__(self, bundle):
        self._bundle = bundle
        self.bundle_calls = 0
        self.writes = []

    def bundle_fn(self, **_kwargs):
        self.bundle_calls += 1
        return self._bundle

    def update_fn(self, row_id, values):
        # Mirrors the real repository's refusal to write anything else.
        unknown = sorted(set(values) - set(repo.ENRICHMENT_FIELDS))
        assert not unknown, unknown
        self.writes.append((row_id, values))
        return [{"id": row_id}]


def _finalize(statuses, rows, bundle, **overrides):
    recorder = _Recorder(bundle)
    report_obj = OpeningSimulationFreshnessReport(market_date="2026-08-15", statuses=statuses)
    kwargs = {
        "market_date": "2026-08-15",
        "bundle_fn": recorder.bundle_fn,
        "read_rows_fn": lambda run_ids: [r for r in rows if r["calculation_run_id"] in set(run_ids)],
        "update_fn": recorder.update_fn,
    }
    kwargs.update(overrides)
    with patch.object(finalizer, "evaluate_opening_simulation_freshness", return_value=report_obj):
        report = finalizer.finalize_sealed_product_rip(object(), **kwargs)
    return report, recorder


# ---------------------------------------------------------------------------
# 4-8. Batch finalization behaviour
# ---------------------------------------------------------------------------

def test_finalizer_builds_the_collector_appeal_bundle_exactly_once_for_many_sets():
    statuses = [_status(f"set{i}", f"sid-{i}", f"run-{i}") for i in range(5)]
    rows = [_row(f"r{i}", f"sid-{i}", f"run-{i}") for i in range(5)]
    report, recorder = _finalize(statuses, rows, _bundle({f"sid-{i}": 50.0 + i for i in range(5)}))

    assert recorder.bundle_calls == 1
    assert report["collectorAppealBundleBuilds"] == 1
    assert report["rowsFinalized"] == 5
    assert report["setCount"] == 5


def test_multiple_rows_from_one_set_share_one_collector_appeal_score_and_version():
    statuses = [_status("setA", "sid-a", "run-a")]
    rows = [
        _row("r1", "sid-a", "run-a", family="booster_box", pack_count=36),
        _row("r2", "sid-a", "run-a", family="booster_bundle", pack_count=6, financial=64.0),
        _row("r3", "sid-a", "run-a", family="sleeved_booster_pack", pack_count=1, financial=58.0),
    ]
    report, recorder = _finalize(statuses, rows, _bundle({"sid-a": 63.5}))

    assert report["rowsFinalized"] == 3
    assert {v["collector_appeal_score"] for _id, v in recorder.writes} == {63.5}
    assert {v["collector_appeal_version"] for _id, v in recorder.writes} == {COLLECTOR_APPEAL_V4_VERSION}
    # Overall still differs per row, because Financial RIP does.
    assert len({v["overall_rip_score"] for _id, v in recorder.writes}) == 3


def test_overall_rip_uses_the_canonical_v8_helper():
    from backend.desirability.weighted_rip import compute_overall_rip_v8

    statuses = [_status("setA", "sid-a", "run-a")]
    rows = [_row("r1", "sid-a", "run-a", financial=71.0)]
    _report, recorder = _finalize(statuses, rows, _bundle({"sid-a": 63.5}))

    expected = compute_overall_rip_v8(71.0, 63.5)
    _row_id, written = recorder.writes[0]
    assert written["overall_rip_score"] == expected["score"]
    assert written["overall_rip_version"] == expected["version"] == OVERALL_RIP_V8_VERSION
    assert written["overall_rip_rankable"] is True
    assert written["overall_rip_payload"] == expected


def test_one_set_without_collector_appeal_does_not_fail_the_cohort():
    statuses = [_status("setA", "sid-a", "run-a"), _status("setB", "sid-b", "run-b")]
    rows = [_row("r1", "sid-a", "run-a"), _row("r2", "sid-b", "run-b")]
    report, recorder = _finalize(statuses, rows, _bundle({"sid-a": 63.5, "sid-b": None}))

    assert report["status"] == "ok"
    assert report["rowsFinalized"] == 2
    assert report["rowsCollectorAppealUnavailable"] == 1

    written = dict(recorder.writes)
    assert written["r1"]["overall_rip_rankable"] is True
    # The set with no appeal: Overall unavailable, never zero, Financial untouched.
    assert written["r2"]["collector_appeal_score"] is None
    assert written["r2"]["overall_rip_score"] is None
    assert written["r2"]["overall_rip_rankable"] is False
    assert written["r2"]["overall_rip_payload"]["status"] == "unavailable_missing_input"
    assert "financial_rip_v3_score" not in written["r2"]


# ---------------------------------------------------------------------------
# 9-12. Cohort boundary, isolation, idempotency
# ---------------------------------------------------------------------------

def test_only_the_current_calculation_run_cohort_is_read_and_updated():
    statuses = [_status("setA", "sid-a", "run-today"), _status("setB", "sid-b", "run-b", status=STATUS_STALE)]
    rows = [
        _row("today", "sid-a", "run-today"),
        _row("historical", "sid-a", "run-last-week"),
        _row("stale-set", "sid-b", "run-b"),
    ]
    requested = {}

    def _read(run_ids):
        requested["ids"] = list(run_ids)
        return [r for r in rows if r["calculation_run_id"] in set(run_ids)]

    report, recorder = _finalize(
        statuses,
        rows,
        _bundle({"sid-a": 63.5, "sid-b": 40.0}),
        read_rows_fn=_read,
        require_verified_cohort=False,
    )

    # A stale set contributes no run id, so its rows are never even read.
    assert requested["ids"] == ["run-today"]
    assert [row_id for row_id, _v in recorder.writes] == ["today"]
    assert report["rowsFinalized"] == 1


def test_historical_product_rows_are_untouched():
    statuses = [_status("setA", "sid-a", "run-today")]
    rows = [_row("today", "sid-a", "run-today"), _row("historical", "sid-a", "run-2025")]
    # Read deliberately over-returns to prove the row loop itself re-checks the run.
    report, recorder = _finalize(statuses, rows, _bundle({"sid-a": 63.5}), read_rows_fn=lambda _ids: rows)

    assert [row_id for row_id, _v in recorder.writes] == ["today"]
    assert report["rowsSkipped"] == 1
    assert report["skipped"][0]["reason"] == "row_outside_current_cohort"


def test_an_unverified_cohort_is_refused_by_default():
    statuses = [_status("setA", "sid-a", "run-a"), _status("setB", "sid-b", None, status=STATUS_STALE)]
    report, recorder = _finalize(statuses, [_row("r1", "sid-a", "run-a")], _bundle({"sid-a": 63.5}))

    assert report["status"] == finalizer.STATUS_CANNOT_START
    assert recorder.writes == []
    assert recorder.bundle_calls == 0


def test_finalization_is_idempotent():
    statuses = [_status("setA", "sid-a", "run-a")]
    rows = [_row("r1", "sid-a", "run-a"), _row("r2", "sid-a", "run-a", financial=64.0)]
    bundle = _bundle({"sid-a": 63.5})

    first_report, first = _finalize(statuses, rows, bundle)
    second_report, second = _finalize(statuses, rows, bundle)

    assert first.writes == second.writes
    assert first_report["rowsFinalized"] == second_report["rowsFinalized"] == 2
    assert len(second.writes) == 2  # no duplicated rows, no growth


def test_finalization_regenerates_no_distributions_and_runs_no_simulation():
    statuses = [_status("setA", "sid-a", "run-a")]
    rows = [_row("r1", "sid-a", "run-a")]
    with patch(
        "backend.calculations.evr.sealed_product_distribution.build_stage1_product_distributions"
    ) as build, patch(
        "backend.calculations.evr.financial_rip_v3.build_financial_rip_v3"
    ) as financial:
        _finalize(statuses, rows, _bundle({"sid-a": 63.5}))
    assert build.call_count == 0
    assert financial.call_count == 0


def test_enrichment_write_refuses_any_non_enrichment_column():
    for forbidden in (
        "financial_rip_v3_score",
        "product_market_cost",
        "calculation_run_id",
        "sealed_product_id",
        "pack_count",
        "expected_value",
        "composition_version",
    ):
        assert forbidden not in repo.ENRICHMENT_FIELDS
        with pytest.raises(ValueError):
            repo.update_sealed_product_enrichment("row-1", {forbidden: 1})


# ---------------------------------------------------------------------------
# 13-16. Comparison scope contract
# ---------------------------------------------------------------------------

def test_comparison_scope_is_within_product_family_only():
    assert scope.SEALED_PRODUCT_COMPARISON_SCOPE == "within_product_family_only"
    contract = scope.sealed_product_comparison_scope_contract()
    assert contract["comparisonScope"] == "within_product_family_only"
    assert _run_stage1()["comparisonScope"] == "within_product_family_only"


def test_cross_format_comparison_is_false_everywhere_it_is_published():
    assert scope.SEALED_PRODUCT_CROSS_FORMAT_COMPARABLE is False
    assert scope.sealed_product_comparison_scope_contract()["crossFormatComparable"] is False
    assert _run_stage1()["crossFormatComparable"] is False

    statuses = [_status("setA", "sid-a", "run-a")]
    report, _rec = _finalize(statuses, [_row("r1", "sid-a", "run-a")], _bundle({"sid-a": 63.5}))
    assert report["crossFormatComparable"] is False
    assert report["comparisonScope"] == "within_product_family_only"


@pytest.mark.parametrize("family", ["booster_box", "booster_bundle", "sleeved_booster_pack"])
def test_same_family_comparison_is_allowed(family):
    assert scope.may_compare_products(family, family) is True


@pytest.mark.parametrize(
    "left,right",
    [
        ("booster_box", "booster_bundle"),
        ("booster_box", "sleeved_booster_pack"),
        ("booster_bundle", "sleeved_booster_pack"),
        ("booster_box", "elite_trainer_box"),
    ],
)
def test_cross_format_comparison_is_not_allowed(left, right):
    assert scope.may_compare_products(left, right) is False


def test_comparison_scope_does_not_overload_financial_rip_rankable():
    """Two different concepts, two different fields."""
    captured = []
    _run_stage1(captured=captured)
    # Rankable stays a property of the Financial RIP CALCULATION and is true here
    # even though the row is not cross-format comparable.
    assert captured[0]["financial_rip_v3_rankable"] is True
    assert scope.SEALED_PRODUCT_CROSS_FORMAT_COMPARABLE is False
    assert "financial_rip_v3_rankable" not in scope.sealed_product_comparison_scope_contract()


def test_the_family_scoped_ranking_helper_still_exists_and_no_all_family_one_does():
    assert callable(repo.get_latest_sealed_product_result_for_family)
    public = [name for name in dir(repo) if not name.startswith("_")]
    # Nothing that ranks across families. `get_latest_sealed_product_results_for_set`
    # returns a set's rows unranked; the only ranking helper is family-scoped.
    assert [name for name in public if "rank" in name.lower()] == []
    assert "get_best_sealed_product_across_families" not in public
    assert "get_sealed_product_leaderboard" not in public


# ---------------------------------------------------------------------------
# 17-19. Protected surfaces are unchanged on this branch
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "relative_path",
    [
        "backend/calculations/evr/financial_rip_v3.py",
        "backend/calculations/evr/financial_rip_v3_config.py",
        "backend/calculations/evr/sealed_product_distribution.py",
        "backend/desirability/collector_appeal.py",
        "backend/domain/pokemon/sealed_product_composition.py",
        "backend/domain/pokemon/sealed_product_classifier.py",
    ],
)
def test_protected_scoring_files_are_unmodified_since_stage_1_5(relative_path):
    """Stage 1.6 changes WHERE work happens, never what any formula computes."""
    import subprocess

    completed = subprocess.run(
        ["git", "diff", "--name-only", "4362838b8ff7c68d29fe00fad193522a17b62511", "--", relative_path],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        pytest.skip(f"git unavailable or revision missing: {completed.stderr.strip()}")
    assert completed.stdout.strip() == "", f"{relative_path} was modified"


def test_simulations_package_is_unmodified_since_stage_1_5():
    import subprocess

    completed = subprocess.run(
        ["git", "diff", "--name-only", "4362838b8ff7c68d29fe00fad193522a17b62511", "--", "backend/simulations"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        pytest.skip(f"git unavailable or revision missing: {completed.stderr.strip()}")
    assert completed.stdout.strip() == ""
