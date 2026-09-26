"""Rankings writer is release-driven: V12 unchanged, V14 truthful, mixed authority rejected."""
import copy
import json

import pytest

from backend.db.services import explore_rip_statistics_service as service
from backend.db.services import rankings_publication_lifecycle as lifecycle
from backend.db.services import rankings_release_authority as ra
from backend.db.services import rip_release as rr
from backend.desirability import scoring_config as sc
from backend.tests.unit.db.services.test_explore_rip_statistics_service import (
    _Client, _build_handlers, _stub_collector_appeal_bundle,
)

V12 = rr.static_canonical_bundle()
V14 = next(b for b in rr.RELEASES.values() if b.requires_v5_schema)


def _build(monkeypatch, **kwargs):
    monkeypatch.setattr(service, "service_read_client", _Client(_build_handlers()))
    _stub_collector_appeal_bundle(monkeypatch)
    monkeypatch.setattr(service, "build_rip_interpretation", lambda summary_row: {})
    return service.get_rip_statistics_targets_payload(limit="150", **kwargs)


def _stable(payload):
    """Deterministic semantic content: drop wall-clock stamps, keep everything else."""
    text = json.dumps(payload, sort_keys=True, default=str)
    return json.loads(text)


def _strip_time(obj):
    if isinstance(obj, dict):
        return {k: _strip_time(v) for k, v in obj.items()
                if k not in {"generatedAt", "builtAt", "generated_at", "elapsedMs", "timings", "totalMs"}}
    if isinstance(obj, list):
        return [_strip_time(v) for v in obj]
    return obj


def test_v12_release_output_is_identical_to_the_pre_change_default(monkeypatch):
    default = _strip_time(_stable(_build(monkeypatch)))
    explicit = _strip_time(_stable(_build(monkeypatch, release=V12)))
    assert default == explicit
    cfg = default["meta"]["ripWeightsConfig"]
    assert cfg["overallRip"]["version"] == sc.CANONICAL_OVERALL_RIP_VERSION
    assert cfg["financialRip"]["version"] == sc.CANONICAL_FINANCIAL_RIP_VERSION
    assert cfg["publicContract"]["version"] == sc.canonical_public_rip_contract_version()
    assert all("overallRipV14" not in t and "financialRipV5" not in t and "publicRipContractV12" not in t
               for t in default["targets"])


def test_v14_release_builds_truthful_v14_identity_and_keeps_v12_blocks_untouched(monkeypatch):
    v12 = _strip_time(_stable(_build(monkeypatch)))
    v14 = _strip_time(_stable(_build(monkeypatch, release=V14, set_authority_rows_fn=lambda client, runs: {})))
    cfg = v14["meta"]["ripWeightsConfig"]
    assert cfg["overallRip"]["version"] == V14.overall_version == sc.OVERALL_RIP_V14_VERSION
    assert cfg["financialRip"]["version"] == V14.financial_version
    assert cfg["publicContract"]["version"] == "public_rip_contract_v12"
    assert cfg["overallRip"]["weights"] == dict(sc.OVERALL_RIP_V14_WEIGHTS)
    by_id = {t["target_id"]: t for t in v12["targets"]}
    for t in v14["targets"]:
        # V14 lives under its own keys; V4 / V12 blocks and the V11 contract are byte-for-byte the V12 build's
        assert t["financialRipV4"] == by_id[t["target_id"]]["financialRipV4"]
        assert t["overallRipV12"] == by_id[t["target_id"]]["overallRipV12"]
        assert "financialRipV5" in t and "overallRipV14" in t and "publicRipContractV12" in t
        # no authority row -> unavailable; nothing falls back to V4 / V12
        assert t["financialRipV5"]["score"] is None and t["overallRipV14"]["score"] is None
        assert t["overallRipV14"].get("version") != sc.OVERALL_RIP_V12_VERSION
        assert t["publicRipContractV12"]["contractVersion"] == "public_rip_contract_v12"


def test_v14_ranking_only_runs_for_the_v14_release():
    rows = [{"target_id": f"s{i}", "financialRipV5": {"score": 50.0 + i}, "overallRipV14": {"score": 60.0 + i, "rankable": True},
             "overallRipV12": {"score": 10.0 + i}} for i in range(3)]
    v14_rows = copy.deepcopy(rows)
    service._rank_within_cohort(v14_rows, cohort_size=3, release=V14)
    assert [r["overallRipV14"]["rank"] for r in v14_rows] == [3, 2, 1] and v14_rows[2]["financialRipV5"]["rank"] == 1
    assert "leaderNormalizedScore" in v14_rows[0]["overallRipV14"]
    v12_rows = copy.deepcopy(rows)
    service._rank_within_cohort(v12_rows, cohort_size=3, release=V12)
    assert "rank" not in v12_rows[0]["overallRipV14"] and "rank" not in v12_rows[0]["financialRipV5"]


# ------------------------------------------------------------------ snapshot release authority

def _snapshot(release, *, ranked=True):
    fv, ov, cv = release.financial_version, release.overall_version, release.public_contract_version
    fin_key, ov_key = release.financial_target_key, release.overall_target_key
    return {
        "meta": {"ripWeightsConfig": {"financialRip": {"version": fv}, "overallRip": {"version": ov},
                                       "publicContract": {"version": cv}}},
        "targets": [{"target_id": "s1", "calculation_run_id": "run-1",
                     ov_key: {"score": 60.0, "rank": 1 if ranked else None, "version": ov},
                     fin_key: {"score": 55.0, "status": "ready", "version": fv,
                               "source": {"calculationRunId": "run-1"}}}],
    }


