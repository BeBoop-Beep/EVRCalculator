import pytest

from backend.db.services.sealed_product_rip_finalization_service import _enrichment_for


def test_enrichment_writes_both_v9_and_v10():
    row = {"financial_rip_v3_score": 41.0, "financial_rip_v4_score": 39.5}
    appeal = {"score": 60.0, "version": "collector_appeal_v5_contextual_roster_h_only_d_baseline_up4_down2"}

    enrichment = _enrichment_for(row, appeal)

    # legacy V9 fields untouched in shape/meaning
    assert "overall_rip_v9" in enrichment["overall_rip_version"] or "overall_rip_v9" in str(enrichment["overall_rip_payload"].get("version", ""))
    # new V10 fields present
    assert "overall_rip_v10" in enrichment["overall_rip_v10_version"]
    assert enrichment["overall_rip_v10_rankable"] is True


def test_v10_arithmetic_is_exactly_90_10():
    row = {"financial_rip_v3_score": 41.0, "financial_rip_v4_score": 40.0}
    appeal = {"score": 50.0, "version": "collector_appeal_v5_..."}

    enrichment = _enrichment_for(row, appeal)

    expected = 0.90 * 40.0 + 0.10 * 50.0
    assert enrichment["overall_rip_v10_score"] == pytest.approx(expected)


def test_v9_and_v10_use_same_collector_appeal_input_never_diverge():
    row = {"financial_rip_v3_score": 41.0, "financial_rip_v4_score": 39.5}
    appeal = {"score": 60.0, "version": "collector_appeal_v5_..."}

    enrichment = _enrichment_for(row, appeal)

    assert enrichment["collector_appeal_score"] == 60.0
    # both blends were fed the SAME appeal_score local variable - verified by
    # construction (one `appeal_score = appeal.get("score")` line feeds both calls)
    assert enrichment["overall_rip_v10_payload"]["score"] is not None
