from __future__ import annotations

import ast
from pathlib import Path

import numpy as np
import pytest

from backend.domain.pokemon import sealed_product_comparison_scope as scope
from backend.scripts import research_cross_format_product_rip as research


def _snapshot(**overrides):
    row = {"id": "snapshot", "publication_status": "complete", "published_at": "now",
           "eligible_cohort_count": 22, "financial_rip_version": "financial_rip_v3_test",
           "overall_rip_version": "overall_rip_v9_test"}
    row.update(overrides)
    return row


def _rows():
    return [{"set_id": f"set-{i}", "set_canonical_key": f"key{i}",
             "simulation_calculation_run_id": f"authoritative-{i}", "overall_rip_rank": i + 1,
             "pack_price": 5.0} for i in range(22)]


def test_authority_requires_complete_published_exact_cohort_and_distinct_runs():
    research.validate_authority(_snapshot(), _rows())
    with pytest.raises(RuntimeError, match="complete and published"):
        research.validate_authority(_snapshot(publication_status="failed"), _rows())
    with pytest.raises(RuntimeError, match="incomplete cohort"):
        research.validate_authority(_snapshot(), _rows()[:-1])
    duplicate = _rows(); duplicate[-1]["simulation_calculation_run_id"] = duplicate[0]["simulation_calculation_run_id"]
    with pytest.raises(RuntimeError, match="one-to-one"):
        research.validate_authority(_snapshot(), duplicate)


def test_authoritative_selection_does_not_consult_or_substitute_latest_runs():
    source = Path(research.__file__).read_text(encoding="utf-8")
    resolver = source[source.index("def resolve_authoritative_snapshot"):source.index("def validate_authority")]
    assert "explore_rip_statistics_latest" not in resolver
    assert "simulation_calculation_run_id" not in resolver  # rows are accepted as published authority, not replaced


def test_six_requested_pack_counts_and_baseline_delta():
    assert research.PACK_COUNTS == (1, 6, 9, 11, 18, 36)
    sets = []
    for i in range(22):
        entries = [{"packCount": k, "deltaVsOnePack": 0.0 if k == 1 else float(k),
                    "rtpDeviationVsOnePack": 0.0,
                    "componentDeltasVsOnePack": {c: 0.0 for c in research.FINANCIAL_RIP_V3_COMPONENT_ORDER}}
                   for k in research.PACK_COUNTS]
        sets.append({"entries": entries, "concentration": {}, "maxAbsolutePackCountDelta": 36.0,
                     "authoritativeRunId": str(i), "artifact": {"outcome_count": 1_000_000},
                     "canonicalKey": f"key{i}", "collectorAppealV5Derived": 50.0})
    report = research.assemble_report({"id":"s", "market_date":"d", "published_at":"p",
        "publication_status":"complete", "financial_rip_version":"v3", "overall_rip_version":"v9"}, sets)
    assert report["deltaSummaries"]["1"]["maxAbsolute"] == 0


def test_cost_scales_as_k_times_authoritative_pack_cost_and_no_guaranteed_composition(monkeypatch):
    costs = []
    monkeypatch.setattr(research, "EXPECTED_OUTCOMES", 10)
    monkeypatch.setattr(research, "load_pack_outcome_artifact", lambda *_: type("A", (), {
        "outcomes": np.arange(10, dtype=float), "metadata": {"outcome_count": 10, "raw_sha256": "a"*64}})())
    monkeypatch.setattr(research, "build_stage1_product_distributions", lambda *_, **__: {
        "distributions": {k: np.arange(10, dtype=float) * k for k in research.PACK_COUNTS}, "meta": {}})
    def fake_score(values, cost, count):
        costs.append((count, cost)); return {"packCount": count, "score": 1.0, "components": {
            c: 1.0 for c in research.FINANCIAL_RIP_V3_COMPONENT_ORDER}, "rtpRatioDirect": 1.0,
            "status":"ready", "rankable":True, "rawInputs":{}, "distributionDisclosures":{}, "clippedInputs":[]}
    monkeypatch.setattr(research, "_score_entry", fake_score)
    research.score_set(None, {"simulation_calculation_run_id":"run", "set_canonical_key":"key", "set_id":"id",
        "overall_rip_rank":1, "pack_price":4.25, "financial_rip_score":1, "overall_rip_score":1}, {})
    assert costs == [(k, k * 4.25) for k in research.PACK_COUNTS]
    assert research.assemble_report.__code__.co_names.count("guaranteedValueComposition") == 0  # literal lives in report method
    assert "guaranteed_component_value" not in Path(research.__file__).read_text(encoding="utf-8")


def test_exact_artifact_count_is_required(monkeypatch):
    monkeypatch.setattr(research, "load_pack_outcome_artifact", lambda *_: type("A", (), {
        "outcomes": np.ones(9), "metadata": {"outcome_count": 9, "raw_sha256": "a"*64}})())
    with pytest.raises(RuntimeError, match="artifact count"):
        research.score_set(None, {"simulation_calculation_run_id":"run", "set_canonical_key":"key"}, {})


def test_rtp_invariant_calculation():
    entry = research._score_entry(np.array([2.0, 4.0] * 5000), 5.0, 1)
    assert entry["rtpRatioDirect"] == pytest.approx(0.6)


def test_no_database_writes_and_production_contract_and_import_isolation():
    source = Path(research.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden = {"insert", "update", "delete", "upsert", "rpc"}
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call) and
             isinstance(node.func, ast.Attribute) and node.func.attr in forbidden]
    def mentions_client(node):
        return any(isinstance(part, ast.Name) and part.id == "client" for part in ast.walk(node))
    # Local dict/list/sys.path methods may share SQL verbs; no forbidden method
    # may be rooted in the database client query chain.
    assert not any(mentions_client(node.func.value) for node in calls)
    assert scope.SEALED_PRODUCT_CROSS_FORMAT_COMPARABLE is False
    repo = Path(research.__file__).resolve().parents[2]
    production = [p for p in (repo / "backend").rglob("*.py") if "tests" not in p.parts and p != Path(research.__file__)]
    assert all("research_cross_format_product_rip" not in p.read_text(encoding="utf-8", errors="ignore") for p in production)
