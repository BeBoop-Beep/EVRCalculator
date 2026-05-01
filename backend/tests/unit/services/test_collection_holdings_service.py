"""Unit tests for collection_holdings_service.py"""

from __future__ import annotations

from uuid import uuid4
from unittest.mock import MagicMock, patch

import pytest

from backend.db.services.collection_holdings_service import mutate_holding


@pytest.fixture
def sample_user_id():
    """Generate a sample user UUID string."""
    return str(uuid4())


@pytest.fixture
def sample_holding_id():
    """Generate a sample holding UUID string."""
    return str(uuid4())


class TestMutateHoldingIncrement:
    """Tests for mutate_holding with increment action."""

    def test_increment_calls_refresh_wrapper(self, sample_user_id, sample_holding_id):
        """After increment, should call refresh_user_portfolio_summary_and_deltas."""
        with patch(
            "backend.db.services.collection_holdings_service.get_holding"
        ) as mock_get, patch(
            "backend.db.services.collection_holdings_service.update_holding_quantity"
        ) as mock_update, patch(
            "backend.db.services.collection_holdings_service.refresh_user_portfolio_summary_and_deltas"
        ) as mock_refresh:
            
            # Setup: holding exists with quantity 5
            mock_get.return_value = {"quantity": "5"}
            
            result, error = mutate_holding(
                user_id=sample_user_id,
                holding_type="card",
                holding_id=sample_holding_id,
                action="increment",
            )
            
            # Verify success
            assert error is None
            assert result["action"] == "incremented"
            assert result["quantity"] == 6
            
            # Verify refresh was called with user UUID
            mock_refresh.assert_called_once()
            call_args = mock_refresh.call_args[0]
            # Call args: (UUID(user_id), snapshot_date)
            # The user_id string is converted to UUID by the function
            assert str(call_args[0]) == sample_user_id

    def test_increment_continues_on_refresh_failure(self, sample_user_id, sample_holding_id):
        """Increment should succeed even if refresh fails (non-fatal)."""
        with patch(
            "backend.db.services.collection_holdings_service.get_holding"
        ) as mock_get, patch(
            "backend.db.services.collection_holdings_service.update_holding_quantity"
        ) as mock_update, patch(
            "backend.db.services.collection_holdings_service.refresh_user_portfolio_summary_and_deltas"
        ) as mock_refresh, patch(
            "backend.db.services.collection_holdings_service.logger"
        ) as mock_logger:
            
            # Setup: holding exists, refresh will fail
            mock_get.return_value = {"quantity": "5"}
            mock_refresh.side_effect = RuntimeError("DB connection failed")
            
            result, error = mutate_holding(
                user_id=sample_user_id,
                holding_type="card",
                holding_id=sample_holding_id,
                action="increment",
            )
            
            # Verify increment succeeded
            assert error is None
            assert result["action"] == "incremented"
            assert result["quantity"] == 6
            
            # Verify error was logged (but mutation still returned success)
            mock_logger.exception.assert_called_once()


class TestMutateHoldingDecrement:
    """Tests for mutate_holding with decrement action."""

    def test_decrement_calls_refresh_wrapper(self, sample_user_id, sample_holding_id):
        """After decrement, should call refresh_user_portfolio_summary_and_deltas."""
        with patch(
            "backend.db.services.collection_holdings_service.get_holding"
        ) as mock_get, patch(
            "backend.db.services.collection_holdings_service.update_holding_quantity"
        ) as mock_update, patch(
            "backend.db.services.collection_holdings_service.refresh_user_portfolio_summary_and_deltas"
        ) as mock_refresh:
            
            # Setup: holding exists with quantity 5
            mock_get.return_value = {"quantity": "5"}
            
            result, error = mutate_holding(
                user_id=sample_user_id,
                holding_type="card",
                holding_id=sample_holding_id,
                action="decrement",
            )
            
            # Verify success
            assert error is None
            assert result["action"] == "decremented"
            assert result["quantity"] == 4
            
            # Verify refresh was called
            mock_refresh.assert_called_once()

    def test_decrement_fails_at_quantity_one(self, sample_user_id, sample_holding_id):
        """Decrement should fail at quantity 1 (must use remove)."""
        with patch(
            "backend.db.services.collection_holdings_service.get_holding"
        ) as mock_get, patch(
            "backend.db.services.collection_holdings_service.refresh_user_portfolio_summary_and_deltas"
        ) as mock_refresh:
            
            # Setup: holding exists with quantity 1
            mock_get.return_value = {"quantity": "1"}
            
            result, error = mutate_holding(
                user_id=sample_user_id,
                holding_type="card",
                holding_id=sample_holding_id,
                action="decrement",
            )
            
            # Verify error
            assert result is None
            assert error is not None
            assert error["status"] == 422
            assert "remove" in error["message"].lower()
            
            # Verify refresh was NOT called (action failed before refresh)
            mock_refresh.assert_not_called()


