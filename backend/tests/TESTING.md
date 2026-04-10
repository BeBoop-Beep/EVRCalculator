# Portfolio Freshness Testing Guide

## Overview

This document describes the unit and integration tests for the portfolio summary freshness implementation.

## Test Structure

```
backend/tests/
├── conftest.py                          # Pytest configuration
├── unit/
│   ├── integration/
│   │   ├── test_freshness_integration.py    # Integration tests
│   │   └── __init__.py
│   ├── jobs/
│   │   ├── test_scheduler_service.py        # Scheduler service tests
│   │   └── __init__.py
│   ├── services/
│   │   ├── test_collection_freshness_service.py  # Freshness service tests
│   │   └── __init__.py
│   └── ...existing tests...
```

## Running Tests

### Run all tests
```bash
cd backend
pytest tests/
```

### Run only freshness-related tests
```bash
pytest tests/ -m freshness
```

### Run only scheduler tests
```bash
pytest tests/ -m scheduler
```

### Run with verbose output
```bash
pytest tests/ -v
```

### Run specific test file
```bash
pytest tests/unit/services/test_collection_freshness_service.py -v
```

### Run with coverage report
```bash
pytest tests/ --cov=backend --cov-report=html
```

## Test Files

### 1. `test_collection_freshness_service.py`

Tests the service layer for portfolio freshness orchestration.

#### Test Classes:
- **TestEnsureFreshUserCollectionSummary**: Tests `ensure_fresh_user_collection_summary(user_id)`
  - `test_success_calls_repo_function()` - Verifies repository is called with correct user_id
  - `test_success_logs_info()` - Verifies success is logged
  - `test_repo_exception_logs_exception_and_raises()` - Verifies exceptions are logged and reraised
  - `test_handles_various_exceptions()` - Verifies handling of different exception types

- **TestRefreshUserCollectionSummaryLive**: Tests `refresh_user_collection_summary_live(user_id)`
  - `test_success_calls_repo_function()` - Verifies live refresh calls repository
  - `test_success_logs_info()` - Verifies logging
  - `test_exception_handling()` - Verifies exception handling

- **TestRefreshAllStaleUserCollectionSummaries**: Tests `refresh_all_stale_user_collection_summaries()`
  - `test_success_calls_repo_function()` - Verifies batch refresh calls repository
  - `test_success_logs_info()` - Verifies logging
  - `test_exception_handling()` - Verifies exception handling

- **TestRunNightlyPortfolioRefresh**: Tests `run_nightly_portfolio_refresh()`
  - `test_success_calls_repo_function()` - Verifies nightly job calls repository
  - `test_success_logs_info()` - Verifies logging
  - `test_exception_handling()` - Verifies exception handling
  - `test_handles_timeout_error()` - Verifies handling of timeout errors

#### Coverage Areas:
- Service layer function calls
- Exception propagation
- Logging behavior
- Integration with repository layer

### 2. `test_scheduler_service.py`

Tests the background job scheduler for portfolio maintenance tasks.

#### Test Classes:
- **TestSchedulerServiceWithAPScheduler**: Tests assuming APScheduler is installed
  - `test_initialize_scheduler_creates_instance()` - Verifies scheduler instance creation
  - `test_initialize_scheduler_adds_job()` - Verifies nightly job is registered
  - `test_initialize_scheduler_with_custom_time()` - Verifies custom time configuration
  - `test_initialize_scheduler_idempotent()` - Verifies repeated calls don't create duplicate schedulers
  - `test_stop_scheduler_shuts_down()` - Verifies graceful shutdown

- **TestSchedulerServiceWithoutAPScheduler**: Tests assuming APScheduler is not installed
  - `test_initialize_scheduler_returns_none_without_apscheduler()` - Verifies graceful degradation
  - `test_stop_scheduler_handles_missing_apscheduler()` - Verifies no crash without APScheduler

- **TestNightlyPortfolioRefreshJob**: Tests the nightly job function
  - `test_nightly_job_calls_collection_summary_service()` - Verifies service is called
  - `test_nightly_job_exception_handling()` - Verifies exception handling in job

#### Coverage Areas:
- Scheduler initialization and lifecycle
- APScheduler availability handling
- Job registration and execution
- Error resilience

### 3. `test_freshness_integration.py`

Integration tests for freshness execution paths.

