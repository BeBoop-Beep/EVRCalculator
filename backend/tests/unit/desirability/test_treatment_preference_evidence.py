import json
from pathlib import Path

import pytest

from backend.desirability.treatment_preference_evidence import (
    assert_price_independent,
    connected_components,
    market_validation_eligible,
    validate_source,
)

ROOT = Path(__file__).resolve().parents[4]
ARTIFACTS = ROOT / "backend" / "artifacts" / "treatment"


def load(name):
    return json.loads((ARTIFACTS / name).read_text(encoding="utf-8"))


def test_frozen_taxonomy_and_cohorts_are_compatible():
    manifest = load("treatment_preference_candidate_manifest.json")
    assert manifest["taxonomyFingerprint"] == "85fdb2344d9ae7842a91bf0b3b0a434e02e99298be4cb025c8b3826066f67ddc"
    assert manifest["cohortControls"] == {
        "best_same_card": {"count": 2, "fingerprint": "ec964944c28f6abe0361eb3807e13e30b66adcf7a34e3c7c64b9ac009f19dfff"},
        "best_same_subject": {"count": 6251, "fingerprint": "87c4e955c6783b90d2535b32c49f6faa538a12bc604ad894ec7765841fe042af"},
        "best_scarcity_matched": {"count": 87, "fingerprint": "d9f40b5d4d20781ea057972054c3a5999fc6a5a733cf7239ef21b2e02b367adb"},
        "era_local": {"count": 6253, "fingerprint": "d09d2ae899b3b3c2298c383572f6d93100c4ec84c032c71b6fd5bfb5c9848677"},
    }


def test_sources_are_classified_and_none_construct_authority():
    data = load("treatment_preference_sources.json")
    for source in data["sources"]:
        validate_source(source)
    assert data["counts"] == {"A": 2, "B": 6, "C": 3, "D": 4, "E": 1}
    assert not any(source["usableForAuthority"] for source in data["sources"])


def test_era_isolation_and_confidence_states():
    data = load("treatment_preference_era_evidence.json")
    assert {row["era"] for row in data["eras"]} == {"Scarlet & Violet", "Sword & Shield", "Sun & Moon", "XY", "Vintage"}
    assert all(row["verdict"] == "INSUFFICIENT_EVIDENCE" for row in data["eras"])
    assert all(row["confidence"] == "INSUFFICIENT" for row in data["eras"])
    assert all(row["crossEraInferenceAllowed"] is False for row in data["eras"])


def test_preference_construction_has_no_market_fields():
    for name in (
        "treatment_preference_era_evidence.json",
        "treatment_semantic_attribute_evidence.json",
        "treatment_preference_graph.json",
        "treatment_preference_candidate_manifest.json",
    ):
        assert_price_independent(load(name))
    with pytest.raises(ValueError, match="market field prohibited"):
        assert_price_independent({"market_price": 10})


def test_graph_is_disconnected_without_accepted_direct_edges():
    graph = load("treatment_preference_graph.json")
    assert graph["directPreferenceEdgeCount"] == 0
    assert graph["indirectOnlyEdgeCount"] == 3
    assert connected_components(graph["nodes"], graph["edges"]) == [[node] for node in sorted(graph["nodes"])]
    assert graph["cardinalScoringEligible"] is False


def test_market_validation_leakage_gate_stays_closed():
    manifest = load("treatment_preference_candidate_manifest.json")
    assert market_validation_eligible(manifest) is False
    assert manifest["marketValidation"]["status"] == "NOT_RUN_INELIGIBLE"
