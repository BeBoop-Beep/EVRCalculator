"""Unit tests for collection_freshness_service.py"""

from __future__ import annotations

import logging
from uuid import UUID, uuid4
from unittest.mock import MagicMock, patch, call

import pytest

from backend.db.services.collection_freshness_service import (
    ensure_fresh_user_collection_summary,
    refresh_user_collection_summary_live,
    refresh_all_stale_user_collection_summaries,
    run_nightly_portfolio_refresh,
    refresh_user_portfolio_summary_and_deltas,
)


@pytest.fixture
def sample_user_id():
    """Generate a sample user UUID."""
    return uuid4()


@pytest.fixture
def mock_logger():
    """Provide a mock logger."""
    with patch("backend.db.services.collection_freshness_service.logger") as mock:
        yield mock


class TestEnsureFreshUserCollectionSummary:
    """Tests for ensure_fresh_user_collection_summary."""

    def test_success_calls_repo_function(self, sample_user_id, mock_logger):
        """ensure_fresh_user_collection_summary should call repo function with correct user_id."""
        with patch(
            "backend.db.services.collection_freshness_service.repo_ensure_fresh"
        ) as mock_repo:
            ensure_fresh_user_collection_summary(sample_user_id)
            mock_repo.assert_called_once_with(sample_user_id)

    def test_success_logs_info(self, sample_user_id, mock_logger):
        """ensure_fresh_user_collection_summary should log info on success."""
        with patch(
            "backend.db.services.collection_freshness_service.repo_ensure_fresh"
        ):
            ensure_fresh_user_collection_summary(sample_user_id)
            mock_logger.info.assert_called_once()
            call_args = mock_logger.info.call_args[0]
            assert "ensure_fresh" in call_args[0]
            assert sample_user_id in call_args

    def test_repo_exception_logs_exception_and_raises(self, sample_user_id, mock_logger):
        """ensure_fresh_user_collection_summary should log exception and reraise."""
        test_error = RuntimeError("DB connection failed")
        with patch(
            "backend.db.services.collection_freshness_service.repo_ensure_fresh",
            side_effect=test_error,
        ):
            with pytest.raises(RuntimeError):
                ensure_fresh_user_collection_summary(sample_user_id)
            mock_logger.exception.assert_called_once()

    def test_handles_various_exceptions(self, sample_user_id):
        """ensure_fresh_user_collection_summary should handle various exception types."""
        exceptions = [
            RuntimeError("DB error"),
            ValueError("Invalid user"),
            Exception("Unknown error"),
        ]
        for exc in exceptions:
            with patch(
                "backend.db.services.collection_freshness_service.repo_ensure_fresh",
                side_effect=exc,
            ):
                with pytest.raises(type(exc)):
                    ensure_fresh_user_collection_summary(sample_user_id)


class TestRefreshUserCollectionSummaryLive:
    """Tests for refresh_user_collection_summary_live."""

    def test_success_calls_repo_function(self, sample_user_id, mock_logger):
        """Should call repo function with correct user_id."""
        with patch(
            "backend.db.services.collection_freshness_service.repo_refresh_live"
        ) as mock_repo:
            refresh_user_collection_summary_live(sample_user_id)
            mock_repo.assert_called_once_with(sample_user_id)

    def test_success_logs_info(self, sample_user_id, mock_logger):
        """Should log info on success."""
        with patch(
            "backend.db.services.collection_freshness_service.repo_refresh_live"
        ):
            refresh_user_collection_summary_live(sample_user_id)
            mock_logger.info.assert_called_once()
            call_args = mock_logger.info.call_args[0]
            assert "refresh_live" in call_args[0]

    def test_exception_handling(self, sample_user_id, mock_logger):
        """Should log exception and reraise."""
        test_error = RuntimeError("Stale summary check failed")
        with patch(
            "backend.db.services.collection_freshness_service.repo_refresh_live",
            side_effect=test_error,
        ):
            with pytest.raises(RuntimeError):
                refresh_user_collection_summary_live(sample_user_id)
            mock_logger.exception.assert_called_once()


