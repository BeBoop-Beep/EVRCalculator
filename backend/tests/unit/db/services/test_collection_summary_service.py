from uuid import uuid4
from unittest.mock import patch

from backend.db.services.collection_summary_service import (
    get_user_collection_summary,
    get_user_collection_summary_snapshot,
    refresh_user_summary_with_history_and_deltas,
    run_daily_portfolio_reconciliation_all_users,
)
from backend.models.collection_summary_models import CollectionSummary


@patch("backend.db.services.collection_summary_service.load_user_collection_for_summary")
def test_get_user_collection_summary_returns_model(mock_loader):
    mock_loader.return_value = {
        "user_card_holdings": [{"quantity": 2, "market_price": 10.0}],
        "user_sealed_product_holdings": [{"quantity": 1, "market_price": 20.0}],
        "user_graded_card_holdings": [{"quantity": 3, "market_price": 5.0}],
    }

    result = get_user_collection_summary(uuid4())

    assert isinstance(result, CollectionSummary)
    assert result.cards_count == 2
    assert result.sealed_count == 1
    assert result.graded_count == 3
    assert result.portfolio_value == 55.0


@patch("backend.db.services.collection_summary_service.load_user_collection_for_summary")
def test_get_user_collection_summary_empty_payload(mock_loader):
    mock_loader.return_value = {
        "user_card_holdings": [],
        "user_sealed_product_holdings": [],
        "user_graded_card_holdings": [],
    }

    result = get_user_collection_summary(uuid4())

    assert result.portfolio_value == 0.0
    assert result.cards_count == 0
    assert result.sealed_count == 0
    assert result.graded_count == 0


@patch("backend.db.services.collection_summary_service.load_user_collection_summary_snapshot")
def test_get_user_collection_summary_snapshot_returns_precomputed_values(mock_load_snapshot):
    mock_load_snapshot.return_value = {
        "portfolio_value": "2152.5",
        "cards_count": "11",
        "sealed_count": 2,
        "graded_count": 1,
        "portfolio_delta_1d": "12.1",
        "portfolio_delta_7d": 44,
        "portfolio_delta_3m": 88.5,
        "portfolio_delta_6m": 130,
        "portfolio_delta_1y": 245,
        "portfolio_delta_lifetime": 600,
        "portfolio_delta_pct_1d": "0.56",
        "portfolio_delta_pct_7d": "2.14",
        "portfolio_delta_pct_3m": 4.2,
        "portfolio_delta_pct_6m": 6.7,
        "portfolio_delta_pct_1y": 12.8,
        "portfolio_delta_pct_lifetime": 28.0,
        "computed_at": "2026-04-08T12:34:56+00:00",
        "is_stale": False,
    }

    result = get_user_collection_summary_snapshot(uuid4())

    assert result == {
        "portfolio_value": 2152.5,
        "cards_count": 11,
        "sealed_count": 2,
        "graded_count": 1,
        "portfolio_delta_1d": 12.1,
        "portfolio_delta_7d": 44.0,
        "portfolio_delta_3m": 88.5,
        "portfolio_delta_6m": 130.0,
        "portfolio_delta_1y": 245.0,
        "portfolio_delta_lifetime": 600.0,
        "portfolio_delta_pct_1d": 0.56,
        "portfolio_delta_pct_7d": 2.14,
        "portfolio_delta_pct_3m": 4.2,
        "portfolio_delta_pct_6m": 6.7,
        "portfolio_delta_pct_1y": 12.8,
        "portfolio_delta_pct_lifetime": 28.0,
        "computed_at": "2026-04-08T12:34:56+00:00",
        "is_stale": False,
        "row_found": True,
    }


@patch("backend.db.services.collection_summary_service.load_user_collection_summary_snapshot")
def test_get_user_collection_summary_snapshot_defaults_when_row_missing(mock_load_snapshot):
    mock_load_snapshot.return_value = None

    result = get_user_collection_summary_snapshot(uuid4())

    assert result == {
        "portfolio_value": 0.0,
        "cards_count": 0,
        "sealed_count": 0,
        "graded_count": 0,
        "portfolio_delta_1d": 0.0,
        "portfolio_delta_7d": 0.0,
        "portfolio_delta_3m": 0.0,
        "portfolio_delta_6m": 0.0,
        "portfolio_delta_1y": 0.0,
        "portfolio_delta_lifetime": 0.0,
        "portfolio_delta_pct_1d": None,
        "portfolio_delta_pct_7d": None,
        "portfolio_delta_pct_3m": None,
        "portfolio_delta_pct_6m": None,
        "portfolio_delta_pct_1y": None,
        "portfolio_delta_pct_lifetime": None,
        "computed_at": None,
        "is_stale": None,
        "row_found": False,
    }