def test_matching_snapshots_are_accepted_for_their_own_release():
    assert ra.snapshot_release_problems(_snapshot(V12), V12) == []
    assert ra.snapshot_release_problems(_snapshot(V14), V14) == []


def test_stale_v12_snapshot_is_rejected_under_v14_and_v14_snapshot_under_v12():
    assert any("stale_or_foreign_snapshot" in p for p in ra.snapshot_release_problems(_snapshot(V12), V14))
    assert any("stale_or_foreign_snapshot" in p for p in ra.snapshot_release_problems(_snapshot(V14), V12))


def test_rollback_makes_the_untouched_historical_v12_snapshot_current_again():
    v12_snapshot = _snapshot(V12)
    before = copy.deepcopy(v12_snapshot)
    assert ra.snapshot_release_problems(v12_snapshot, V14) != []      # V14 selected: stale
    assert ra.snapshot_release_problems(v12_snapshot, V12) == []      # rollback: valid, with no rewrite
    assert v12_snapshot == before


@pytest.mark.parametrize("mutate,expect", [
    (lambda s: s["meta"]["ripWeightsConfig"]["financialRip"].update(version=sc.FINANCIAL_RIP_V4_VERSION), "financial"),
    (lambda s: s["meta"]["ripWeightsConfig"]["publicContract"].update(version="public_rip_contract_v11"), "contract"),
    (lambda s: s["meta"]["ripWeightsConfig"]["overallRip"].update(version=sc.OVERALL_RIP_V12_VERSION), "overall"),
    (lambda s: s["targets"][0]["financialRipV5"].update(version=sc.FINANCIAL_RIP_V4_VERSION), "financialRipV5.version"),
    (lambda s: s["targets"][0]["financialRipV5"]["source"].update(calculationRunId="wrong-run"), "built from run"),
    (lambda s: s["targets"][0]["financialRipV5"].update(status="unavailable"), "without a ready"),
    (lambda s: s["targets"][0].update(overallRipV12={"version": sc.OVERALL_RIP_V14_VERSION}), "value under overallRipV12"),
    (lambda s: s["targets"][0].update(financialRipV4={"version": V14.financial_version}), "value under financialRipV4"),
])
def test_mixed_authority_is_rejected_under_v14(mutate, expect):
    snap = _snapshot(V14)
    mutate(snap)
    problems = ra.snapshot_release_problems(snap, V14)
    assert problems and any(expect in p for p in problems), problems


def test_cohort_fingerprint_mismatch_and_unknown_release_fail_closed():
    snap = _snapshot(V14)
    snap["meta"]["snapshot"] = {"cohortFingerprint": "abc"}
    assert any("cohort_fingerprint_mismatch" in p for p in ra.snapshot_release_problems(snap, V14, expected_cohort_fingerprint="xyz"))
    assert ra.snapshot_release_problems(snap, None)[0].startswith("unknown_release")


@pytest.mark.parametrize("observed", [
    {"overall": V14.overall_version, "financial": sc.FINANCIAL_RIP_V4_VERSION},                       # V14 + Financial V4
    {"overall": V14.overall_version, "ranking": V12.ranking_method_version},                          # V14 + Ranking V1
    {"overall": V14.overall_version, "contract": "public_rip_contract_v11"},                          # V14 + Contract V11
    {"overall": V12.overall_version, "ranking": V14.ranking_method_version},                          # Ranking V2 + Overall V12
    {"overall": V14.overall_version, "bestOpen": list(V12.best_open_method_versions)},                # V14 + Best-Open V1/V2
    {"overall": "overall_rip_v99"},                                                                   # unknown release
])
def test_observed_bundle_mixes_are_rejected(observed):
    assert ra.observed_bundle_problems(observed)


def test_coherent_observed_bundles_pass():
    for b in (V12, V14):
        assert ra.observed_bundle_problems({"overall": b.overall_version, "financial": b.financial_version,
                                            "contract": b.public_contract_version, "ranking": b.ranking_method_version,
                                            "bestOpen": list(b.best_open_method_versions)}) == []


# ------------------------------------------------------------------ lifecycle

def test_lifecycle_helpers_are_release_selected_and_default_to_canonical():
    assert lifecycle._overall_target_key() == "overallRipV12" == lifecycle._overall_target_key(V12)
    assert lifecycle._overall_target_key(V14) == "overallRipV14"
    assert lifecycle._publication_identity()["overallRipVersion"] == sc.CANONICAL_OVERALL_RIP_VERSION
    assert lifecycle._publication_identity(V14)["overallRipVersion"] == V14.overall_version
    assert lifecycle._publication_identity(V14)["financialRipVersion"] == V14.financial_version


def test_readiness_blocks_a_foreign_generation_snapshot_under_the_selected_release():
    row = {"ranking_payload_json": _snapshot(V12)}
    report = lifecycle.evaluate_rankings_publication_readiness(row, {"market_date": "2026-09-15", "eligible_cohort_count": 1},
                                                               release=V14)
    assert report.status == lifecycle.BLOCKED_RELEASE_AUTHORITY_MISMATCH
    assert any("stale_or_foreign_snapshot" in p for p in report.problems)
