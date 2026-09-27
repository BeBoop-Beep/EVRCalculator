"""Exact-artifact Financial RIP V5 finalization: lineage, reuse and fail-closed behavior."""
from types import SimpleNamespace

import numpy as np
import pytest

from backend.calculations.evr.financial_rip_v4 import build_financial_rip_v4
from backend.calculations.evr.financial_rip_v5 import build_financial_rip_v5, validate_financial_rip_v5_payload
from backend.calculations.evr.financial_rip_v5_config import FINANCIAL_RIP_V5_VERSION
from backend.calculations.evr.guaranteed_component_value import add_guaranteed_components
from backend.calculations.evr.sealed_product_distribution import build_stage1_product_distributions
from backend.db.repositories.sealed_product_results_repository import FINANCIAL_RIP_V5_FIELDS
from backend.db.services import sealed_product_financial_v5_finalization_service as svc
from backend.db.services.pack_outcome_artifact_service import (
    PackOutcomeArtifactCorrupt, PackOutcomeArtifactUnavailable,
)

N = 20001
RUN_A, RUN_B = "run-a", "run-b"
SET_A, SET_B = "set-a", "set-b"
HASH = {RUN_A: "hash-a", RUN_B: "hash-b"}
KEY = {RUN_A: "key-a", RUN_B: "key-b"}
ALL_COUNTS = [1, 9, 10, 36]  # Stage 1 requests the run's WHOLE count set in one bootstrap call
# (name, family, pack_count, guaranteed, cost)
SKUS = [("Loose Pack", "loose_booster_pack", 1, 0.0, 4.0),
        ("ETB", "elite_trainer_box", 9, 12.5, 60.0),
        ("ETB variant", "elite_trainer_box", 9, 12.5, 62.0),   # same K as ETB: must share one distribution
        ("PC ETB", "pokemon_center_elite_trainer_box", 10, 30.0, 130.0),
        ("Booster Box", "booster_box", 36, 0.0, 150.0)]


def _outcomes(seed):
    rng = np.random.default_rng(seed)
    return rng.choice([0.05, 0.1, 0.3, 1.0, 3.0, 25.0, 200.0], size=N, p=[.3, .3, .2, .1, .07, .02, .01])


OUTCOMES = {RUN_A: _outcomes(1), RUN_B: _outcomes(2)}


def _row(run_id, set_id, idx, sku, *, key=None, store_v4=True):
    name, family, k, g, cost = sku
    built = build_stage1_product_distributions(OUTCOMES[run_id], pack_counts=ALL_COUNTS,
                                               canonical_set_key=key or KEY[run_id], run_fingerprint=HASH[run_id])
    vec = built["distributions"][k]
    if g:
        vec = add_guaranteed_components(vec, g)
    row = dict(id=f"{run_id}-{idx}", calculation_run_id=run_id, set_id=set_id, sealed_product_id=f"{run_id}-p{idx}",
               product_name=name, product_family=family, pack_count=k, random_pack_count=k,
               guaranteed_component_market_value=g or None, accessory_value_included=False,
               product_market_cost=cost, simulation_count=N, expected_value=float(vec.mean()),
               median_value=float(np.median(vec)), p05_value=float(np.percentile(vec, 5)),
               p95_value=float(np.percentile(vec, 95)), p99_value=float(np.percentile(vec, 99)))
    row["financial_rip_v4_score"] = build_financial_rip_v4(vec, cost)["score"] if store_v4 else None
    return row


def _rows(**kw):
    rows = []
    for run_id, set_id in ((RUN_A, SET_A), (RUN_B, SET_B)):
        rows += [_row(run_id, set_id, i, s, **kw) for i, s in enumerate(SKUS)]
    return rows


