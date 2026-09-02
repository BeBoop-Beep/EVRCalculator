"""The unattended publication path: active local checkout, three-way success.

TWO CONTRACTS THIS FILE PINS
----------------------------
1. The Windows scheduled task must run the repository the developer actually
   uses at ``D:\\EVRCalculator``. This project intentionally advances one active
   feature branch at a time, so branch name, HEAD, and working-tree state are
   diagnostics for the unattended run rather than checkout gates. The task must
   never switch branches, stash/reset work, or require a second hard-coded
   production worktree.

2. Success is gated on all publication audits, not opening-analytics freshness
   alone. A scoring-version regression moves no timestamp and changes no market
   date, so the public RIP audit remains an independent success condition.

Neither script can run under pytest, so these are source contracts.
"""

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
SCRIPT = REPO_ROOT / "infra" / "local" / "run_simulations.sh"
TASK_BAT = REPO_ROOT / "infra" / "local" / "run_simulations_task.bat"


@pytest.fixture(scope="module")
def script_text():
    return SCRIPT.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def task_bat():
    return TASK_BAT.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# The canonical public RIP audit
# ---------------------------------------------------------------------------

def test_wrapper_runs_the_public_rip_audit(script_text):
    assert (
        "python -m backend.scripts.audit_public_rip_leaderboard_publication --json"
        in script_text
    )
    assert "logs/public_rip_audit.log" in script_text


def test_public_rip_audit_uses_its_own_exit_variable(script_text):
    assert "PUBLIC_RIP_AUDIT_EXIT=0" in script_text
    assert "|| PUBLIC_RIP_AUDIT_EXIT=$?" in script_text
    # Never conflated with the opening-analytics audit's variable.
    assert "AUDIT_EXIT=$PUBLIC_RIP_AUDIT_EXIT" not in script_text
    assert "PUBLIC_RIP_AUDIT_EXIT=$AUDIT_EXIT" not in script_text


def test_public_rip_audit_failure_sends_a_distinct_message(script_text):
    marker = "Canonical public RIP leaderboard audit FAILED"
    assert marker in script_text
    failure = script_text[script_text.index(marker) :]
    failure = failure[: failure.index('"\nfi')]
    assert "Branch: ${ACTUAL_PUBLICATION_BRANCH:-detached}" in failure
    assert "Commit: $(git rev-parse HEAD)" in failure
    assert "Exit: $PUBLIC_RIP_AUDIT_EXIT" in failure
    assert "Canonical versions expected:" in failure
    assert "logs/public_rip_audit.log" in failure


def test_the_canonical_versions_named_in_the_message_are_the_real_ones(script_text):
    """The shell restates four version strings; they must be THE four."""
    from backend.desirability.collector_appeal import COLLECTOR_APPEAL_V4_VERSION
    from backend.desirability.scoring_config import (
        CANONICAL_FINANCIAL_RIP_VERSION,
        CANONICAL_OVERALL_RIP_VERSION,
        canonical_public_rip_contract_version,
    )

    for version in (
        CANONICAL_FINANCIAL_RIP_VERSION,
        COLLECTOR_APPEAL_V4_VERSION,
        CANONICAL_OVERALL_RIP_VERSION,
        canonical_public_rip_contract_version(),
    ):
        assert version in script_text


# ---------------------------------------------------------------------------
# The three-way success gate
# ---------------------------------------------------------------------------

def test_success_requires_all_three_results(script_text):
    assert (
        'if [ "$PUBLICATION_EXIT" -eq 0 ] && [ "$AUDIT_EXIT" -eq 0 ] '
        '&& [ "$PUBLIC_RIP_AUDIT_EXIT" -eq 0 ]; then' in script_text
    )


def test_only_one_success_notification_exists(script_text):
    assert script_text.count("✅") == 1