class TestMutateHoldingRemove:
    """Tests for mutate_holding with remove action."""

    def test_remove_calls_refresh_wrapper(self, sample_user_id, sample_holding_id):
        """After remove, should call refresh_user_portfolio_summary_and_deltas."""
        with patch(
            "backend.db.services.collection_holdings_service.get_holding"
        ) as mock_get, patch(
            "backend.db.services.collection_holdings_service.delete_holding"
        ) as mock_delete, patch(
            "backend.db.services.collection_holdings_service.refresh_user_portfolio_summary_and_deltas"
        ) as mock_refresh:
            
            # Setup: holding exists
            mock_get.return_value = {"quantity": "3"}
            mock_delete.return_value = True
            
            result, error = mutate_holding(
                user_id=sample_user_id,
                holding_type="card",
                holding_id=sample_holding_id,
                action="remove",
            )
            
            # Verify success
            assert error is None
            assert result["action"] == "removed"
            
            # Verify refresh was called
            mock_refresh.assert_called_once()

    def test_remove_continues_on_refresh_failure(self, sample_user_id, sample_holding_id):
        """Remove should succeed even if refresh fails (non-fatal)."""
        with patch(
            "backend.db.services.collection_holdings_service.get_holding"
        ) as mock_get, patch(
            "backend.db.services.collection_holdings_service.delete_holding"
        ) as mock_delete, patch(
            "backend.db.services.collection_holdings_service.refresh_user_portfolio_summary_and_deltas"
        ) as mock_refresh, patch(
            "backend.db.services.collection_holdings_service.logger"
        ) as mock_logger:
            
            # Setup: holding will be deleted, but refresh fails
            mock_get.return_value = {"quantity": "3"}
            mock_delete.return_value = True
            mock_refresh.side_effect = RuntimeError("DB connection failed")
            
            result, error = mutate_holding(
                user_id=sample_user_id,
                holding_type="card",
                holding_id=sample_holding_id,
                action="remove",
            )
            
            # Verify remove succeeded
            assert error is None
            assert result["action"] == "removed"
            
            # Verify error was logged
            mock_logger.exception.assert_called_once()


class TestMutateHoldingInputValidation:
    """Tests for input validation in mutate_holding."""

    def test_rejects_unauthenticated_user(self, sample_holding_id):
        """Should reject when user_id is empty."""
        result, error = mutate_holding(
            user_id="",
            holding_type="card",
            holding_id=sample_holding_id,
            action="increment",
        )
        
        assert result is None
        assert error is not None
        assert error["status"] == 401
        assert "authenticated" in error["message"].lower()

    def test_rejects_invalid_holding_type(self, sample_user_id, sample_holding_id):
        """Should reject invalid holding_type."""
        result, error = mutate_holding(
            user_id=sample_user_id,
            holding_type="invalid_type",
            holding_id=sample_holding_id,
            action="increment",
        )
        
        assert result is None
        assert error is not None
        assert error["status"] == 400

    def test_rejects_invalid_action(self, sample_user_id, sample_holding_id):
        """Should reject invalid action."""
        result, error = mutate_holding(
            user_id=sample_user_id,
            holding_type="card",
            holding_id=sample_holding_id,
            action="invalid_action",
        )
        
        assert result is None
        assert error is not None
        assert error["status"] == 400

    def test_rejects_missing_holding_id(self, sample_user_id):
        """Should reject when holding_id is empty."""
        result, error = mutate_holding(
            user_id=sample_user_id,
            holding_type="card",
            holding_id="",
            action="increment",
        )
        
        assert result is None
        assert error is not None
        assert error["status"] == 400

    def test_rejects_nonexistent_holding(self, sample_user_id, sample_holding_id):
        """Should reject when holding doesn't exist or access denied."""
        with patch(
            "backend.db.services.collection_holdings_service.get_holding"
        ) as mock_get:
            mock_get.return_value = None
            
            result, error = mutate_holding(
                user_id=sample_user_id,
                holding_type="card",
                holding_id=sample_holding_id,
                action="increment",
            )
            
            assert result is None
            assert error is not None
            assert error["status"] == 404


class TestMutateHoldingAllTypes:
    """Tests for all holding types to ensure consistency boundary works."""

    @pytest.mark.parametrize("holding_type", ["card", "sealed_product", "graded_card"])
    def test_all_holding_types_call_refresh(self, sample_user_id, sample_holding_id, holding_type):
        """All holding types should call refresh after increment."""
        with patch(
            "backend.db.services.collection_holdings_service.get_holding"
        ) as mock_get, patch(
            "backend.db.services.collection_holdings_service.update_holding_quantity"
        ) as mock_update, patch(
            "backend.db.services.collection_holdings_service.refresh_user_portfolio_summary_and_deltas"
        ) as mock_refresh:
            
            mock_get.return_value = {"quantity": "1"}
            
            result, error = mutate_holding(
                user_id=sample_user_id,
                holding_type=holding_type,
                holding_id=sample_holding_id,
                action="increment",
            )
            
            assert error is None
            assert result["action"] == "incremented"
            # Verify refresh was called for each type
            mock_refresh.assert_called_once()