class TestRefreshAllStaleUserCollectionSummaries:
    """Tests for refresh_all_stale_user_collection_summaries."""

    def test_success_calls_repo_function(self, mock_logger):
        """Should call repo function."""
        with patch(
            "backend.db.services.collection_freshness_service.repo_refresh_all_stale"
        ) as mock_repo:
            refresh_all_stale_user_collection_summaries()
            mock_repo.assert_called_once()

    def test_success_logs_info(self, mock_logger):
        """Should log info on success."""
        with patch(
            "backend.db.services.collection_freshness_service.repo_refresh_all_stale"
        ):
            refresh_all_stale_user_collection_summaries()
            mock_logger.info.assert_called_once()

    def test_exception_handling(self, mock_logger):
        """Should log exception and reraise."""
        test_error = RuntimeError("Batch refresh failed")
        with patch(
            "backend.db.services.collection_freshness_service.repo_refresh_all_stale",
            side_effect=test_error,
        ):
            with pytest.raises(RuntimeError):
                refresh_all_stale_user_collection_summaries()
            mock_logger.exception.assert_called_once()


class TestRunNightlyPortfolioRefresh:
    """Tests for run_nightly_portfolio_refresh."""

    def test_success_calls_repo_function(self, mock_logger):
        """Should call repo function."""
        with patch(
            "backend.db.services.collection_freshness_service.run_daily_portfolio_reconciliation_all_users"
        ) as mock_repo:
            mock_repo.return_value = {
                "status": "ok",
                "snapshot_all_users_executed": True,
                "delta_refresh_all_users_executed": True,
                "pricing_freshness": {"is_fresh": True, "check_completed": True, "timings_ms": {"total_ms": 1.0}},
            }
            run_nightly_portfolio_refresh()
            mock_repo.assert_called_once()

    def test_success_logs_info(self, mock_logger):
        """Should log info on success."""
        with patch(
            "backend.db.services.collection_freshness_service.run_daily_portfolio_reconciliation_all_users"
        ) as mock_service:
            mock_service.return_value = {
                "status": "ok",
                "snapshot_all_users_executed": True,
                "delta_refresh_all_users_executed": True,
                "pricing_freshness": {"is_fresh": True, "check_completed": True, "timings_ms": {"total_ms": 1.0}},
            }
            result = run_nightly_portfolio_refresh()
            mock_logger.info.assert_called_once()
            call_args = mock_logger.info.call_args[0]
            assert "nightly" in call_args[0].lower()
            assert result["pricing_freshness"]["is_fresh"] is True

    def test_exception_handling(self, mock_logger):
        """Should log exception and reraise."""
        test_error = RuntimeError("Nightly reconciliation failed")
        with patch(
            "backend.db.services.collection_freshness_service.run_daily_portfolio_reconciliation_all_users",
            side_effect=test_error,
        ):
            with pytest.raises(RuntimeError):
                run_nightly_portfolio_refresh()
            mock_logger.exception.assert_called_once()

    def test_handles_timeout_error(self, mock_logger):
        """Should handle timeout exceptions gracefully."""
        test_error = TimeoutError("Query timeout")
        with patch(
            "backend.db.services.collection_freshness_service.run_daily_portfolio_reconciliation_all_users",
            side_effect=test_error,
        ):
            with pytest.raises(TimeoutError):
                run_nightly_portfolio_refresh()

    def test_returns_skipped_status_when_pricing_is_incomplete(self, mock_logger):
        """Should surface skipped snapshot status and pricing freshness payload."""
        with patch(
            "backend.db.services.collection_freshness_service.run_daily_portfolio_reconciliation_all_users"
        ) as mock_service:
            mock_service.return_value = {
                "status": "skipped",
                "summary_source_verified": True,
                "snapshot_all_users_executed": False,
                "delta_refresh_all_users_executed": False,
                "pricing_freshness": {
                    "is_fresh": False,
                    "check_completed": True,
                    "timings_ms": {"total_ms": 9.0},
                    "warning": "Pricing freshness incomplete for snapshot_date=2026-04-25; missing_or_stale_assets=1. Nightly snapshot skipped.",
                },
                "warning": "Pricing freshness incomplete for snapshot_date=2026-04-25; missing_or_stale_assets=1. Nightly snapshot skipped.",
            }

            result = run_nightly_portfolio_refresh(current_date="2026-04-25")

            assert result["status"] == "skipped"
            assert result["nightly_refresh_executed"] is False
            assert result["pricing_freshness"]["is_fresh"] is False
            mock_service.assert_called_once_with(current_date="2026-04-25")

    def test_returns_incomplete_status_when_freshness_check_cannot_complete(self, mock_logger):
        """Should surface incomplete freshness failures without snapshot execution."""
        with patch(
            "backend.db.services.collection_freshness_service.run_daily_portfolio_reconciliation_all_users"
        ) as mock_service:
            mock_service.return_value = {
                "status": "incomplete",
                "summary_source_verified": True,
                "snapshot_all_users_executed": False,
                "delta_refresh_all_users_executed": False,
                "pricing_freshness": {
                    "is_fresh": False,
                    "check_completed": False,
                    "timings_ms": {"total_ms": 12.0},
                    "warning": "Pricing freshness check could not complete for snapshot_date=2026-04-25; nightly snapshot skipped.",
                },
                "warning": "Pricing freshness check could not complete for snapshot_date=2026-04-25; nightly snapshot skipped.",
            }

            result = run_nightly_portfolio_refresh(current_date="2026-04-25")

            assert result["status"] == "incomplete"
            assert result["nightly_refresh_executed"] is False
            assert result["pricing_freshness"]["check_completed"] is False


