"""Contract checks for the scheduler wrapper infra/local/run_simulations.sh.

The wrapper cannot run under pytest (it needs bash + the VM environment), so we
assert its source contracts.

Checkout handling has exactly two paths:

* ``local`` (the default, and anything that is not "production") — purely
  informational. It logs branch/HEAD/working-tree state and continues. It can
  never refuse a run because of the branch name, a detached HEAD, dirty tracked
  files, or origin synchronization. A developer runs
  ``bash infra/local/run_simulations.sh`` from a feature branch with uncommitted
  changes and no environment variables at all.
* ``production`` — opt in with EVR_PUBLICATION_CHECKOUT_MODE=production. Strict,
  fail-closed: expected branch, HEAD == origin ref, clean tracked tree.

Everything after the checkout step (orchestrator, deferral, audit, exit codes) is
unchanged and still asserted here.
"""
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
SCRIPT = REPO_ROOT / "infra" / "local" / "run_simulations.sh"


@pytest.fixture(scope="module")
def script_text():
    # read_text normalizes CRLF, so multi-line anchors below stay valid.
    return SCRIPT.read_text(encoding="utf-8")


def _function_body(text: str, name: str) -> str:
    """Slice one shell function body, from its `name() {` to the closing brace."""
    start = text.index(f"{name}() {{")
    end = text.index("\n}\n", start)
    return text[start:end]


@pytest.fixture(scope="module")
def local_body(script_text):
    return _function_body(script_text, "log_local_checkout")


@pytest.fixture(scope="module")
def production_body(script_text):
    return _function_body(script_text, "verify_production_checkout")


# ---------------------------------------------------------------------------
# 1. Local mode is the default
# ---------------------------------------------------------------------------
def test_checkout_mode_defaults_to_local(script_text):
    assert 'EVR_PUBLICATION_CHECKOUT_MODE="${EVR_PUBLICATION_CHECKOUT_MODE:-local}"' in script_text


def test_dispatch_sends_only_production_down_the_strict_path(script_text):
    assert 'case "$EVR_PUBLICATION_CHECKOUT_MODE" in' in script_text
    assert "  production)\n    verify_production_checkout\n    ;;" in script_text
    assert "  *)\n    log_local_checkout\n    ;;" in script_text


def test_checkout_step_still_runs_before_any_work(script_text):
    assert 'esac\n\nnotify_slack "🚀 Simulation job started' in script_text


def test_only_an_invalid_repo_path_can_fail_the_checkout_step_locally(script_text):
    assert "repository path is not a Git worktree: $REPO_DIR" in script_text


# ---------------------------------------------------------------------------
# 2-5. Local mode refuses nothing
# ---------------------------------------------------------------------------
def test_local_mode_never_returns_a_failure(local_body):
    # No refusal, no nonzero return, no exit: the local path is informational.
    assert "return 2" not in local_body
    assert "REFUSED" not in local_body
    assert "exit" not in local_body
    assert "failure_reason" not in local_body
    assert local_body.rstrip().endswith("return 0")


def test_local_mode_accepts_any_branch(local_body):
    assert "EXPECTED_PUBLICATION_BRANCH" not in local_body
    assert "expected branch" not in local_body


def test_local_mode_accepts_a_detached_head(local_body):
    # The branch is only ever read for reporting, never validated.
    assert "detached HEAD is not a named branch" not in local_body
    assert 'ACTUAL_PUBLICATION_BRANCH=$(git symbolic-ref --short -q HEAD || true)' in local_body


def test_local_mode_accepts_tracked_working_tree_changes(local_body):
    # Dirtiness is recorded as state, never used as a failure condition.
    assert "tracked working-tree changes are present" not in local_body
    assert 'PUBLICATION_WORKING_TREE_STATE="modified"' in local_body
    assert 'PUBLICATION_WORKING_TREE_STATE="clean"' in local_body