@pytest.mark.parametrize(
    ("publication", "audit", "public_rip", "expected"),
    [
        (0, 0, 0, True),
        # THE regression: a passing opening-analytics audit cannot produce
        # success while the public RIP audit fails.
        (0, 0, 1, False),
        (0, 1, 0, False),
        (1, 0, 0, False),
        (0, 1, 1, False),
        (1, 1, 1, False),
    ],
)
def test_success_condition_evaluated_over_every_combination(
    script_text, publication, audit, public_rip, expected
):
    """Evaluates the ACTUAL shell condition, not a restatement of it.

    The condition is sliced out of the script and each `[ "$X" -eq 0 ]` test is
    substituted with its truth value, so a future edit that drops one of the
    three conjuncts fails here instead of shipping.
    """
    # The LAST occurrence: an earlier `if [ "$PUBLICATION_EXIT" -eq 0 ]` is the
    # block that deliberately WITHHOLDS the success notification until the
    # audits have run.
    marker = 'if [ "$PUBLICATION_EXIT" -eq 0 ] && [ "$AUDIT_EXIT" -eq 0 ]'
    condition = script_text[script_text.rindex(marker) + 3 :]
    condition = condition[: condition.index("; then")]
    expression = (
        condition.replace('[ "$PUBLICATION_EXIT" -eq 0 ]', str(publication == 0))
        .replace('[ "$AUDIT_EXIT" -eq 0 ]', str(audit == 0))
        .replace('[ "$PUBLIC_RIP_AUDIT_EXIT" -eq 0 ]', str(public_rip == 0))
        .replace("&&", "and")
        .strip()
    )
    assert eval(expression) is expected  # noqa: S307 - expression is script-derived


def test_a_failing_public_rip_audit_exits_nonzero(script_text):
    gate = script_text[script_text.index('if [ "$PUBLICATION_FAILED" -ne 0 ]') :]
    assert "PUBLIC_RIP_AUDIT_EXIT" in gate[: gate.index("exit 1")]


# ---------------------------------------------------------------------------
# The Windows scheduled entry point runs the active local checkout
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("EVR_PUBLICATION_CHECKOUT_MODE", "local"),
        ("PUBLICATION_FETCH_ORIGIN", "0"),
        ("EVR_PRODUCTION_REPO_DIR", "/d/EVRCalculator"),
    ],
)
def test_scheduled_task_runs_the_active_local_checkout(task_bat, name, value):
    assert 'set "' + name + "=" + value + '"' in task_bat


def test_scheduled_task_does_not_pin_a_branch_or_checkout_override(task_bat):
    assert 'set "EXPECTED_PUBLICATION_BRANCH=' not in task_bat
    assert 'set "ALLOW_UNVERIFIED_PUBLICATION_CHECKOUT=' not in task_bat


def test_scheduled_task_uses_the_development_checkout(task_bat):
    assert 'set "EVR_PRODUCTION_WINDOWS_DIR=D:\\EVRCalculator"' in task_bat
    assert 'set "EVR_PRODUCTION_REPO_DIR=/d/EVRCalculator"' in task_bat
    assert "EVRCalculator-production" not in task_bat
    assert 'cd /d "%EVR_PRODUCTION_WINDOWS_DIR%"' in task_bat
    invocation = task_bat[task_bat.index("bash.exe") :]
    invocation = invocation[: invocation.index("\n")]
    assert "%EVR_PRODUCTION_REPO_DIR%" in invocation


def test_scheduled_task_refuses_only_a_missing_configured_repository(task_bat):
    assert 'if not exist "%EVR_PRODUCTION_WINDOWS_DIR%"' in task_bat
    assert "Repository missing: %EVR_PRODUCTION_WINDOWS_DIR%" in task_bat
    assert "exit /b 2" in task_bat
    assert "Refusing to fall back to the development checkout." not in task_bat


def test_local_scheduler_does_not_fetch_or_compare_origin(task_bat):
    assert 'set "PUBLICATION_FETCH_ORIGIN=0"' in task_bat
    assert 'set "PUBLICATION_FETCH_ORIGIN=1"' not in task_bat
    assert "git fetch" not in task_bat
    assert "origin/main" not in task_bat


