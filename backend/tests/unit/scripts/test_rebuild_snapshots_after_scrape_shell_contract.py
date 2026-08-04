"""Contract checks for the VM post-scrape wrapper.

``backend/scripts/rebuild_snapshots_after_scrape.sh`` is what the 6:00 AM Phoenix
cron actually calls. It cannot run under pytest (it needs bash, the VM venv, and
a live database), so its source contracts are asserted here instead.

The contracts exist because of a real production failure: on August 4 the batch
promoted cleanly and the set page advanced, while Explore Top Rankings and Sealed
Market stayed on August 3. The wrapper must therefore delegate the ENTIRE
publication order to the canonical orchestrator — never call individual builders,
never publish around the gate — and then prove the result with the post-scrape
market audit before it may exit zero.
"""
from pathlib import Path
import shutil
import subprocess

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
SCRIPT = REPO_ROOT / "backend" / "scripts" / "rebuild_snapshots_after_scrape.sh"

REFRESH = "backend/scripts/refresh_stale_public_snapshots.py"
AUDIT = "backend/scripts/audit_pokemon_market_publication.py"


@pytest.fixture(scope="module")
def script_text():
    # read_text normalizes CRLF, so multi-line anchors below stay valid.
    return SCRIPT.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def script_code(script_text):
    """Executable lines only.

    The header comment names the flags this wrapper must NOT use, and explains
    why. Absence checks have to run against real commands, not that explanation.
    """
    return "\n".join(
        line for line in script_text.splitlines() if not line.lstrip().startswith("#")
    )


def test_the_wrapper_is_tracked_in_the_repository():
    """A VM-only script is unreviewable and undeployable. This one is tracked."""
    assert SCRIPT.exists(), f"{SCRIPT} must exist so the VM cron target is under review"


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash unavailable")
def test_shell_syntax_is_valid():
    result = subprocess.run(
        ["bash", "-n", str(SCRIPT)], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr


def test_uses_strict_shell_mode(script_text):
    assert "set -euo pipefail" in script_text


def test_resolves_repo_root_and_venv_from_the_script_location(script_text):
    assert 'SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"' in script_text
    assert 'REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"' in script_text
    assert '${REPO_ROOT}/.venv/bin/python' in script_text


def test_uses_the_phoenix_market_date(script_text):
    """A run that slips past midnight UTC must still target the promoted date."""
    assert 'MARKET_DATE="$(TZ=America/Phoenix date +%F)"' in script_text


def test_logs_the_required_run_identity(script_text):
    for anchor in ("started_at=", "repo_root=", "git_sha=", "market_date=", "final exit_status="):
        assert anchor in script_text, f"missing log anchor {anchor}"
    assert "command: ${REFRESH_CMD[*]}" in script_text
    assert "command: ${AUDIT_CMD[*]}" in script_text


def test_invokes_the_canonical_refresh_orchestrator(script_text):
    assert REFRESH in script_text
    assert "--commit" in script_text
    assert '--market-date "${MARKET_DATE}"' in script_text


def test_uses_a_bounded_publication_gate_wait(script_text):
    assert "--gate-wait-attempts 6" in script_text
    assert "--gate-wait-seconds 600" in script_text


def test_never_calls_individual_snapshot_builders(script_code):
    """The orchestrator owns the publication order; duplicating it is the bug."""
    for builder in (
        "build_pokemon_set_sealed_market_snapshots",
        "build_pokemon_set_cards_snapshots",
        "build_pokemon_market_dashboard_snapshots",
        "build_pokemon_explore_rankings_snapshot",
        "build_pokemon_explore_card_movers_snapshot",
        "build_pokemon_set_page_snapshots",
        "build_pokemon_public_snapshots",
        "coordinated_pokemon_set_market_snapshots",
    ):
        assert builder not in script_code, f"wrapper must not call {builder} directly"


def test_never_pulls_forces_or_weakens_the_gate(script_code):
    assert "git pull" not in script_code
    assert "--force-publish" not in script_code
    # --strict would fail on the OPvC staleness this phase is defined to allow.
    assert "--strict" not in script_code


def test_runs_the_post_scrape_audit_phase(script_text):
    assert AUDIT in script_text
    assert "--phase post-scrape" in script_text


def test_the_audit_runs_only_after_a_successful_refresh(script_text):
    refresh_at = script_text.index(REFRESH)
    audit_at = script_text.index(AUDIT)
    assert refresh_at < audit_at, "the audit must be ordered after the refresh"

    # The failure branch that skips the audit must appear between them.
    between = script_text[refresh_at:audit_at]
    assert 'if [[ "${REFRESH_STATUS}" -ne 0 ]]; then' in between
    assert "skipping the post-scrape audit" in between


def test_a_deferred_gate_propagates_exit_code_3_without_auditing(script_text):
    refresh_at = script_text.index(REFRESH)
    audit_at = script_text.index(AUDIT)
    between = script_text[refresh_at:audit_at]

    assert 'if [[ "${REFRESH_STATUS}" -eq 3 ]]; then' in between
    assert "exit 3" in between


def test_a_failed_audit_fails_the_whole_run(script_text):
    audit_at = script_text.index(AUDIT)
    tail = script_text[audit_at:]

    assert 'if [[ "${AUDIT_STATUS}" -ne 0 ]]; then' in tail
    assert 'exit "${AUDIT_STATUS}"' in tail


def test_documents_that_opvc_is_intentionally_deferred(script_text):
    assert "Opening Profit vs Cost" in script_text
