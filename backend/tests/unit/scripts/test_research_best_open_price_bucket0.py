import pytest

from backend.desirability.weighted_rip import compute_overall_rip_v12
from backend.scripts.research_best_open_price_bucket0 import (
    _financial_competitor,
    _historical_authority,
    _verify_v12_parity,
    interval_probe_cents,
    quantity_price_interval_cents,
    validate_financial_only_rank_reconstructs,
    validate_rank_column_contiguous,
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


def test_interval_probes_span_quartiles_and_deduplicate_narrow_intervals():
    assert interval_probe_cents(100, 200) == [100, 125, 150, 175, 200]
    assert interval_probe_cents(7, 8) == [7, 8]
    with pytest.raises(ValueError):
        interval_probe_cents(2, 1)


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


def _financial_row(pid, *, budget_rank_v12=None, financial_only_rank=None, financial_rip_v4_score=None):
    return {
        "sealed_product_id": pid,
        "budget_rank_v12": budget_rank_v12,
        "financial_only_rank": financial_only_rank,
        "financial_rip_v4_score": financial_rip_v4_score,
    }


def test_financial_competitor_picks_rank_two_for_the_financial_leader():
    rows = [_financial_row("a", financial_only_rank=1), _financial_row("b", financial_only_rank=2), _financial_row("c", financial_only_rank=3)]
    assert _financial_competitor(rows[0], rows)["sealed_product_id"] == "b"


def test_financial_competitor_picks_rank_one_for_a_financial_nonleader():
    rows = [_financial_row("a", financial_only_rank=1), _financial_row("b", financial_only_rank=2), _financial_row("c", financial_only_rank=3)]
    assert _financial_competitor(rows[1], rows)["sealed_product_id"] == "a"
    assert _financial_competitor(rows[2], rows)["sealed_product_id"] == "a"


def test_validate_rank_column_contiguous_accepts_valid_permutation():
    rows = [_financial_row("a", budget_rank_v12=2), _financial_row("b", budget_rank_v12=1), _financial_row("c", budget_rank_v12=3)]
    validate_rank_column_contiguous(rows, "budget_rank_v12")  # must not raise


def test_validate_rank_column_contiguous_rejects_missing_value():
    rows = [_financial_row("a", budget_rank_v12=1), _financial_row("b", budget_rank_v12=None)]
    with pytest.raises(RuntimeError, match="missing"):
        validate_rank_column_contiguous(rows, "budget_rank_v12")


def test_validate_rank_column_contiguous_rejects_duplicate():
    rows = [_financial_row("a", budget_rank_v12=1), _financial_row("b", budget_rank_v12=1)]
    with pytest.raises(RuntimeError, match="contiguous"):
        validate_rank_column_contiguous(rows, "budget_rank_v12")


def test_validate_rank_column_contiguous_rejects_non_contiguous_gap():
    rows = [_financial_row("a", budget_rank_v12=1), _financial_row("b", budget_rank_v12=3)]
    with pytest.raises(RuntimeError, match="contiguous"):
        validate_rank_column_contiguous(rows, "budget_rank_v12")


def test_validate_financial_only_rank_reconstructs_accepts_correct_ranks():
    rows = [
        _financial_row("high", financial_only_rank=1, financial_rip_v4_score=90.0),
        _financial_row("low", financial_only_rank=2, financial_rip_v4_score=10.0),
    ]
    validate_financial_only_rank_reconstructs(rows)  # must not raise


def test_validate_financial_only_rank_reconstructs_rejects_mismatched_rank():
    rows = [
        _financial_row("high", financial_only_rank=2, financial_rip_v4_score=90.0),  # wrong: should be 1
        _financial_row("low", financial_only_rank=1, financial_rip_v4_score=10.0),
    ]
    with pytest.raises(RuntimeError, match="does not reconstruct"):
        validate_financial_only_rank_reconstructs(rows)
