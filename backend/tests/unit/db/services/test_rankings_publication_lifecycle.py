from copy import deepcopy

import pytest

from backend.db.services import rankings_publication_lifecycle as lifecycle
from backend.db.services.set_rip_service import METHODOLOGY_VERSION


def candidate():
    targets = []
    products = []
    for index, key in enumerate(("alpha", "beta"), 1):
        set_id = f"set-{index}"
        run_id = f"run-{index}"
        targets.append({
            "set_id": set_id, "canonical_key": key, "calculation_run_id": run_id,
            "overallRipV10": {"rank": index},
            "setRipV1": {"rankable": True, "rank": index, "score": 80 - index,
                         "participatingFamilyCount": 2, "methodologyVersion": METHODOLOGY_VERSION},
        })
        for family in ("booster_box", "elite_trainer_box"):
            products.append((family, {
                "sealedProductId": f"{family}-{index}", "setId": set_id,
                "calculationRunId": run_id, "overallRipLeaderScore": 10,
                "financialRipLeaderScore": 10,
            }))
    families = {}
    for family, product in products:
        families.setdefault(family, {"products": [], "count": 2, "currentlyRankableCount": 2})["products"].append(product)
    row = {"ranking_payload_json": {
        "targets": targets,
        "productFamilyRankings": {"families": families},
        "setRip": {"methodologyVersion": METHODOLOGY_VERSION, "rankedSetCount": 2},
    }}
    snapshot = {"market_date": "2026-08-27", "eligible_cohort_count": 2}
    return row, snapshot


@pytest.fixture(autouse=True)
def supported(monkeypatch):
    monkeypatch.setattr(lifecycle, "supported_cohort_fingerprint", lambda: {"count": 2})


def test_complete_rankings_readiness_passes():
    row, snapshot = candidate()
    report = lifecycle.evaluate_rankings_publication_readiness(
        row, snapshot, expected_market_date="2026-08-27",
        sealed_product_finalization_status="ok",
        sealed_product_finalization_report={"setCount": 2, "rowsFinalized": 4},
    )
    assert report.ready
    assert report.verified_simulation_cohort_count == 2
    assert report.set_rip_ranked_set_count == 2
    assert report.source_run_ids == {"alpha": "run-1", "beta": "run-2"}


def test_missing_current_simulation_is_explicitly_deferred():
    row, snapshot = candidate()
    row["ranking_payload_json"]["targets"].pop()
    report = lifecycle.evaluate_rankings_publication_readiness(row, snapshot)
    assert report.reason_code == lifecycle.DEFERRED_SIMULATION_COHORT_INCOMPLETE


def test_incomplete_sealed_product_finalization_blocks_rankings():
    row, snapshot = candidate()
    report = lifecycle.evaluate_rankings_publication_readiness(
        row, snapshot, sealed_product_finalization_status="cannot_start")
    assert report.reason_code == lifecycle.DEFERRED_SEALED_PRODUCT_FINALIZATION_INCOMPLETE


def test_product_family_incomplete_blocks_rankings():
    row, snapshot = candidate()
    row["ranking_payload_json"]["productFamilyRankings"]["families"] = {}
    report = lifecycle.evaluate_rankings_publication_readiness(row, snapshot)
    assert report.reason_code == lifecycle.DEFERRED_PRODUCT_RANKINGS_INCOMPLETE


def test_set_rip_incomplete_blocks_rankings():
    row, snapshot = candidate()
    row["ranking_payload_json"]["setRip"]["rankedSetCount"] = 1
    report = lifecycle.evaluate_rankings_publication_readiness(row, snapshot)
    assert report.reason_code == lifecycle.DEFERRED_SET_RIP_INCOMPLETE


def test_source_run_fingerprint_is_order_independent():
    assert lifecycle.source_run_fingerprint({"a": "1", "b": "2"}) == lifecycle.source_run_fingerprint({"b": "2", "a": "1"})


def _ready_chase_accessibility_rows():
    from backend.desirability.chase_accessibility import CHASE_ACCESSIBILITY_VERSION
    # keyed by canonical_key ("alpha"/"beta"), matching source_run_ids' keying in
    # evaluate_rankings_publication_readiness (canonical_key or set_id/target_id).
    return [
        {"set_id": "alpha", "calculation_run_id": "run-1", "version": CHASE_ACCESSIBILITY_VERSION,
         "status": "ready", "accessibility": 0.002, "mapped_hc_mass": 1.0},
        {"set_id": "beta", "calculation_run_id": "run-2", "version": CHASE_ACCESSIBILITY_VERSION,
         "status": "ready", "accessibility": 0.003, "mapped_hc_mass": 1.0},
    ]


def test_chase_accessibility_integrity_gate_passes_when_rows_are_clean():
    row, snapshot = candidate()
    report = lifecycle.evaluate_rankings_publication_readiness(
        row, snapshot, expected_market_date="2026-08-27",
        sealed_product_finalization_status="ok",
        sealed_product_finalization_report={"setCount": 2, "rowsFinalized": 4},
        chase_accessibility_rows=_ready_chase_accessibility_rows(),
    )
    assert report.ready


