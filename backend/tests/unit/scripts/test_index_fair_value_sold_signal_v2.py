from __future__ import annotations

import pandas as pd

from backend.scripts import reanalyze_index_fair_value_sold_signal_v2 as pilot


def _frame() -> pd.DataFrame:
    rows = []
    for i in range(30):
        baseline = 20.0 + i
        target = baseline * (0.92 + (i % 7) * 0.025)
        sold_median = baseline * (0.85 + (i % 5) * 0.08)
        rows.append(
            {
                "canonical_card_id": f"card-{i}",
                "root_set_id": f"set-{i % 6}",
                "target_nm_market_price": target,
                "structural_price": baseline,
                "market_anchored_price": baseline * 1.02,
                "eligible_sold_count": 3 + (i % 8),
                "sold_30d": i % 4,
                "sold_90d": 2 + (i % 7),
                "sold_180d": 4 + (i % 11),
                "last_sale_age_days": 1 + (i % 30),
                "sold_median": sold_median,
                "sold_mad": sold_median * 0.08,
                "sold_iqr": sold_median * 0.18,
                "sold_trend_fraction": (i % 5 - 2) * 0.03,
                # Deliberately absurd leaked values: V2 must ignore this column.
                "sold_median_to_nm_ratio": 1000.0 + i,
            }
        )
    return pd.DataFrame(rows)


def test_deployable_features_do_not_include_target_or_v1_leak():
    frame = _frame()
    features, names = pilot._deployable_features(frame, "market_anchored_price", "price_context")
    assert not features.empty
    assert "target_nm_market_price" not in names
    assert "sold_median_to_nm_ratio" not in names
    assert not any("to_nm_ratio" in name for name in names)
    assert "log_sold_median_to_baseline" in names


def test_grouped_v2_model_evaluates_without_leaked_column():
    frame = _frame()
    _, result = pilot._grouped_ridge(frame, "structural_price", "price_context")
    assert result["status"] == "EVALUATED"
    assert result["n"] == len(frame)
    assert "target_nm_market_price" not in result["features"]
    assert "sold_median_to_nm_ratio" not in result["features"]


def test_analyze_records_v1_leakage_and_spends_zero_credits(tmp_path, monkeypatch):
    source = tmp_path / "sample_features.csv"
    _frame().to_csv(source, index=False)
    monkeypatch.setattr(pilot, "OUT", tmp_path / "out")
    report = pilot.analyze(source)
    assert report["providerCalls"] == 0
    assert report["providerCreditsUsed"] == 0
    assert report["sourceContainsV1LeakedColumn"] is True
    assert report["v1MethodologyReassessment"]["finding"] == "TARGET_LEAKAGE"
    assert (pilot.OUT / "pilot_report.json").exists()
    assert (pilot.OUT / "oof_predictions.csv").exists()