def test_local_mode_ignores_untracked_files(local_body):
    assert "git status --porcelain --untracked-files=no" in local_body


def test_local_mode_never_compares_head_against_origin(local_body):
    assert "refs/remotes/origin" not in local_body
    assert "origin_sha" not in local_body
    assert "git fetch" not in local_body


def test_local_mode_requires_no_environment_override(local_body):
    assert "ALLOW_UNVERIFIED_PUBLICATION_CHECKOUT" not in local_body


def test_local_mode_logs_branch_head_and_working_tree_state(local_body):
    assert "[publication-checkout]" in local_body
    assert "mode=local" in local_body
    assert "branch=${ACTUAL_PUBLICATION_BRANCH:-detached}" in local_body
    assert "head=${PUBLICATION_HEAD_SHA:-unknown}" in local_body
    assert "working_tree=$PUBLICATION_WORKING_TREE_STATE" in local_body


# ---------------------------------------------------------------------------
# 6. Production mode keeps the strict guard
# ---------------------------------------------------------------------------
def test_expected_publication_branch_still_defaults_to_main(script_text):
    assert 'EXPECTED_PUBLICATION_BRANCH="${EXPECTED_PUBLICATION_BRANCH:-main}"' in script_text


def test_production_mode_requires_the_expected_branch(production_body):
    assert '"$ACTUAL_PUBLICATION_BRANCH" != "$EXPECTED_PUBLICATION_BRANCH"' in production_body
    assert "expected branch $EXPECTED_PUBLICATION_BRANCH but checkout is" in production_body


def test_production_mode_requires_head_to_match_origin(production_body):
    assert (
        'git rev-parse --verify --quiet "refs/remotes/origin/$EXPECTED_PUBLICATION_BRANCH"'
        in production_body
    )
    assert '"$head_sha" != "$origin_sha"' in production_body
    assert "does not match origin/$EXPECTED_PUBLICATION_BRANCH" in production_body


def test_production_mode_requires_a_clean_tracked_working_tree(production_body):
    assert '[ -n "$dirty_files" ]' in production_body
    assert "tracked working-tree changes are present" in production_body


def test_production_mode_still_rejects_a_detached_head(production_body):
    assert "${ACTUAL_PUBLICATION_BRANCH:-detached}" in production_body


def test_production_mode_keeps_optional_origin_fetch(production_body, script_text):
    assert 'PUBLICATION_FETCH_ORIGIN="${PUBLICATION_FETCH_ORIGIN:-0}"' in script_text
    assert '[ "$PUBLICATION_FETCH_ORIGIN" = "1" ]' in production_body
    assert 'git fetch --quiet origin "$EXPECTED_PUBLICATION_BRANCH"' in production_body


def test_production_mode_fails_closed_with_an_explicit_emergency_override(production_body, script_text):
    assert (
        'ALLOW_UNVERIFIED_PUBLICATION_CHECKOUT="${ALLOW_UNVERIFIED_PUBLICATION_CHECKOUT:-0}"'
        in script_text
    )
    assert 'if [ "$ALLOW_UNVERIFIED_PUBLICATION_CHECKOUT" = "1" ]' in production_body
    assert "REFUSED unsafe checkout" in production_body
    assert "return 2" in production_body


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------
def test_startup_notification_reports_mode_branch_commit_and_working_tree(script_text):
    assert (
        'notify_slack "🚀 Simulation job started\n'
        "Host: $HOSTNAME_VALUE\n"
        "Repo: $REPO_DIR\n"
        "Mode: $EVR_PUBLICATION_CHECKOUT_MODE\n"
        "Branch: ${ACTUAL_PUBLICATION_BRANCH:-detached}\n"
        "Commit: $(git rev-parse HEAD)\n"
        "Working tree: $PUBLICATION_WORKING_TREE_STATE\n" in script_text
    )


