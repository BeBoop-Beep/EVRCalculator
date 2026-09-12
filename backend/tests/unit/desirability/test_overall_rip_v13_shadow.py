import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
ARTIFACT = ROOT / "docs" / "research" / "overall_rip_v13_collector_v7_shadow.json"


def test_shadow_is_append_only_and_not_promoted():
    data = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    assert data["decision"] == "OVERALL_RIP_V13_COLLECTOR_V7_BLOCKED"
    assert data["candidate"]["published"] is False
    assert data["history"] == {"v12RowsModified": 0, "v13HistoryStarted": False, "backcastPerformed": False}
    assert data["productionMutations"] == "NONE"


def test_weights_and_frozen_collector_authority_are_exact():
    data = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    assert data["candidate"]["weights"] == {"financialRipV4": 0.86, "chaseAccessibilityV1": 0.04, "collectorAppealV7": 0.10}
    authority = data["collectorAuthority"]
    assert authority["modelRunId"] == "e282f26e-2136-4105-b0a3-f0974c4d9d70"
    assert authority["formulaFingerprint"] == "06f5660047b9b8a4d7349d04b79547b1314c2be3720c245ba8780890db1c114b"
    assert authority["priceExcluded"] and authority["treatmentExcluded"]
    assert authority["scarcityDirectContribution"] is False


def test_v7_stays_secondary_but_publication_gate_is_closed():
    data = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    influence = data["influence"]
    assert influence["collectorV7ContributionVariance"] < influence["collectorV5ContributionVariance"]
    assert influence["collectorV7ContributionVariance"] < influence["financialContributionVariance"]
    assert influence["weightDecision"] == "KEEP_86_04_10"
    assert data["promotionGate"]["acceptedConceptually"] is True
    assert data["promotionGate"]["inactiveCandidateBuilt"] is False
