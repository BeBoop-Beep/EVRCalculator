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


def test_wrapper_captures_publication_exit_code(script_text):
    # Exit code captured without tripping `set -e`.
    assert "PUBLICATION_EXIT=$?" in script_text


def test_wrapper_runs_the_coordinated_orchestrator_not_two_loose_commands(script_text):
    # Simulation generation and snapshot publication used to be two independent
    # commands with nothing reconciling them, which let a stopped simulation
    # batch coexist with advancing market snapshots. One orchestrator now owns
    # the order and the verification between them.
    assert "run_daily_opening_publication.py" in script_text
    # The wrapper must not invoke the two underlying steps directly any more —
    # that would bypass the verification between them.
    assert "python backend/scripts/run_all_v2_sets.py" not in script_text
    assert "python backend/scripts/refresh_stale_public_snapshots.py" not in script_text


def test_wrapper_branches_on_deferred_exit_3(script_text):
    assert '"$PUBLICATION_EXIT" -eq 3' in script_text


def test_wrapper_sends_deferred_warning_not_success(script_text):
    # Distinct DEFERRED message, and it greps the machine-readable marker.
    assert "DEFERRED" in script_text
    assert "PUBLICATION_DEFERRED" in script_text
    # The success message must be gated behind exit 0 only.
    assert 'PUBLICATION_EXIT" -eq 0' in script_text
    assert "Simulation + publication completed" in script_text


def test_wrapper_deferred_stays_non_successful(script_text):
    # A deferral flips PUBLICATION_DEFERRED, which forces the final nonzero exit.
    assert "PUBLICATION_DEFERRED=1" in script_text
    assert '"$PUBLICATION_DEFERRED" -ne 0' in script_text


def test_wrapper_runs_the_read_only_parity_audit_last(script_text):
    # The audit re-reads what was actually published; it is the tripwire for a
    # frozen Opening Profit vs Cost series behind a fresh market date.
    assert "audit_opening_analytics_publication.py" in script_text
    assert script_text.index("run_daily_opening_publication.py") < script_text.index(
        "audit_opening_analytics_publication.py"
    ), "the audit must run after publication, not before it"


def test_wrapper_keeps_publication_and_audit_results_independent(script_text):
    assert "PUBLICATION_FAILED=1" in script_text
    assert "PUBLICATION_DEFERRED=1" in script_text
    assert "AUDIT_EXIT=$?" in script_text
    # Final gate considers all three independently.
    assert '"$PUBLICATION_FAILED" -ne 0' in script_text
    assert '"$AUDIT_EXIT" -ne 0' in script_text


def test_a_failed_audit_keeps_the_job_visibly_unsuccessful(script_text):
    assert "Opening analytics publication audit FAILED" in script_text
    assert "logs/opening_analytics_audit.log" in script_text


def test_wrapper_includes_operator_action_and_log_path(script_text):
    assert "resolve/requeue the incomplete scrape batch" in script_text
    assert "logs/refresh_public_snapshots.log" in script_text
