import json
from pathlib import Path

from backend.desirability.scoring_config import (
    OVERALL_RIP_V12_COLLECTOR_APPEAL_WEIGHT,
    OVERALL_RIP_V12_VERSION,
)
from backend.scripts.operationalize_historical_rip import FROZEN_FORMULA_FINGERPRINT, V7

ROOT = Path(__file__).resolve().parents[4]
DIR = ROOT / "docs" / "research" / "collector_appeal"


def load(name):
    return json.loads((DIR / name).read_text(encoding="utf-8"))


def test_current_pointer_and_exact_frozen_formula_lineage():
    manifest = load("final_collector_appeal_control_manifest.json")
    assert manifest["status"] == "COLLECTOR_APPEAL_FINAL_CONTROL_FROZEN"
    assert manifest["model"]["version"] == V7
    assert manifest["model"]["formulaFingerprint"] == FROZEN_FORMULA_FINGERPRINT
    assert manifest["model"]["runId"] == manifest["setPage"]["collectorModelRunId"]
    assert len(manifest["sourceLineage"]) == 6


def test_treatment_and_scarcity_never_contribute():
    manifest = load("final_collector_appeal_control_manifest.json")
    assert manifest["components"]["diagnosticOnly"] == ["Treatment", "Pull Scarcity"]
    assert manifest["model"]["treatmentInputsExcluded"] is True
    assert manifest["model"]["scarcityDirectContribution"] is False
    register = load("final_collector_appeal_component_register.json")
    by_name = {row["component"]: row for row in register["components"]}
    for name in ("Treatment", "Pull Scarcity"):
        assert by_name[name]["productionStatus"] == "NOT INCLUDED IN COLLECTOR APPEAL SCORE"


def test_refresh_history_and_atomic_publication_contracts_are_closed():
    ops = load("final_collector_appeal_control_manifest.json")["operations"]
    assert ops["selectiveRefresh"] and ops["frozenFormulaRebuild"]
    assert ops["atomicPublication"] and ops["dailyHistoryAppend"] and ops["idempotent"]
    assert ops["historyLiveReadback"]["distinctDates"] == 2
    assert ops["historyLiveReadback"]["currentRunRows"] == 128


def test_overall_v12_is_not_interfered_with():
    overall = load("final_collector_appeal_control_manifest.json")["overall"]
    assert overall["currentVersion"] == OVERALL_RIP_V12_VERSION
    assert OVERALL_RIP_V12_COLLECTOR_APPEAL_WEIGHT == 0.10
    assert overall["currentCollectorAuthority"] == "collector_appeal_v5_contextual_roster_h_only_d_baseline_up4_down2"
    assert overall["v7Used"] is False


def test_article_manifest_has_exact_model_lineage_and_all_visuals():
    control = load("final_collector_appeal_control_manifest.json")
    article = load("collector_appeal_article_evidence_manifest.json")
    for field in ("version", "runId", "modelFingerprint", "formulaFingerprint", "cardFingerprint", "setFingerprint"):
        assert article["model"][field] == control["model"][field]
    assert len(article["requiredVisuals"]) == 5
    assert article["articleWritten"] is False


def test_validation_register_preserves_uncertain_v7_over_v6_result():
    validation = load("final_collector_market_validation_register.json")
    assert validation["overall"]["verdict"] == "APPEAL_PRICING_SIGNAL_PARTIAL"
    assert validation["overall"]["promotion"] == "V7_PROMOTION_SUPPORTED_WITH_LIMITATIONS"
    low, high = validation["v7VsV6"]["bootstrapOosR2Interval"]
    assert low < 0 < high
    assert not validation["rerunPerformed"] and not validation["retuningPerformed"]
