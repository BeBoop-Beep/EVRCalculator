from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]


def test_fv_shadow_ops_cron_has_fixed_cutoff_and_bounded_retry_windows():
    cron = (ROOT / "infra/oracle/fair-value-shadow-ops.crontab").read_text(encoding="utf-8")
    live = [l for l in cron.splitlines() if l.strip() and not l.lstrip().startswith("#") and not l.startswith("CRON_TZ")]
    assert len(live) == 2
    assert live[0].startswith("5,20,35,50 18 * * * ")
    assert "run_fair_value_shadow_daily_guarded.sh" in live[0]
    assert live[1].startswith("12 5,7,9 * * * ")
    assert "run_fair_value_forward_outcomes_guarded.sh" in live[1]


def test_daily_shadow_wrapper_pins_release_and_uses_fixed_information_cutoff():
    text = (ROOT / "infra/oracle/run_fair_value_shadow_daily.sh").read_text(encoding="utf-8")
    assert "release.sha" in text
    assert "time(18, 0)" in text
    assert "--information-cutoff" in text
    assert "--source-commit" in text
    assert "/tmp/pkmnprices-api.lock" in text
    assert "/tmp/pokemon-post-scrape-publication.lock" in text
    assert text.count("DB_SAFETY_HOLD") == 2


def test_forward_wrapper_uses_shared_safety_locks_and_append_only_runner():
    text = (ROOT / "infra/oracle/run_fair_value_forward_outcomes.sh").read_text(encoding="utf-8")
    assert "release.sha" in text
    assert "/tmp/pokemon-scrape-dispatcher.lock" in text
    assert "/tmp/pokemon-post-scrape-publication.lock" in text
    assert "run_index_fair_value_forward_outcomes_v1 --commit" in text
    assert text.count("DB_SAFETY_HOLD") == 2


def test_both_scheduled_jobs_use_continuous_db_pressure_guard():
    for name in ("run_fair_value_shadow_daily_guarded.sh", "run_fair_value_forward_outcomes_guarded.sh"):
        text = (ROOT / "infra/oracle" / name).read_text(encoding="utf-8")
        assert "/home/ubuntu/state/db-safety/db_workload_guard.py" in text
        assert "--run-encoded" in text
        assert "--wait-lock-seconds 300" in text


def test_fv_shadow_ops_installer_is_verify_first_and_managed():
    text = (ROOT / "infra/oracle/install_fair_value_shadow_ops_cron.sh").read_text(encoding="utf-8")
    assert 'if [ "${1:-}" != "--apply" ]' in text
    assert "worktree add --detach" in text
    assert "run_index_fair_value_prospective_shadow_v1" in text
    assert "run_index_fair_value_forward_outcomes_v1" in text
    assert "fair-value-shadow-ops.crontab" in text
    assert "release.sha.tmp" in text
    assert re.search(r"conflicting FV shadow schedule", text)
