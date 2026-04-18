from unittest.mock import patch

import pytest

from backend.db.services.calculation_run_persistence_service import persist_simulation_etb_summary


@patch("backend.db.services.calculation_run_persistence_service.create_simulation_etb_summary")
def test_persist_simulation_etb_summary_raises_when_metrics_missing(mock_create_simulation_etb_summary):
    with pytest.raises(ValueError, match="Missing required field: etb_metrics"):
        persist_simulation_etb_summary(run_id="run-1", etb_metrics=None)

    mock_create_simulation_etb_summary.assert_not_called()


@patch("backend.db.services.calculation_run_persistence_service.create_simulation_etb_summary")
def test_persist_simulation_etb_summary_raises_when_required_field_missing(mock_create_simulation_etb_summary):
    incomplete_metrics = {
        "etb_market_price": "49.99",
        "etb_promo_price": "3.5",
        "total_ev_per_pack": "4.5",
        "total_packs_per_etb": "9",
        "total_etb_ev": "44.0",
        "etb_net_value": "-5.99",
    }

    with pytest.raises(ValueError, match="Missing required field"):
        persist_simulation_etb_summary(run_id="run-1", etb_metrics=incomplete_metrics)

    mock_create_simulation_etb_summary.assert_not_called()


@patch("backend.db.services.calculation_run_persistence_service.create_simulation_etb_summary")
def test_persist_simulation_etb_summary_coerces_and_persists(mock_create_simulation_etb_summary):
    mock_create_simulation_etb_summary.return_value = {"id": "etb-1"}

    result = persist_simulation_etb_summary(
        run_id="run-1",
        etb_metrics={
            "etb_market_price": "49.99",
            "etb_promo_price": "3.5",
            "total_ev_per_pack": "4.5",
            "total_packs_per_etb": "9",
            "total_etb_ev": "44.0",
            "etb_net_value": "-5.99",
            "etb_roi": "0.880176",
            "etb_roi_percentage": "88.0176",
        },
    )

    assert result == {"persisted": True, "etb_summary_id": "etb-1"}
    mock_create_simulation_etb_summary.assert_called_once_with(
        "run-1",
        {
            "packs_per_etb": 9,
            "etb_market_price": 49.99,
            "promo_price": 3.5,
            "ev_per_pack": 4.5,
            "total_etb_ev": 44.0,
            "net_value": -5.99,
            "roi": 0.880176,
            "roi_percent": 88.0176,
        },
    )