class TestRefreshUserPortfolioSummaryAndDeltas:
    """Tests for refresh_user_portfolio_summary_and_deltas (consistency boundary wrapper)."""

    def test_success_calls_repo_function(self, sample_user_id, mock_logger):
        """Should call repo function with correct user_id."""
        with patch(
            "backend.db.services.collection_freshness_service.repo_refresh_summary_and_deltas"
        ) as mock_repo:
            refresh_user_portfolio_summary_and_deltas(sample_user_id)
            mock_repo.assert_called_once_with(sample_user_id, None)

    def test_success_calls_repo_with_snapshot_date(self, sample_user_id, mock_logger):
        """Should call repo function with snapshot_date when provided."""
        with patch(
            "backend.db.services.collection_freshness_service.repo_refresh_summary_and_deltas"
        ) as mock_repo:
            refresh_user_portfolio_summary_and_deltas(sample_user_id, snapshot_date="2026-04-25")
            mock_repo.assert_called_once_with(sample_user_id, "2026-04-25")

    def test_success_logs_info(self, sample_user_id, mock_logger):
        """Should log info on success."""
        with patch(
            "backend.db.services.collection_freshness_service.repo_refresh_summary_and_deltas"
        ):
            refresh_user_portfolio_summary_and_deltas(sample_user_id)
            mock_logger.info.assert_called_once()
            call_args = mock_logger.info.call_args[0]
            assert "refresh_summary_and_deltas" in call_args[0]
            assert sample_user_id in call_args

    def test_logs_snapshot_date_in_info(self, sample_user_id, mock_logger):
        """Should include snapshot_date in log when provided."""
        with patch(
            "backend.db.services.collection_freshness_service.repo_refresh_summary_and_deltas"
        ):
            refresh_user_portfolio_summary_and_deltas(sample_user_id, snapshot_date="2026-04-25")
            mock_logger.info.assert_called_once()
            call_args = mock_logger.info.call_args[0]
            assert "2026-04-25" in str(call_args)

    def test_logs_default_for_missing_snapshot_date(self, sample_user_id, mock_logger):
        """Should log '(default)' when snapshot_date is None."""
        with patch(
            "backend.db.services.collection_freshness_service.repo_refresh_summary_and_deltas"
        ):
            refresh_user_portfolio_summary_and_deltas(sample_user_id)
            mock_logger.info.assert_called_once()
            call_args = mock_logger.info.call_args[0]
            assert "(default)" in str(call_args)

    def test_exception_handling(self, sample_user_id, mock_logger):
        """Should log exception and reraise."""
        test_error = RuntimeError("Consistency boundary refresh failed")
        with patch(
            "backend.db.services.collection_freshness_service.repo_refresh_summary_and_deltas",
            side_effect=test_error,
        ):
            with pytest.raises(RuntimeError):
                refresh_user_portfolio_summary_and_deltas(sample_user_id)
            mock_logger.exception.assert_called_once()

    def test_handles_various_exceptions(self, sample_user_id):
        """Should handle various exception types."""
        exceptions = [
            RuntimeError("DB error"),
            ValueError("Invalid snapshot_date"),
            Exception("Unknown error"),
        ]
        for exc in exceptions:
            with patch(
                "backend.db.services.collection_freshness_service.repo_refresh_summary_and_deltas",
                side_effect=exc,
            ):
                with pytest.raises(type(exc)):
                    refresh_user_portfolio_summary_and_deltas(sample_user_id)
