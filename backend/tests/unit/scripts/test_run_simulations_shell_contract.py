"""Contract checks for the scheduler wrapper infra/local/run_simulations.sh.

The wrapper cannot run under pytest (it needs bash + the VM environment), so we
assert its fail-closed source contracts: unsafe checkouts must be rejected before
simulation/publication, and a closed publication gate must remain a distinct
non-successful outcome.
"""
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
SCRIPT = REPO_ROOT / "infra" / "local" / "run_simulations.sh"


@pytest.fixture(scope="module")
def script_text():
    return SCRIPT.read_text(encoding="utf-8")


def test_wrapper_supports_isolated_production_checkout(script_text):
    assert 'REPO_DIR="${EVR_PRODUCTION_REPO_DIR:-/d/EVRCalculator}"' in script_text
    assert 'cd "$REPO_DIR"' in script_text


def test_wrapper_verifies_main_clean_and_synced_before_work(script_text):
    assert "verify_publication_checkout" in script_text
    assert 'EXPECTED_PUBLICATION_BRANCH="${EXPECTED_PUBLICATION_BRANCH:-main}"' in script_text
    assert "git symbolic-ref --short -q HEAD" in script_text
    assert 'refs/remotes/origin/$EXPECTED_PUBLICATION_BRANCH' in script_text
    assert 'git status --porcelain --untracked-files=no' in script_text
    assert 'verify_publication_checkout\n\nnotify_slack "🚀 Simulation job started' in script_text


def test_wrapper_checkout_guard_fails_closed_with_explicit_emergency_override(script_text):
    assert 'ALLOW_UNVERIFIED_PUBLICATION_CHECKOUT="${ALLOW_UNVERIFIED_PUBLICATION_CHECKOUT:-0}"' in script_text
    assert 'if [ "$ALLOW_UNVERIFIED_PUBLICATION_CHECKOUT" = "1" ]' in script_text
    assert "REFUSED unsafe checkout" in script_text
    assert "return 2" in script_text


def test_wrapper_can_optionally_fetch_origin_before_verification(script_text):
    assert 'PUBLICATION_FETCH_ORIGIN="${PUBLICATION_FETCH_ORIGIN:-0}"' in script_text
    assert 'git fetch --quiet origin "$EXPECTED_PUBLICATION_BRANCH"' in script_text


def test_wrapper_logs_commit_in_job_notifications(script_text):
    assert "[publication-checkout]" in script_text
    assert "Commit: $(git rev-parse HEAD)" in script_text


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