class Harness:
    def __init__(self, rows=None, loader=None, cohort_ok=True):
        self.rows = rows if rows is not None else _rows()
        self.loads, self.writes, self.builds = [], [], []
        self.loader = loader
        self.cohort_ok = cohort_ok

    def cohort(self, client, **_):
        return {"error": None, "marketDate": "2026-09-14", "verificationPassed": self.cohort_ok,
                "runIdBySetId": {SET_A: RUN_A, SET_B: RUN_B}, "setKeyByRunId": dict(KEY)}

    def load(self, client, run_id):
        self.loads.append(run_id)
        if self.loader:
            return self.loader(run_id)
        return SimpleNamespace(metadata={"calculation_run_id": run_id}, outcomes=OUTCOMES[run_id])

    def run(self, monkeypatch, **kw):
        real = svc.build_stage1_product_distributions

        def spy(*a, **k):
            self.builds.append(list(k["pack_counts"]))
            return real(*a, **k)
        monkeypatch.setattr(svc, "build_stage1_product_distributions", spy)
        return svc.finalize_financial_rip_v5(
            None, market_date="2026-09-14", resolve_cohort_fn=self.cohort,
            read_rows_fn=lambda runs: [r for r in self.rows if r["calculation_run_id"] in runs],
            artifact_loader_fn=self.load, run_hash_fn=lambda c, runs: {r: HASH[r] for r in runs},
            write_fn=lambda rid, fields: self.writes.append((rid, fields)), **kw)


def test_artifact_loaded_once_per_run_and_each_pack_count_built_once(monkeypatch):
    h = Harness()
    report = h.run(monkeypatch)
    assert sorted(h.loads) == [RUN_A, RUN_B] and report["artifactLoads"] == 2
    assert report["distributionBuilds"] == 2 and len(h.builds) == 2
    assert all(b == [1, 9, 10, 36] for b in h.builds)  # distinct counts only: ETB + variant share K=9
    assert report["rowsReady"] == len(SKUS) * 2 and report["cohortComplete"] is True


def test_v5_equals_direct_production_scorer_and_payload_validates_and_reconstructs(monkeypatch):
    h = Harness()
    h.run(monkeypatch)
    by_id = dict(h.writes)
    for row in h.rows:
        name, _, k, g, cost = next(s for s in SKUS if s[0] == row["product_name"])
        vec = build_stage1_product_distributions(OUTCOMES[row["calculation_run_id"]], pack_counts=ALL_COUNTS,
                                                 canonical_set_key=KEY[row["calculation_run_id"]],
                                                 run_fingerprint=HASH[row["calculation_run_id"]])["distributions"][k]
        if g:
            vec = add_guaranteed_components(vec, g)
        direct = build_financial_rip_v5(vec, cost)
        fields = by_id[row["id"]]
        assert fields["financial_rip_v5_score"] == direct["score"]
        assert fields["financial_rip_v5_status"] == "ready" and fields["financial_rip_v5_rankable"] is True
        assert fields["financial_rip_v5_version"] == FINANCIAL_RIP_V5_VERSION
        assert validate_financial_rip_v5_payload(fields["financial_rip_v5_payload"])[0] is True
        assert fields["financial_rip_v5_payload"]["audit"]["v4LineageParity"] == "exact"


def test_only_v5_columns_are_written_v4_columns_untouched(monkeypatch):
    h = Harness()
    h.run(monkeypatch)
    assert h.writes and all(set(f) <= set(FINANCIAL_RIP_V5_FIELDS) for _, f in h.writes)
    assert not any("v4" in k or "v12" in k or "v10" in k for _, f in h.writes for k in f)


def test_guaranteed_offset_is_deterministic_and_shared_distribution_not_resampled(monkeypatch):
    first = Harness(); first.run(monkeypatch)
    second = Harness(); second.run(monkeypatch)
    assert dict(first.writes) == dict(second.writes)
    etb = {r["product_name"]: dict(first.writes)[r["id"]] for r in first.rows if r["calculation_run_id"] == RUN_A}
    # same K, same guaranteed offset, different cost -> same random vector, different score
    assert etb["ETB"]["financial_rip_v5_score"] != etb["ETB variant"]["financial_rip_v5_score"]
    assert etb["ETB"]["financial_rip_v5_payload"]["components"]["shortfall_resilience"]["raw"]["outcomeCount"] == N


@pytest.mark.parametrize("exc,reason", [(PackOutcomeArtifactUnavailable("none"), "artifact_unavailable"),
                                        (PackOutcomeArtifactCorrupt("bad sha"), "artifact_corrupt")])