def test_chase_accessibility_integrity_gate_blocks_on_missing_row():
    row, snapshot = candidate()
    rows = _ready_chase_accessibility_rows()[:1]  # beta's row is missing
    report = lifecycle.evaluate_rankings_publication_readiness(
        row, snapshot, expected_market_date="2026-08-27",
        sealed_product_finalization_status="ok",
        sealed_product_finalization_report={"setCount": 2, "rowsFinalized": 4},
        chase_accessibility_rows=rows,
    )
    assert report.reason_code == lifecycle.DEFERRED_CHASE_ACCESSIBILITY_INTEGRITY
    assert "missing_chase_accessibility_row" in report.detail


def test_chase_accessibility_integrity_gate_blocks_on_stale_calculation_run():
    row, snapshot = candidate()
    rows = _ready_chase_accessibility_rows()
    rows[0]["calculation_run_id"] = "run-stale"
    report = lifecycle.evaluate_rankings_publication_readiness(
        row, snapshot, expected_market_date="2026-08-27",
        sealed_product_finalization_status="ok",
        sealed_product_finalization_report={"setCount": 2, "rowsFinalized": 4},
        chase_accessibility_rows=rows,
    )
    assert report.reason_code == lifecycle.DEFERRED_CHASE_ACCESSIBILITY_INTEGRITY
    assert "stale_calculation_run" in report.detail


def test_chase_accessibility_integrity_gate_does_not_run_when_rows_not_supplied():
    """Backward compatible: omitting the param never fabricates a block."""
    row, snapshot = candidate()
    report = lifecycle.evaluate_rankings_publication_readiness(
        row, snapshot, expected_market_date="2026-08-27",
        sealed_product_finalization_status="ok",
        sealed_product_finalization_report={"setCount": 2, "rowsFinalized": 4},
    )
    assert report.ready


def test_aug27_v10_candidate_regression_documents_set_rip_wiring():
    source = (__import__("pathlib").Path(__file__).resolve().parents[4] / "scripts" / "pokemon_snapshot_builders.py").read_text(encoding="utf-8")
    assert 'target.get("overallRipV10")' in source
    assert 'target.get("overallRipV9")' not in source[source.index("product_family_rankings ="):source.index("comparison_diagnostics =")]


class Query:
    def __init__(self, client, name, rows):
        self.client, self.name, self.rows = client, name, list(rows)
    def select(self, *_args): return self
    def eq(self, key, value):
        self.rows = [row for row in self.rows if str(row.get(key)) == str(value)]
        return self
    def limit(self, count):
        self.rows = self.rows[:count]
        return self
    def insert(self, row):
        self.client.tables[self.name].append(dict(row)); self.rows = [row]
        return self
    def update(self, values):
        for row in self.rows: row.update(values)
        return self
    def execute(self): return type("Result", (), {"data": self.rows})()


class Client:
    def __init__(self, tables): self.tables = tables
    def table(self, name): return Query(self, name, self.tables.setdefault(name, []))


def parity_client(report, *, market_date="2026-08-27", run_ids=None, versions=None):
    run_ids = run_ids or report.source_run_ids
    targets = [{"canonical_key": key, "calculation_run_id": run_id, "overallRipV10": {"rank": index}}
               for index, (key, run_id) in enumerate(run_ids.items(), 1)]
    canonical_versions = versions or report.contract_versions
    payload = {"targets": targets, "meta": {"snapshot": {"marketDate": market_date},
        "ripWeightsConfig": {"publicContract": {"version": canonical_versions.get("publicRipContractVersion")}}}}
    return Client({
        "pokemon_explore_rankings_snapshot_latest": [{"tcg": "pokemon", "scope": "rip-statistics", "ranking_payload_json": payload, "updated_at": "now"}],
        "pokemon_public_rip_leaderboard_snapshots": [{"id": "publication", "market_date": market_date,
            "publication_status": "complete", "payload_json": payload,
            "overall_rip_version": canonical_versions.get("overallRipVersion"),
            "financial_rip_version": canonical_versions.get("financialRipVersion"),
            "ca7_version": canonical_versions.get("collectorAppealVersion")}],
    })


def ready_report():
    row, snapshot = candidate()
    return lifecycle.evaluate_rankings_publication_readiness(row, snapshot)


def test_post_publication_parity_catches_market_date_mismatch():
    report = ready_report()
    with pytest.raises(RuntimeError, match="market date"):
        lifecycle.assert_rankings_publication_parity(parity_client(report, market_date="2026-08-26"), report, publication_id="publication")


def test_post_publication_parity_catches_superseded_source_run():
    report = ready_report()
    with pytest.raises(RuntimeError, match="source run authority"):
        lifecycle.assert_rankings_publication_parity(parity_client(report, run_ids={"alpha": "old", "beta": "run-2"}), report, publication_id="publication")


def test_post_publication_parity_catches_version_mismatch():
    report = ready_report()
    wrong = {**report.contract_versions, "overallRipVersion": "old"}
    with pytest.raises(RuntimeError, match="version mismatch"):
        lifecycle.assert_rankings_publication_parity(parity_client(report, versions=wrong), report, publication_id="publication")


def test_attempt_record_is_written_and_finalized():
    report = ready_report()
    client = Client({"pokemon_rankings_publication_attempts": []})
    attempt_id = lifecycle.start_rankings_publication_attempt(client, report)
    lifecycle.finish_rankings_publication_attempt(client, attempt_id, status="published", reason_code="READY", detail="ok", publication_id="publication")
    row = client.tables["pokemon_rankings_publication_attempts"][0]
    assert row["status"] == "published"
    assert row["source_run_ids"] == report.source_run_ids
    assert row["completed_at"]
