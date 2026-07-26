"""Contract checks for the scheduler wrapper infra/local/run_simulations.sh.

The wrapper cannot run under pytest (it needs bash + the VM environment), so we
assert the deferred-publication contract at the source level: a closed gate
(exit 3) must produce a distinct DEFERRED warning, keep the task non-successful,
and stay independent of the simulation-batch result.
"""

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
SCRIPT = REPO_ROOT / "infra" / "local" / "run_simulations.sh"


@pytest.fixture(scope="module")
def script_text():
    return SCRIPT.read_text(encoding="utf-8")


def test_wrapper_captures_refresh_exit_code(script_text):
    # Exit code captured without tripping `set -e`.
    assert "REFRESH_EXIT=$?" in script_text
    assert "refresh_stale_public_snapshots.py --commit --strict" in script_text


def test_wrapper_branches_on_deferred_exit_3(script_text):
    assert '"$REFRESH_EXIT" -eq 3' in script_text


def test_wrapper_sends_deferred_warning_not_success(script_text):
    # Distinct DEFERRED message, and it greps the machine-readable marker.
    assert "DEFERRED" in script_text
    assert "PUBLICATION_DEFERRED" in script_text
    # The success message must be gated behind exit 0 only.
    assert 'REFRESH_EXIT" -eq 0' in script_text
    assert "Public snapshot refresh completed" in script_text


def test_wrapper_deferred_stays_non_successful(script_text):
    # A deferral flips REFRESH_DEFERRED, which forces the final nonzero exit.
    assert "REFRESH_DEFERRED=1" in script_text
    assert '"$REFRESH_DEFERRED" -ne 0' in script_text


def test_wrapper_keeps_simulation_and_refresh_results_independent(script_text):
    # Simulation failure and publication deferral are tracked separately.
    assert "SIMULATIONS_FAILED" in script_text
    assert "REFRESH_FAILED=1" in script_text
    assert "REFRESH_DEFERRED=1" in script_text
    # Final gate considers all three independently.
    assert '"$SIMULATIONS_FAILED" -ne 0' in script_text


def test_wrapper_includes_operator_action_and_log_path(script_text):
    assert "resolve/requeue the incomplete scrape batch" in script_text
    assert "logs/refresh_public_snapshots.log" in script_text