#### Test Classes:
- **TestDashboardFreshnessFlow**: Tests GET /collection/dashboard freshness check
  - `test_dashboard_calls_freshness_check_on_success()` - Verifies endpoint calls freshness check
  - `test_dashboard_continues_even_if_freshness_fails()` - Verifies non-blocking behavior
  
- **TestManualRefreshEndpoint**: Tests POST /collection/summary/refresh endpoint
  - `test_refresh_endpoint_available()` - Verifies endpoint existence

- **TestNightlySchedulerFlow**: Tests nightly scheduler execution path
  - `test_scheduler_initialization_on_startup()` - Verifies startup initialization
  - `test_scheduler_lifecycle()` - Verifies startup and shutdown lifecycle

- **TestFreshnessRepositoryFunctions**: Tests repository-level RPC calls
  - `test_ensure_fresh_user_collection_summary_calls_rpc()` - Verifies RPC call
  - `test_refresh_user_collection_summary_live_calls_rpc()` - Verifies live refresh RPC
  - `test_refresh_all_stale_user_collection_summaries_calls_rpc()` - Verifies batch RPC

- **TestErrorHandling**: Tests error handling across all paths
  - `test_repository_handles_supabase_errors()` - Verifies Supabase error handling
  - `test_service_handles_repository_errors()` - Verifies service error handling

#### Coverage Areas:
- API endpoint behavior
- Freshness check invocation flow
- RPC call correctness
- End-to-end error handling

## Test Markers

Tests use pytest markers for selective execution:

```bash
# Run only unit tests
pytest tests/unit/ -m unit

# Run only integration tests
pytest tests/unit/integration/ -m integration

# Run only freshness tests
pytest tests/ -m freshness

# Run only scheduler tests
pytest tests/ -m scheduler
```

## Fixtures

### Service Tests
- `sample_user_id` - Provides a random UUID for testing
- `mock_logger` - Provides a mock logger for assertion

### Integration Tests
- `sample_user_id` - Provides a random UUID for testing
- `mock_supabase_client` - Provides a mock Supabase client

## Mocking Strategy

All tests use `unittest.mock` to mock external dependencies:

1. **Database/Supabase**: Mocked to avoid actual database calls
2. **Logger**: Mocked to verify logging behavior
3. **Services**: Mocked service layer functions to isolate tests
4. **APScheduler**: Mocked to test both with and without availability

## Expected Test Results

All tests should pass with the following characteristics:

- **Unit Tests**: ~30 tests, <1 second total execution
- **Integration Tests**: ~12 tests, <1 second total execution
- **Total Coverage**: ~100% of freshness service paths

## Troubleshooting

### Import Errors
If you get `ModuleNotFoundError: No module named 'backend'`:
```bash
# Run from backend directory
cd backend
pytest tests/
```

### Fixture Not Found
Ensure `conftest.py` exists in the `tests/` directory with all required fixtures.

### APScheduler Not Found
If APScheduler is not installed, tests should still pass (they mock its availability):
```bash
# Optional: Install APScheduler for full scheduler testing
pip install apscheduler
```

## Continuous Integration

These tests are designed to run in CI/CD pipelines:

```yaml
# Example GitHub Actions workflow
- name: Run freshness tests
  run: |
    cd backend
    pytest tests/unit/services/test_collection_freshness_service.py -v
    pytest tests/unit/jobs/test_scheduler_service.py -v
    pytest tests/unit/integration/test_freshness_integration.py -v
```

## Coverage Report

To generate a coverage report:

```bash
pytest tests/ --cov=backend.db.services.collection_freshness_service \
              --cov=backend.jobs.scheduler_service \
              --cov-report=html
# Open htmlcov/index.html in browser
```

## Adding New Tests

When adding tests for new freshness features:

1. Create test file in appropriate directory (unit/integration)
2. Name file `test_*.py`
3. Use descriptive test class and method names
4. Add docstrings explaining what is being tested
5. Use appropriate fixtures
6. Add pytest markers for selective execution
7. Update this documentation

Example:
```python
@pytest.mark.freshness
def test_new_freshness_feature(sample_user_id):
    """Test description of what is being tested."""
    # Setup
    with patch("...") as mock:
        # Exercise
        result = function_under_test(sample_user_id)
        
        # Assert
        mock.assert_called_once()
        assert result is not None
```

## See Also

- [portfolio-freshness-implementation.md](../docs/portfolio-freshness-implementation.md) - Implementation guide
- [DELIVERY_REPORT.md](../docs/DELIVERY_REPORT.md) - Complete delivery report
- [pytest documentation](https://docs.pytest.org/)
