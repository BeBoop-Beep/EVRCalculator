# Portfolio Freshness - Testing & Validation Guide

This guide explains how to validate the portfolio freshness implementation and run all tests.

## Quick Start

### Prerequisites
```bash
# Python 3.9+
python --version

# Install backend dependencies (if not already installed)
cd backend
pip install -r requirements.txt

# Optional: Install testing dependencies
pip install pytest pytest-cov
```

### Run All Tests
```bash
cd backend
pytest tests/ -v
```

## What Was Implemented

The portfolio freshness implementation includes four execution paths:

1. **Nightly Scheduler** (3 AM daily) - Refreshes all users' portfolio summaries
2. **Fresh-on-Read Safety Net** - Checks freshness when dashboard is accessed
3. **Holdings Change Refresh** - Refreshes when user modifies holdings
4. **Batch Stale Refresh** - Explicitly refresh all stale summaries

## Test Organization

### Unit Tests (Service Layer)
```
backend/tests/unit/services/test_collection_freshness_service.py
├── TestEnsureFreshUserCollectionSummary (4 tests)
├── TestRefreshUserCollectionSummaryLive (3 tests)
├── TestRefreshAllStaleUserCollectionSummaries (3 tests)
└── TestRunNightlyPortfolioRefresh (4 tests)
```

**Run:** `pytest tests/unit/services/ -v`

**What it tests:**
- Service layer function calls
- Exception handling and logging
- Repository interaction
- Integration with DB layer

### Unit Tests (Scheduler)
```
backend/tests/unit/jobs/test_scheduler_service.py
├── TestSchedulerServiceWithAPScheduler (5 tests)
├── TestSchedulerServiceWithoutAPScheduler (2 tests)
└── TestNightlyPortfolioRefreshJob (2 tests)
```

**Run:** `pytest tests/unit/jobs/ -v`

**What it tests:**
- Scheduler initialization
- Job registration
- APScheduler availability handling
- Graceful degradation without APScheduler
- Job execution and error handling

### Integration Tests (End-to-End Flows)
```
backend/tests/unit/integration/test_freshness_integration.py
├── TestDashboardFreshnessFlow (2 tests)
├── TestManualRefreshEndpoint (1 test)
├── TestNightlySchedulerFlow (2 tests)
├── TestFreshnessRepositoryFunctions (3 tests)
└── TestErrorHandling (2 tests)
```

**Run:** `pytest tests/unit/integration/ -v`

**What it tests:**
- API endpoint freshness integration
- Scheduler startup/shutdown lifecycle
- Repository RPC calls
- Error propagation across layers

## Running Specific Test Groups

### By Category
```bash
# Only freshness service tests
pytest tests/unit/services/test_collection_freshness_service.py -v

# Only scheduler tests
pytest tests/unit/jobs/test_scheduler_service.py -v

# Only integration tests
pytest tests/unit/integration/test_freshness_integration.py -v
```

### By Test Class
```bash
# Test a specific class
pytest tests/unit/services/test_collection_freshness_service.py::TestEnsureFreshUserCollectionSummary -v

# Test a specific method
pytest tests/unit/services/test_collection_freshness_service.py::TestEnsureFreshUserCollectionSummary::test_success_calls_repo_function -v
```

### By Marker
```bash
# Run all tests marked as 'freshness'
pytest tests/ -m freshness -v

# Run all tests marked as 'scheduler'
pytest tests/ -m scheduler -v
```

## Extended Testing

### Generate Coverage Report
```bash
# Generate HTML coverage report
pytest tests/ --cov=backend.db.services.collection_freshness_service \
              --cov=backend.jobs.scheduler_service \
              --cov-report=html

# Open report in browser
start htmlcov/index.html  # Windows
open htmlcov/index.html   # macOS
```

### Run with Output Capture Disabled
```bash
# See all print() statements during test execution
pytest tests/ -v -s
```

### Run with Detailed Failure Output
```bash
# Show variables, assertions, and diff on failures
pytest tests/ -v --tb=long
```

### Run Specific Tests Only
```bash
# Run tests that match a name pattern
pytest tests/ -k "freshness" -v
pytest tests/ -k "scheduler" -v
pytest tests/ -k "dashboard" -v
```

## Validating the Implementation

### 1. Verify Implementation Files Exist
```bash
# Check scheduler service
ls backend/jobs/scheduler_service.py

# Check freshness service
ls backend/db/services/collection_freshness_service.py

# Check API modifications
grep -n "ensure_fresh_user_collection_summary" backend/api/main.py

# Check repository layer updates
grep -n "def ensure_fresh_user_collection_summary" backend/db/repositories/user_collection_summary_repository.py
```

### 2. Run Quick Syntax Check
```bash
# Check for obvious syntax errors
python -m py_compile backend/jobs/scheduler_service.py
python -m py_compile backend/db/services/collection_freshness_service.py
python -m py_compile backend/api/main.py
```

### 3. Verify API Starts Successfully
```bash
# This confirms all imports and dependencies work
cd backend
python -c "from api.main import app; print('✓ API initialization successful')"
```

### 4. Run All Tests
```bash
cd backend
pytest tests/unit/ -v --tb=short
```

### 5. Check Test Coverage
```bash
pytest tests/unit/ --cov=backend --cov-report=term-missing --co
```

## Expected Test Results

When all tests pass, you should see:
```
================================ 49 passed in 1.23s ================================
```

Each test group should show:
- **Service tests**: 14 passed
- **Scheduler tests**: 9 passed  
- **Integration tests**: 12 passed

## Interpreting Test Output

### Passing Test
```
test_success_calls_repo_function PASSED
```

### Failing Test
```
test_success_calls_repo_function FAILED
AssertionError: assert call_list == [...]
```

### Skipped Test
```
test_feature_requires_external_service SKIPPED
```

## Troubleshooting

### "ModuleNotFoundError: No module named 'backend'"
**Solution:** Run tests from the backend directory
```bash
cd backend
pytest tests/
```

### "No tests collected"
**Solution:** Ensure pytest is installed and test files are named `test_*.py`
```bash
pip install pytest
pytest tests/ --collect-only
```

### "APScheduler not found" (warning only, tests still pass)
**Solution:** Optional - install APScheduler for full scheduler testing
```bash
pip install apscheduler
```

### Tests timeout
**Solution:** Increase timeout for slower systems
```bash
pytest tests/ --timeout=30
```

## Continuous Integration

For CI/CD pipelines (GitHub Actions, GitLab CI, etc.):

```yaml
# Example: Run tests and generate coverage
- name: Run portfolio freshness tests
  run: |
    cd backend
    pip install pytest pytest-cov
    pytest tests/unit/ -v --cov=backend --cov-report=xml
```

## Next Steps

1. **Run tests locally** to verify implementation works
2. **Review test output** for any failures
3. **Check coverage report** to verify all paths are tested
4. **Deploy to staging** for integration testing
5. **Monitor API** for successful freshness check calls in production

## Documentation

For detailed information, see:
- [TESTING.md](./tests/TESTING.md) - Comprehensive test documentation
- [portfolio-freshness-implementation.md](./docs/portfolio-freshness-implementation.md) - Implementation details
- [DELIVERY_REPORT.md](./docs/DELIVERY_REPORT.md) - Complete delivery report

## Support

If tests fail:
1. Run the failing test with `-vv -s` flags for detailed output
2. Check the test docstring to understand what is being tested
3. Review the mock setup to ensure it matches the actual code
4. Verify all implementation files exist and are syntactically correct
5. Check API startup: `python -c "from api.main import app; print('OK')"`