def test_production_override_remains_available_on_the_manual_shell_path(script_text):
    """Scheduler local mode does not remove the optional manual production path."""
    assert (
        'ALLOW_UNVERIFIED_PUBLICATION_CHECKOUT="${ALLOW_UNVERIFIED_PUBLICATION_CHECKOUT:-0}"'
        in script_text
    )
    assert 'if [ "$ALLOW_UNVERIFIED_PUBLICATION_CHECKOUT" = "1" ]' in script_text


@pytest.mark.parametrize(
    "forbidden", ["git checkout", "git stash", "git reset", "git clean", "git pull"]
)
def test_scheduled_task_never_mutates_a_checkout(task_bat, forbidden):
    assert forbidden not in task_bat


def test_scheduled_task_propagates_the_real_exit_code(task_bat):
    """`echo` resets ERRORLEVEL, so it must be captured immediately."""
    assert 'set "RUN_EXIT=%ERRORLEVEL%"' in task_bat
    assert "exit /b %RUN_EXIT%" in task_bat
    body = task_bat[task_bat.index("run_simulations.sh") :]
    assert body.index('set "RUN_EXIT=%ERRORLEVEL%"') < body.index("echo Task finished")


# ---------------------------------------------------------------------------
# Fail-closed startup checks and environment provenance
# ---------------------------------------------------------------------------

def test_wrapper_refuses_a_missing_repository_directory(script_text):
    assert 'if [ ! -d "$REPO_DIR" ]; then' in script_text
    # Checked BEFORE the cd, or `set -e` aborts with no message at all and the
    # Task Scheduler log shows an empty run.
    assert script_text.index('if [ ! -d "$REPO_DIR" ]') < script_text.index('cd "$REPO_DIR"')


def test_wrapper_refuses_a_missing_virtual_environment(script_text):
    assert "if [ ! -f backend/.venv/Scripts/activate ]; then" in script_text
    assert "no virtual environment at $REPO_DIR/backend/.venv" in script_text


def test_production_mode_dispatch_is_explicitly_fail_closed(script_text):
    assert "verify_production_checkout || exit $?" in script_text


def test_local_mode_is_the_scheduler_compatible_default(script_text):
    assert 'EVR_PUBLICATION_CHECKOUT_MODE="${EVR_PUBLICATION_CHECKOUT_MODE:-local}"' in script_text
    assert "  *)\n    log_local_checkout\n    ;;" in script_text


def test_local_checkout_logs_branch_head_and_dirty_state_without_gating(script_text):
    body = script_text[script_text.index("log_local_checkout()") :]
    body = body[: body.index("verify_production_checkout()")]
    assert "ACTUAL_PUBLICATION_BRANCH=$(git symbolic-ref --short -q HEAD || true)" in body
    assert "PUBLICATION_HEAD_SHA=$(git rev-parse HEAD 2>/dev/null || true)" in body
    assert "git status --porcelain --untracked-files=no" in body
    assert "[publication-checkout] mode=local" in body
    assert "return 0" in body
    assert "EXPECTED_PUBLICATION_BRANCH" not in body


def test_wrapper_logs_environment_provenance_without_secrets(script_text):
    assert "[publication-environment]" in script_text
    assert "python=$(command -v python)" in script_text
    assert "supabase_project=${SUPABASE_PROJECT_REF:-unknown}" in script_text
    # The project ref is an identifier that appears in every request URL. No
    # key, token or connection string is ever echoed.
    assert "SUPABASE_SERVICE_ROLE_KEY" not in script_text
    assert "SUPABASE_KEY" not in script_text
    assert "SUPABASE_ANON" not in script_text


@pytest.mark.parametrize(
    "field",
    ["repo=$REPO_DIR", "branch=", "expected_branch=$EXPECTED_PUBLICATION_BRANCH",
     "head=", "origin_sha=", "working_tree=$PUBLICATION_WORKING_TREE_STATE"],
)
def test_optional_production_checkout_line_reports_every_required_field(script_text, field):
    line = script_text[script_text.index("[publication-checkout] mode=production") :]
    line = line[: line.index('"\n')]
    assert field in line
