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
            "backend.db.services.collection_freshness_service.repo_run_nightly"
        ) as mock_repo:
            run_nightly_portfolio_refresh()
            mock_repo.assert_called_once()

    def test_success_logs_info(self, mock_logger):
        """Should log info on success."""
        with patch(
            "backend.db.services.collection_freshness_service.repo_run_nightly"
        ):
            run_nightly_portfolio_refresh()
            mock_logger.info.assert_called_once()
            call_args = mock_logger.info.call_args[0]
            assert "nightly" in call_args[0].lower()

    def test_exception_handling(self, mock_logger):
        """Should log exception and reraise."""
        test_error = RuntimeError("Nightly reconciliation failed")
        with patch(
            "backend.db.services.collection_freshness_service.repo_run_nightly",
            side_effect=test_error,
        ):
            with pytest.raises(RuntimeError):
                run_nightly_portfolio_refresh()
            mock_logger.exception.assert_called_once()

    def test_handles_timeout_error(self, mock_logger):
        """Should handle timeout exceptions gracefully."""
        test_error = TimeoutError("Query timeout")
        with patch(
            "backend.db.services.collection_freshness_service.repo_run_nightly",
            side_effect=test_error,
        ):
            with pytest.raises(TimeoutError):
                run_nightly_portfolio_refresh()
