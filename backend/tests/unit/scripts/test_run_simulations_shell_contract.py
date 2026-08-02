"""Contract checks for the scheduler wrapper infra/local/run_simulations.sh.

The wrapper cannot run under pytest (it needs bash + the VM environment), so we
assert its source contracts.

Checkout verification has two modes:

* ``current_branch`` (default) — local development runs from whatever branch is
  actually checked out. No branch-name equality check, no origin comparison.
* ``production`` — unchanged fail-closed behavior: the checkout must be the
  expected branch, in sync with its origin ref, and clean.

Everything after verification (orchestrator, deferral, audit, exit codes) is
unchanged and still asserted here.
"""
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
SCRIPT = REPO_ROOT / "infra" / "local" / "run_simulations.sh"

PRODUCTION_MARKER = "# [checkout-mode:production]"
CURRENT_BRANCH_MARKER = "# [checkout-mode:current_branch]"
END_MARKER = "# [checkout-mode:end]"


@pytest.fixture(scope="module")
def script_text():
    # read_text normalizes CRLF, so multi-line anchors below stay valid.
    return SCRIPT.read_text(encoding="utf-8")


def _block(text: str, start: str, end: str) -> str:
    start_index = text.index(start)
    end_index = text.index(end, start_index)
    return text[start_index:end_index]


@pytest.fixture(scope="module")
def production_block(script_text):
    return _block(script_text, PRODUCTION_MARKER, CURRENT_BRANCH_MARKER)


@pytest.fixture(scope="module")
def current_branch_block(script_text):
    return _block(script_text, CURRENT_BRANCH_MARKER, END_MARKER)


# ---------------------------------------------------------------------------
# Repo location + mode selection
# ---------------------------------------------------------------------------
def test_wrapper_supports_isolated_production_checkout(script_text):
    assert 'REPO_DIR="${EVR_PRODUCTION_REPO_DIR:-/d/EVRCalculator}"' in script_text
    assert 'cd "$REPO_DIR"' in script_text


def test_checkout_mode_defaults_to_current_branch(script_text):
    assert (
        'EVR_PUBLICATION_CHECKOUT_MODE="${EVR_PUBLICATION_CHECKOUT_MODE:-current_branch}"'
        in script_text
    )


def test_both_checkout_modes_are_dispatched_explicitly(script_text):
    assert PRODUCTION_MARKER in script_text
    assert CURRENT_BRANCH_MARKER in script_text
    assert END_MARKER in script_text
    assert script_text.index(PRODUCTION_MARKER) < script_text.index(CURRENT_BRANCH_MARKER)


def test_an_unknown_checkout_mode_fails_closed(script_text):
    # A typo like "prod" must not silently fall through to the permissive mode.
    assert "unknown EVR_PUBLICATION_CHECKOUT_MODE" in script_text


def test_the_checkout_guard_still_runs_before_any_work(script_text):
    assert 'verify_publication_checkout\n\nnotify_slack "🚀 Simulation job started' in script_text


# ---------------------------------------------------------------------------
# current_branch mode
# ---------------------------------------------------------------------------
def test_current_branch_mode_detects_the_branch_dynamically(script_text):
    assert 'ACTUAL_PUBLICATION_BRANCH="$(git symbolic-ref --short -q HEAD || true)"' in script_text
    assert "ACTUAL_PUBLICATION_BRANCH=$(git symbolic-ref --short -q HEAD || true)" in script_text


def test_current_branch_mode_accepts_any_named_branch(current_branch_block):
    # No branch-name equality check at all: a feature branch is a valid checkout.
    assert "EXPECTED_PUBLICATION_BRANCH" not in current_branch_block
    assert "expected branch" not in current_branch_block


def test_current_branch_mode_never_compares_head_against_an_origin_ref(current_branch_block):
    assert "refs/remotes/origin" not in current_branch_block
    assert "origin_sha" not in current_branch_block
    assert "does not match origin" not in current_branch_block


def test_current_branch_mode_still_rejects_detached_head(current_branch_block):
    assert '[ -z "$ACTUAL_PUBLICATION_BRANCH" ]' in current_branch_block
    assert "detached HEAD" in current_branch_block


def test_current_branch_mode_still_requires_a_clean_tracked_working_tree(current_branch_block):
    assert '[ -n "$dirty_files" ]' in current_branch_block
    assert "tracked working-tree changes are present" in current_branch_block


