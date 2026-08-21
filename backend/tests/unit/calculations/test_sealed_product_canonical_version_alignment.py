from backend.db.services.sealed_product_rip_service import interpret_collector_appeal_payload
from backend.desirability.collector_appeal import (
    COLLECTOR_APPEAL_V4_VERSION,
    COLLECTOR_APPEAL_V5_VERSION,
)
from backend.desirability.scoring_config import (
    OVERALL_RIP_V10_EFFECTIVE_WEIGHTS,
    OVERALL_RIP_V10_VERSION,
    OVERALL_RIP_V10_WEIGHTS,
    canonical_collector_appeal_version,
    canonical_public_rip_contract_version,
    canonical_scoring_selection,
)


def _payload(version, score=73.25):
    return {"collectorAppeal": {"version": version, "score": score}}


def test_sealed_products_accept_only_canonical_v5_collector_appeal():
    accepted = interpret_collector_appeal_payload(_payload(COLLECTOR_APPEAL_V5_VERSION))
    assert accepted == {
        "score": 73.25,
        "version": canonical_collector_appeal_version(),
        "available": True,
        "status": "available",
        "reason": None,
    }
    for payload in (
        _payload(COLLECTOR_APPEAL_V4_VERSION),
        _payload("collector_appeal_v3"),
        _payload("collector_appeal_ca7_v1"),
        _payload(None),
        _payload(COLLECTOR_APPEAL_V5_VERSION, None),
        {},
    ):
        rejected = interpret_collector_appeal_payload(payload)
        assert rejected["available"] is False
        assert rejected["score"] is None


def test_canonical_scoring_metadata_is_consistently_v5_v10():
    selection = canonical_scoring_selection()
    assert selection["canonicalCollectorAppealVersion"] == COLLECTOR_APPEAL_V5_VERSION
    assert selection["canonicalOverallRipVersion"] == OVERALL_RIP_V10_VERSION
    assert selection["canonicalPublicRipContractVersion"] == canonical_public_rip_contract_version()
    assert selection["overallRipWeights"] == OVERALL_RIP_V10_WEIGHTS
    assert selection["overallRipEffectiveWeights"] == OVERALL_RIP_V10_EFFECTIVE_WEIGHTS
    assert "Collector Appeal V5" in selection["note"]
    assert "Overall RIP V10" in selection["note"]
    assert "10% Collector Appeal V4" not in selection["note"]
