"""Sealed-product V4/V10 persistence regressions.

`_to_row` previously dropped Financial RIP V4 and Overall RIP V10 entirely, so
both models existed only in memory. They must now serialize ALONGSIDE the V3/V9
fields on the same authoritative row - never in place of them, and never by
duplicating the (calculation_run_id, sealed_product_id) identity.
"""

from backend.db.services.sealed_product_rip_service import _to_row

RUN_ID = "run-1"
SET_ID = "set-1"

V3_PAYLOAD = {"score": 41.0, "scoreVersion": "financial_rip_v3_outcome_profile_25_20_15_25_10_5"}
V4_PAYLOAD = {
    "score": 39.5,
    "scoreVersion": "financial_rip_v4_outcome_profile_p95_only_25_20_15_25_10_5",
}
V10_PAYLOAD = {"score": 43.1, "version": "overall_rip_v10_90_financial_v4_10_collector_appeal_v5"}


def _product(**overrides):
    product = {
        "sealed_product_id": "sku-1",
        # Required identity/provenance columns _to_row reads strictly.
        "product_family": "booster_box",
        "product_name": "Test Box",
        "pack_count": 36,
        "composition_version": "composition_v1",
        "distribution_model_version": "distribution_v1",
        "pack_independence_assumption": True,
        "product_market_cost": 120.0,
        "simulation_count": 1000,
        "financial_rip_v3_score": 41.0,
        "financial_rip_v3_status": "ready",
        "financial_rip_v3_rankable": True,
        "financial_rip_v3_version": V3_PAYLOAD["scoreVersion"],
        "financial_rip_v3_payload": V3_PAYLOAD,
        "collector_appeal_score": 60.0,
        "collector_appeal_version": "collector_appeal_v5_contextual_roster_h_only_d_baseline_up4_down2",
        "overall_rip_score": 44.0,
        "overall_rip_version": "overall_rip_v9_90_financial_v3_10_collector_appeal_v5",
        "overall_rip_rankable": True,
        "overall_rip_payload": {"score": 44.0},
        "financial_rip_v4_score": 39.5,
        "financial_rip_v4_status": "ready",
        "financial_rip_v4_rankable": True,
        "financial_rip_v4_version": V4_PAYLOAD["scoreVersion"],
        "financial_rip_v4_payload": V4_PAYLOAD,
        "overall_rip_v10_score": 43.1,
        "overall_rip_v10_version": V10_PAYLOAD["version"],
        "overall_rip_v10_rankable": True,
        "overall_rip_v10_payload": V10_PAYLOAD,
    }
    product.update(overrides)
    return product


def _row(**overrides):
    return _to_row(_product(**overrides), calculation_run_id=RUN_ID, set_id=SET_ID)


def test_v3_values_are_persisted_unchanged():
    row = _row()
    assert row["financial_rip_v3_score"] == 41.0
    assert row["financial_rip_v3_status"] == "ready"
    assert row["financial_rip_v3_rankable"] is True
    assert row["financial_rip_v3_version"] == V3_PAYLOAD["scoreVersion"]
    assert row["financial_rip_v3_payload"] == V3_PAYLOAD


def test_v9_overall_values_are_persisted_unchanged():
    row = _row()
    assert row["overall_rip_score"] == 44.0
    assert row["overall_rip_version"] == "overall_rip_v9_90_financial_v3_10_collector_appeal_v5"
    assert row["overall_rip_rankable"] is True


def test_v4_serializes_into_its_own_fields():
    row = _row()
    assert row["financial_rip_v4_score"] == 39.5
    assert row["financial_rip_v4_status"] == "ready"
    assert row["financial_rip_v4_rankable"] is True
    assert row["financial_rip_v4_version"] == V4_PAYLOAD["scoreVersion"]
    assert row["financial_rip_v4_payload"] == V4_PAYLOAD


def test_v10_serializes_into_its_own_fields():
    row = _row()
    assert row["overall_rip_v10_score"] == 43.1
    assert row["overall_rip_v10_version"] == V10_PAYLOAD["version"]
    assert row["overall_rip_v10_rankable"] is True
    assert row["overall_rip_v10_payload"] == V10_PAYLOAD


def test_v3_and_v4_never_share_a_field():
    """The two models must be independently readable, not one overwriting the other."""
    row = _row()
    assert row["financial_rip_v3_score"] != row["financial_rip_v4_score"]
    assert row["financial_rip_v3_version"] != row["financial_rip_v4_version"]
    assert row["overall_rip_score"] != row["overall_rip_v10_score"]
    assert row["overall_rip_version"] != row["overall_rip_v10_version"]


def test_a_reader_can_distinguish_versions_by_identity_string():
    row = _row()
    assert "financial_rip_v4" in row["financial_rip_v4_version"]
    assert "financial_rip_v3" in row["financial_rip_v3_version"]
    assert "overall_rip_v10" in row["overall_rip_v10_version"]
    assert "overall_rip_v9" in row["overall_rip_version"]


def test_missing_v4_leaves_null_and_does_not_disturb_v3():
    """Pre-V4 rows must round-trip: absent V4 is NULL, never a V3 value."""
    row = _row(
        financial_rip_v4_score=None,
        financial_rip_v4_status=None,
        financial_rip_v4_rankable=None,
        financial_rip_v4_version=None,
        financial_rip_v4_payload=None,
        overall_rip_v10_score=None,
        overall_rip_v10_version=None,
        overall_rip_v10_rankable=None,
        overall_rip_v10_payload=None,
    )
    assert row["financial_rip_v4_score"] is None
    assert row["financial_rip_v4_payload"] is None
    assert row["overall_rip_v10_score"] is None
    assert row["financial_rip_v3_score"] == 41.0
    assert row["overall_rip_score"] == 44.0


def test_row_identity_is_unchanged_so_the_unique_key_still_holds():
    """V4 must not be encoded by duplicating the run/SKU identity."""
    row = _row()
    assert row["calculation_run_id"] == RUN_ID
    assert row["sealed_product_id"] == "sku-1"
    identity_keys = [key for key in row if key in ("calculation_run_id", "sealed_product_id")]
    assert sorted(identity_keys) == ["calculation_run_id", "sealed_product_id"]