def test_missing_or_corrupt_artifact_fails_closed_and_never_fabricates(monkeypatch, exc, reason):
    def loader(run_id):
        if run_id == RUN_B:
            raise exc
        return SimpleNamespace(metadata={"calculation_run_id": run_id}, outcomes=OUTCOMES[run_id])
    h = Harness(loader=loader)
    report = h.run(monkeypatch)
    b_writes = [f for rid, f in h.writes if rid.startswith(RUN_B)]
    assert len(b_writes) == len(SKUS) and all(f["financial_rip_v5_score"] is None and f["financial_rip_v5_rankable"] is False
                                              and f["financial_rip_v5_status"] == "unavailable" for f in b_writes)
    assert report["unavailableReasons"][reason] == len(SKUS)
    assert report["rowsReady"] == len(SKUS)  # run A rows still finalize; failure is row-level
    assert report["cohortComplete"] is False
    with pytest.raises(ValueError, match="incomplete"):
        svc.assert_v5_cohort_complete(report)


def test_wrong_artifact_run_is_refused(monkeypatch):
    h = Harness(loader=lambda run_id: SimpleNamespace(metadata={"calculation_run_id": "some-other-run"},
                                                      outcomes=OUTCOMES[RUN_A]))
    report = h.run(monkeypatch)
    assert report["rowsReady"] == 0 and report["unavailableReasons"]["artifact_lineage_mismatch"] == len(SKUS) * 2
    assert report["cohortComplete"] is False


def test_partial_cohort_cannot_masquerade_as_complete(monkeypatch):
    rows = _rows()
    rows[1]["median_value"] += 1.0  # persisted stats no longer match the regenerated vector
    h = Harness(rows=rows)
    report = h.run(monkeypatch)
    assert report["unavailableReasons"] == {"regenerated_distribution_mismatch": 1}
    assert report["rowsReady"] == len(rows) - 1 and report["cohortComplete"] is False


def test_v4_lineage_gate_catches_seed_or_cost_drift(monkeypatch):
    rows = _rows()
    rows[3]["financial_rip_v4_score"] += 1.0
    h = Harness(rows=rows)
    report = h.run(monkeypatch)
    assert report["unavailableReasons"] == {"v4_lineage_mismatch": 1} and report["cohortComplete"] is False


def test_wrong_seed_identity_is_detected_not_silently_accepted(monkeypatch):
    h = Harness(rows=_rows(key="a-different-set-key"))  # rows persisted under a different seed identity
    report = h.run(monkeypatch)
    # K=1 is X itself (seed-independent); every bootstrapped K must be refused
    refused = {r["sealedProductId"] for r in report["results"] if r["status"] == "unavailable"}
    assert len(refused) == (len(SKUS) - 1) * 2
    assert set(report["unavailableReasons"]) == {"regenerated_distribution_mismatch"}


def test_row_semantics_guards(monkeypatch):
    rows = _rows()
    rows[0]["accessory_value_included"] = True
    rows[1]["random_pack_count"] = 5
    rows[2]["product_market_cost"] = 0
    report = Harness(rows=rows).run(monkeypatch)
    assert report["unavailableReasons"] == {"accessory_value_must_be_excluded": 1,
                                            "invalid_or_mismatched_pack_count": 1, "invalid_product_cost": 1}


def test_rows_outside_current_cohort_are_skipped_and_block_completeness(monkeypatch):
    rows = _rows()
    rows.append(dict(rows[0], id="stale-1", calculation_run_id="old-run", sealed_product_id="stale-p"))
    h = Harness(rows=rows)
    real_read = lambda runs: rows  # noqa: E731 - a reader that leaks a stale-run row
    report = svc.finalize_financial_rip_v5(
        None, market_date="d", resolve_cohort_fn=h.cohort, read_rows_fn=real_read, artifact_loader_fn=h.load,
        run_hash_fn=lambda c, r: HASH, write_fn=lambda *a: h.writes.append(a))
    assert report["rowsSkipped"] == 1 and report["cohortComplete"] is False
    assert not any(rid == "stale-1" for rid, _ in h.writes)


def test_unverified_cohort_refuses_to_start(monkeypatch):
    h = Harness(cohort_ok=False)
    report = h.run(monkeypatch)
    assert report["status"] == "cannot_start" and not h.writes and not h.loads
    assert h.run(monkeypatch, require_verified_cohort=False)["status"] == "ok"


def test_dry_run_writes_nothing(monkeypatch):
    h = Harness()
    report = h.run(monkeypatch, dry_run=True)
    assert not h.writes and report["rowsReady"] == len(SKUS) * 2 and report["dryRun"] is True