def test_current_branch_mode_does_not_fetch_origin(script_text):
    # The fetch is gated on production mode, so a local run makes no network call.
    assert (
        'if [ "$EVR_PUBLICATION_CHECKOUT_MODE" = "production" ] '
        '&& [ "$PUBLICATION_FETCH_ORIGIN" = "1" ]; then' in script_text
    )


def test_untracked_files_are_still_ignored(script_text):
    assert "git status --porcelain --untracked-files=no" in script_text


# ---------------------------------------------------------------------------
# production mode
# ---------------------------------------------------------------------------
def test_expected_publication_branch_still_defaults_to_main(script_text):
    assert 'EXPECTED_PUBLICATION_BRANCH="${EXPECTED_PUBLICATION_BRANCH:-main}"' in script_text


def test_production_mode_requires_the_expected_branch(production_block):
    assert '"$ACTUAL_PUBLICATION_BRANCH" != "$EXPECTED_PUBLICATION_BRANCH"' in production_block
    assert "expected branch $EXPECTED_PUBLICATION_BRANCH but checkout is" in production_block


def test_production_mode_requires_head_to_match_origin(production_block):
    assert 'refs/remotes/origin/$EXPECTED_PUBLICATION_BRANCH' in production_block
    assert '"$head_sha" != "$origin_sha"' in production_block
    assert "does not match origin/$EXPECTED_PUBLICATION_BRANCH" in production_block


def test_production_mode_resolves_the_origin_ref_without_echoing_it_back(production_block):
    # Plain `git rev-parse <ref>` prints the ref itself on stdout when it cannot
    # resolve it, which made origin_sha a bogus non-empty string, killed the
    # "unable to resolve" branch, and logged a fake SHA. --verify prints nothing.
    assert (
        'git rev-parse --verify --quiet "refs/remotes/origin/$EXPECTED_PUBLICATION_BRANCH"'
        in production_block
    )
    assert "unable to resolve refs/remotes/origin/$EXPECTED_PUBLICATION_BRANCH" in production_block


def test_production_mode_requires_a_clean_tracked_working_tree(production_block):
    assert '[ -n "$dirty_files" ]' in production_block
    assert "tracked working-tree changes are present" in production_block


def test_production_mode_keeps_optional_origin_fetch(script_text):
    assert 'PUBLICATION_FETCH_ORIGIN="${PUBLICATION_FETCH_ORIGIN:-0}"' in script_text
    assert 'git fetch --quiet origin "$EXPECTED_PUBLICATION_BRANCH"' in script_text


# ---------------------------------------------------------------------------
# Emergency override + refusal, unchanged
# ---------------------------------------------------------------------------
def test_wrapper_checkout_guard_fails_closed_with_explicit_emergency_override(script_text):
    assert (
        'ALLOW_UNVERIFIED_PUBLICATION_CHECKOUT="${ALLOW_UNVERIFIED_PUBLICATION_CHECKOUT:-0}"'
        in script_text
    )
    assert 'if [ "$ALLOW_UNVERIFIED_PUBLICATION_CHECKOUT" = "1" ]' in script_text
    assert "REFUSED unsafe checkout" in script_text
    assert "return 2" in script_text


# ---------------------------------------------------------------------------
# Branch reporting
# ---------------------------------------------------------------------------
def test_checkout_log_reports_the_actual_branch_and_mode(script_text):
    assert "[publication-checkout]" in script_text
    assert 'mode=$EVR_PUBLICATION_CHECKOUT_MODE' in script_text
    assert 'branch=${ACTUAL_PUBLICATION_BRANCH:-detached}' in script_text


def test_every_job_notification_reports_the_actual_branch(script_text):
    branch_line = "Branch: ${ACTUAL_PUBLICATION_BRANCH:-detached}"
    # startup, completed, deferred, failed, audit-failed, override, refusal
    assert script_text.count(branch_line) >= 7, script_text.count(branch_line)


def test_notifications_no_longer_hardcode_the_expected_branch_as_the_actual_branch(script_text):
    assert "Branch: $EXPECTED_PUBLICATION_BRANCH" not in script_text


def test_wrapper_logs_commit_in_job_notifications(script_text):
    assert "Commit: $(git rev-parse HEAD)" in script_text


# ---------------------------------------------------------------------------
# Unchanged coordinated workflow
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
