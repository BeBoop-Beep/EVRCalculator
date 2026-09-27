from pathlib import Path
from typing import Optional


WORKFLOW = (
    Path(__file__).resolve().parents[4]
    / ".github"
    / "workflows"
    / "sentinel-runtime-backstop.yml"
)


def _job(source: str, name: str, next_name: Optional[str] = None) -> str:
    start = source.index(f"  {name}:\n")
    end = source.index(f"  {next_name}:\n", start) if next_name else len(source)
    return source[start:end]


def test_independent_observer_has_a_distinct_hosted_read_only_failure_domain():
    source = WORKFLOW.read_text(encoding="utf-8")
    observer = _job(source, "independent-observer", "fast-recovery-backstop")

    assert "runs-on: ubuntu-24.04" in observer
    assert "self-hosted" not in observer
    assert "ref: ${{ github.sha }}" in observer
    assert "SENTINEL_WATCH_COMPONENT: sentinel_vm" in observer
    assert "SENTINEL_WATCH_HOST: tcgplayer-scraper-pokemon-v2" in observer
    assert "SENTINEL_COMPONENT: sentinel_github_backstop" in observer
    assert "SENTINEL_RUNNER_HOST: github-hosted-sentinel-backstop" in observer
    assert "SENTINEL_STATE_WRITES_ENABLED: 'false'" in observer
    assert "SENTINEL_PERSISTENCE_SCHEMA_READY: 'false'" in observer
    assert "SENTINEL_RECOVERY_ENABLED: 'false'" in observer
    assert "SENTINEL_RECOVERY_EXECUTION_READY: 'false'" in observer
    assert "SENTINEL_AI_ENABLED: 'false'" in observer
    assert "backend/.env" not in observer
    assert "--profile independent" in observer


def test_fast_backstop_retains_vm_safety_controls_without_observer_profile():
    source = WORKFLOW.read_text(encoding="utf-8")
    fast = _job(source, "fast-recovery-backstop")

    assert "runs-on: [self-hosted, Linux, ARM64, index-production-vm]" in fast
    assert 'HOLD=/home/ubuntu/state/db-safety/hold.json' in fast
    assert '[ -e "$HOLD" ] || [ -L "$HOLD" ]' in fast
    assert "/usr/bin/flock -n /tmp/index-sentinel-fast.lock" in fast
    assert ". backend/.env" in fast
    assert "SENTINEL_RUNNER_BUILD_SHA=\\$(git rev-parse HEAD)" in fast
    assert "--profile fast" in fast
    assert "--profile independent" not in fast
