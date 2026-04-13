"""Unit tests for scheduler_service.py"""

from __future__ import annotations

import logging
from datetime import time
from unittest.mock import MagicMock, patch, call

import pytest


class TestSchedulerServiceImports:
    """Tests for scheduler service imports and setup."""

    def test_scheduler_service_imports_successfully(self):
        """Scheduler service should import without errors."""
        try:
            from backend.jobs import scheduler_service
            assert scheduler_service is not None
        except ImportError:
            pytest.fail("scheduler_service failed to import")

    def test_has_apscheduler_flag_is_boolean(self):
        """HAS_APSCHEDULER should be a boolean flag."""
        from backend.jobs.scheduler_service import HAS_APSCHEDULER
        assert isinstance(HAS_APSCHEDULER, bool)

    def test_initialize_scheduler_function_exists(self):
        """initialize_scheduler function should exist."""
        from backend.jobs.scheduler_service import initialize_scheduler
        assert callable(initialize_scheduler)

    def test_stop_scheduler_function_exists(self):
        """stop_scheduler function should exist."""
        from backend.jobs.scheduler_service import stop_scheduler
        assert callable(stop_scheduler)

    def test_run_nightly_function_exists(self):
        """_run_nightly_portfolio_refresh function should exist."""
        from backend.jobs.scheduler_service import _run_nightly_portfolio_refresh
        assert callable(_run_nightly_portfolio_refresh)


class TestSchedulerServiceWithoutAPScheduler:
    """Tests for graceful degradation when APScheduler is not available."""

    def test_initialize_scheduler_returns_none_without_apscheduler(self):
        """initialize_scheduler should return None if APScheduler unavailable."""
        with patch("backend.jobs.scheduler_service.HAS_APSCHEDULER", False):
            # Need to reload module to pick up new HAS_APSCHEDULER value
            import sys
            import importlib
            from backend.jobs import scheduler_service
            
            # Save original _scheduler
            original_scheduler = scheduler_service._scheduler
            try:
                # Clear global scheduler
                scheduler_service._scheduler = None
                result = scheduler_service.initialize_scheduler()
                assert result is None
            finally:
                # Restore original
                scheduler_service._scheduler = original_scheduler

    def test_stop_scheduler_handles_missing_apscheduler(self):
        """stop_scheduler should handle missing APScheduler gracefully."""
        from backend.jobs.scheduler_service import stop_scheduler
        
        # Should not raise exception
        try:
            stop_scheduler()
        except ModuleNotFoundError:
            pytest.fail("stop_scheduler raised ModuleNotFoundError")


class TestNightlyPortfolioRefreshJob:
    """Tests for the _run_nightly_portfolio_refresh job function."""

    def test_nightly_job_function_signature(self):
        """_run_nightly_portfolio_refresh should have correct signature."""
        from backend.jobs.scheduler_service import _run_nightly_portfolio_refresh
        import inspect
        
        sig = inspect.signature(_run_nightly_portfolio_refresh)
        # Should take no parameters
        assert len(sig.parameters) == 0

    def test_nightly_job_calls_collection_summary_service(self):
        """_run_nightly_portfolio_refresh should invoke collection_summary_service."""
        with patch("backend.db.services.collection_summary_service.run_daily_portfolio_reconciliation_all_users") as mock_service:
            from backend.jobs.scheduler_service import _run_nightly_portfolio_refresh
            
            _run_nightly_portfolio_refresh()
            
            mock_service.assert_called_once()

    def test_nightly_job_exception_handling(self):
        """_run_nightly_portfolio_refresh should log exceptions without crashing."""
        with patch(
            "backend.db.services.collection_summary_service.run_daily_portfolio_reconciliation_all_users",
            side_effect=Exception("Service failed")
        ), patch("backend.jobs.scheduler_service.logger") as mock_logger:
            from backend.jobs.scheduler_service import _run_nightly_portfolio_refresh
            
            # Should not raise exception
            _run_nightly_portfolio_refresh()
            
            # Should log the error
            assert mock_logger.exception.called or mock_logger.error.called


class TestSchedulerServiceFunctionality:
    """Tests for scheduler service core functionality."""

    @pytest.fixture(autouse=True)
    def reset_scheduler(self):
        """Reset global scheduler state before each test."""
        from backend.jobs import scheduler_service
        original = scheduler_service._scheduler
        scheduler_service._scheduler = None
        yield
        scheduler_service._scheduler = original

    def test_initialize_scheduler_default_time(self):
        """initialize_scheduler should use 3 AM by default."""
        from backend.jobs.scheduler_service import initialize_scheduler
        import inspect
        
        sig = inspect.signature(initialize_scheduler)
        default_time = sig.parameters['nightly_refresh_time'].default
        
        assert default_time == time(3, 0, 0)

    def test_logger_is_configured(self):
        """Logger should be configured in scheduler_service."""
        from backend.jobs.scheduler_service import logger
        
        assert logger is not None
        assert isinstance(logger, logging.Logger)