@patch("backend.db.services.collection_summary_service.get_user_collection_summary_snapshot")
@patch("backend.db.services.collection_summary_service.refresh_user_collection_deltas")
@patch("backend.db.services.collection_summary_service.snapshot_user_portfolio_history")
@patch("backend.db.services.collection_summary_service.upsert_user_collection_summary")
@patch("backend.db.services.collection_summary_service.get_user_collection_summary")
def test_refresh_user_summary_with_history_and_deltas_runs_required_sequence(
    mock_get_summary,
    mock_upsert,
    mock_snapshot,
    mock_refresh_deltas,
    mock_get_snapshot,
):
    user_id = uuid4()
    call_order = []

    mock_get_summary.return_value = CollectionSummary(
        portfolio_value=100.0,
        cards_count=5,
        sealed_count=1,
        graded_count=0,
    )
    mock_upsert.side_effect = lambda *_args, **_kwargs: call_order.append("upsert")
    mock_snapshot.side_effect = lambda *_args, **_kwargs: call_order.append("snapshot")
    mock_refresh_deltas.side_effect = lambda *_args, **_kwargs: call_order.append("refresh_deltas")
    mock_get_snapshot.return_value = {"portfolio_value": 100.0, "row_found": True}

    result = refresh_user_summary_with_history_and_deltas(user_id)

    assert result == {"portfolio_value": 100.0, "row_found": True}
    assert call_order == ["upsert", "snapshot", "refresh_deltas"]
    mock_get_summary.assert_called_once_with(user_id)
    mock_upsert.assert_called_once_with(user_id, mock_get_summary.return_value.to_dict())
    mock_snapshot.assert_called_once_with(user_id)
    mock_refresh_deltas.assert_called_once_with(user_id)
    mock_get_snapshot.assert_called_once_with(user_id)


@patch("backend.db.services.collection_summary_service.snapshot_user_portfolio_history")
@patch("backend.db.services.collection_summary_service.upsert_user_collection_summary")
@patch("backend.db.services.collection_summary_service.get_user_collection_summary")
def test_refresh_user_summary_with_history_and_deltas_stops_when_summary_refresh_fails(
    mock_get_summary,
    mock_upsert,
    mock_snapshot,
):
    mock_get_summary.side_effect = RuntimeError("summary failed")

    try:
        refresh_user_summary_with_history_and_deltas(uuid4())
        assert False, "Expected RuntimeError"
    except RuntimeError as exc:
        assert "Failed to refresh summary" in str(exc)

    mock_upsert.assert_not_called()
    mock_snapshot.assert_not_called()


@patch("backend.db.services.collection_summary_service.refresh_user_collection_deltas")
@patch("backend.db.services.collection_summary_service.snapshot_user_portfolio_history")
@patch("backend.db.services.collection_summary_service.upsert_user_collection_summary")
@patch("backend.db.services.collection_summary_service.get_user_collection_summary")
def test_refresh_user_summary_with_history_and_deltas_stops_when_snapshot_fails(
    mock_get_summary,
    mock_upsert,
    mock_snapshot,
    mock_refresh_deltas,
):
    mock_get_summary.return_value = CollectionSummary(
        portfolio_value=50.0,
        cards_count=2,
        sealed_count=0,
        graded_count=0,
    )
    mock_snapshot.side_effect = RuntimeError("snapshot failed")

    try:
        refresh_user_summary_with_history_and_deltas(uuid4())
        assert False, "Expected RuntimeError"
    except RuntimeError as exc:
        assert "Failed to snapshot portfolio history" in str(exc)

    mock_refresh_deltas.assert_not_called()


@patch("backend.db.services.collection_summary_service.refresh_user_collection_deltas")
@patch("backend.db.services.collection_summary_service.snapshot_all_user_portfolio_history")
@patch("backend.db.services.collection_summary_service.has_stale_user_collection_summary_rows")
def test_run_daily_portfolio_reconciliation_all_users_success(
    mock_has_stale,
    mock_snapshot_all,
    mock_refresh_deltas,
):
    mock_has_stale.return_value = False

    result = run_daily_portfolio_reconciliation_all_users()

    assert result["status"] == "ok"
    assert result["summary_source_verified"] is True
    mock_snapshot_all.assert_called_once_with()
    mock_refresh_deltas.assert_called_once_with()


@patch("backend.db.services.collection_summary_service.snapshot_all_user_portfolio_history")
@patch("backend.db.services.collection_summary_service.has_stale_user_collection_summary_rows")
def test_run_daily_portfolio_reconciliation_all_users_fails_when_summary_source_is_stale(
    mock_has_stale,
    mock_snapshot_all,
):
    mock_has_stale.return_value = True

    try:
        run_daily_portfolio_reconciliation_all_users()
        assert False, "Expected RuntimeError"
    except RuntimeError as exc:
        assert "contains stale rows" in str(exc)

    mock_snapshot_all.assert_not_called()