def test_a_modified_working_tree_is_informational_not_a_refusal(script_text):
    # The only place the state appears is reporting; it gates nothing.
    assert "$PUBLICATION_WORKING_TREE_STATE" in script_text
    assert 'if [ "$PUBLICATION_WORKING_TREE_STATE"' not in script_text


def test_every_job_notification_reports_the_actual_branch(script_text):
    branch_line = "Branch: ${ACTUAL_PUBLICATION_BRANCH:-detached}"
    # startup, completed, deferred, failed, audit-failed, override, refusal
    assert script_text.count(branch_line) >= 7, script_text.count(branch_line)


def test_notifications_never_report_the_expected_branch_as_the_actual_branch(script_text):
    assert "Branch: $EXPECTED_PUBLICATION_BRANCH" not in script_text


def test_wrapper_logs_commit_in_job_notifications(script_text):
    assert "Commit: $(git rev-parse HEAD)" in script_text


def test_wrapper_supports_isolated_production_checkout(script_text):
    assert 'REPO_DIR="${EVR_PRODUCTION_REPO_DIR:-/d/EVRCalculator}"' in script_text
    assert 'cd "$REPO_DIR"' in script_text


# ---------------------------------------------------------------------------
# 7. Unchanged coordinated workflow
# ---------------------------------------------------------------------------
def test_wrapper_captures_publication_exit_code(script_text):
    assert "PUBLICATION_EXIT=$?" in script_text


def test_wrapper_runs_the_coordinated_orchestrator_not_two_loose_commands(script_text):
    assert "run_daily_opening_publication.py" in script_text
    assert "python backend/scripts/run_all_v2_sets.py" not in script_text
    assert "python backend/scripts/refresh_stale_public_snapshots.py" not in script_text


def test_wrapper_passes_the_same_gate_wait_arguments(script_text):
    assert "--gate-wait-attempts 6 --gate-wait-seconds 600" in script_text


def test_wrapper_branches_on_deferred_exit_3(script_text):
    assert '"$PUBLICATION_EXIT" -eq 3' in script_text


def test_wrapper_sends_deferred_warning_not_success(script_text):
    assert "DEFERRED" in script_text
    assert "PUBLICATION_DEFERRED" in script_text
    assert 'PUBLICATION_EXIT" -eq 0' in script_text
    assert "Simulation + publication completed" in script_text


def test_wrapper_deferred_stays_non_successful(script_text):
    assert "PUBLICATION_DEFERRED=1" in script_text
    assert '"$PUBLICATION_DEFERRED" -ne 0' in script_text


def test_wrapper_runs_the_read_only_parity_audit_last(script_text):
    assert "audit_opening_analytics_publication.py" in script_text
    assert script_text.index("run_daily_opening_publication.py") < script_text.index(
        "audit_opening_analytics_publication.py"
    ), "the audit must run after publication, not before it"


def test_wrapper_keeps_publication_and_audit_results_independent(script_text):
    assert "PUBLICATION_FAILED=1" in script_text
    assert "PUBLICATION_DEFERRED=1" in script_text
    assert "AUDIT_EXIT=$?" in script_text
    assert '"$PUBLICATION_FAILED" -ne 0' in script_text
    assert '"$AUDIT_EXIT" -ne 0' in script_text


def test_a_failed_audit_keeps_the_job_visibly_unsuccessful(script_text):
    assert "Opening analytics publication audit FAILED" in script_text
    assert "logs/opening_analytics_audit.log" in script_text


def test_wrapper_includes_operator_action_and_log_path(script_text):
    assert "resolve/requeue the incomplete scrape batch" in script_text
    assert "logs/refresh_public_snapshots.log" in script_text


def test_final_exit_gate_is_unchanged(script_text):
    assert (
        'if [ "$PUBLICATION_FAILED" -ne 0 ] || [ "$PUBLICATION_DEFERRED" -ne 0 ] '
        '|| [ "$AUDIT_EXIT" -ne 0 ]; then\n  exit 1\nfi' in script_text
    )
