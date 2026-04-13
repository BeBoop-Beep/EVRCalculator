"""
Pytest configuration for backend tests.

Configures pytest with fixtures, markers, and plugins for running unit and integration tests.
"""

import pytest
import sys
from pathlib import Path

# Add backend to path so imports work
BACKEND_PATH = Path(__file__).parent.parent.parent / "backend"
sys.path.insert(0, str(BACKEND_PATH))


def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line(
        "markers", "unit: mark test as a unit test"
    )
    config.addinivalue_line(
        "markers", "integration: mark test as an integration test"
    )
    config.addinivalue_line(
        "markers", "freshness: mark test as related to portfolio freshness"
    )
    config.addinivalue_line(
        "markers", "scheduler: mark test as related to background scheduler"
    )


@pytest.fixture(scope="session")
def test_settings():
    """Provide test settings for all tests."""
    return {
        "test_user_id": "00000000-0000-0000-0000-000000000000",
        "timeout_seconds": 5,
    }
