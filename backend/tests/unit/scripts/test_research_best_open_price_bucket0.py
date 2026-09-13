import pytest

from backend.desirability.weighted_rip import compute_overall_rip_v12
from backend.scripts.research_best_open_price_bucket0 import (
    _historical_authority,
    _verify_v12_parity,
    quantity_price_interval_cents,
)


SNAPSHOT = {
    "id": "snapshot-1",
    "cohort_fingerprint": "cohort-1",
    "overall_rip_v12_version": "overall-v12",
    "chase_accessibility_version": "accessibility-v1",
    "chase_accessibility_transform_version": "transform-v1",
}


def _row(product="product-1", set_id="set-1", run="run-1", raw="0.002"):
    computed = compute_overall_rip_v12("70", raw, "60")["score"]
    return {
        "sealed_product_id": product,
        "set_id": set_id,
        "source_calculation_run_id": run,
        "chase_accessibility_raw": raw,
        "financial_rip_v4_score": "70",
        "collector_appeal_score": "60",
        "overall_rip_v12_score": str(computed),
    }


@pytest.mark.parametrize("budget,quantity", [(135000, 1), (135000, 2), (100, 3), (7, 7)])
def test_quantity_price_interval_is_exact_at_boundaries(budget, quantity):
    low, high = quantity_price_interval_cents(budget, quantity)
    assert budget // low == quantity
    assert budget // high == quantity
    if low > 1:
        assert budget // (low - 1) >= quantity + 1
    if high < budget:
        assert budget // (high + 1) <= quantity - 1


def test_quantity_price_interval_rejects_nonpositive_inputs():
    with pytest.raises(ValueError):
        quantity_price_interval_cents(0, 1)
    with pytest.raises(ValueError):
        quantity_price_interval_cents(100, 0)


def test_historical_authority_is_deterministic_across_row_order():
    rows = [_row(), _row("product-2", "set-2", "run-2", "0.003")]
    first = _historical_authority(SNAPSHOT, rows)
    second = _historical_authority(SNAPSHOT, list(reversed(rows)))
    assert first["fingerprint"] == second["fingerprint"]
    assert len(first["setTuples"]) == 2


@pytest.mark.parametrize("field,value,message", [
    ("chase_accessibility_raw", None, "null persisted"),
    ("chase_accessibility_raw", "0.004", "distinct persisted raw values"),
    ("source_calculation_run_id", "run-2", "source calculation runs"),
])
def test_historical_authority_fails_closed(field, value, message):
    second = _row("product-2")
    second[field] = value
    with pytest.raises(RuntimeError, match=message):
        _historical_authority(SNAPSHOT, [_row(), second])


def test_v12_parity_uses_canonical_computation_and_fails_on_any_delta():
    assert _verify_v12_parity([_row()], label="test")["mismatchCount"] == 0
    bad = _row()
    bad["overall_rip_v12_score"] = "0"
    with pytest.raises(RuntimeError, match="parity failed"):
        _verify_v12_parity([bad], label="test")
