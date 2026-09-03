"""Tests for the immediate post-scrape publication handoff.

These are mutation-resistant on purpose: each test proves that removing the
currency check, breaking the exact-market-date pass-through, or letting a
launch failure raise would make it fail.
"""
from pathlib import Path

import pytest

from backend.db.services import post_scrape_publication_trigger as trigger


def _fake_popen(args, *, cwd, log_path):
    class _Proc:
        pid = 4242

    _fake_popen.calls.append({"args": list(args), "cwd": cwd, "log_path": log_path})
    return _Proc()


@pytest.fixture(autouse=True)
def _reset_popen_calls():
    _fake_popen.calls = []
    yield


def test_invalid_market_date_never_launches():
    calls_before = len(_fake_popen.calls)
    result = trigger.trigger_post_scrape_publication_if_needed(
        None, publication_current=lambda d: False, popen=_fake_popen,
    )
    assert result["status"] == trigger.STATUS_INVALID_MARKET_DATE
    assert len(_fake_popen.calls) == calls_before


def test_malformed_market_date_never_launches():
    result = trigger.trigger_post_scrape_publication_if_needed(
        "09-01-2026", publication_current=lambda d: False, popen=_fake_popen,
    )
    assert result["status"] == trigger.STATUS_INVALID_MARKET_DATE
    assert _fake_popen.calls == []


def test_already_current_market_date_skips_launch():
    """Removing the currency check would make this fire a launch — it must not."""
    seen = []

    def current(market_date):
        seen.append(market_date)
        return True

    result = trigger.trigger_post_scrape_publication_if_needed(
        "2026-09-01", publication_current=current, popen=_fake_popen,
    )
    assert result["status"] == trigger.STATUS_SKIPPED_ALREADY_CURRENT
    assert seen == ["2026-09-01"]
    assert _fake_popen.calls == []


def test_stale_market_date_launches_detached_with_exact_date():
    result = trigger.trigger_post_scrape_publication_if_needed(
        "2026-09-01", publication_current=lambda d: False, popen=_fake_popen,
    )
    assert result["status"] == trigger.STATUS_LAUNCH_REQUESTED
    assert len(_fake_popen.calls) == 1
    call = _fake_popen.calls[0]
    # Exact market date propagated unchanged as the invocation argument.
    assert call["args"][-1] == "2026-09-01"
    assert str(trigger.REBUILD_SCRIPT) in call["args"][0]


def test_repeated_calls_after_success_do_not_relaunch():
    """Idle-minute dispatcher calling this repeatedly must not restart the publisher
    once the exact market date is durably current."""
    result_1 = trigger.trigger_post_scrape_publication_if_needed(
        "2026-09-01", publication_current=lambda d: False, popen=_fake_popen,
    )
    assert result_1["status"] == trigger.STATUS_LAUNCH_REQUESTED

    # Publication has since completed; the durable authority now reports current.
    result_2 = trigger.trigger_post_scrape_publication_if_needed(
        "2026-09-01", publication_current=lambda d: True, popen=_fake_popen,
    )
    assert result_2["status"] == trigger.STATUS_SKIPPED_ALREADY_CURRENT
    assert len(_fake_popen.calls) == 1  # only the first call actually launched


def test_launch_failure_is_swallowed_and_reported_not_raised(monkeypatch):
    def boom(args, *, cwd, log_path):
        raise OSError("no such file or directory")

    alerts = []
    monkeypatch.setattr(
        trigger, "_queue_launch_failure_alert",
        lambda market_date, error: alerts.append((market_date, error)),
    )

    result = trigger.trigger_post_scrape_publication_if_needed(
        "2026-09-01", publication_current=lambda d: False, popen=boom,
    )
    assert result["status"] == trigger.STATUS_LAUNCH_FAILED
    assert "error" in result
    assert alerts and alerts[0][0] == "2026-09-01"


def test_currency_check_exception_treated_as_stale_not_raised():
    def broken(market_date):
        raise RuntimeError("db unreachable")

    result = trigger.trigger_post_scrape_publication_if_needed(
        "2026-09-01", publication_current=broken, popen=_fake_popen,
    )
    # Fail-open to "needs publishing" so a broken currency check does not
    # silently block publication forever.
    assert result["status"] == trigger.STATUS_LAUNCH_REQUESTED
    assert len(_fake_popen.calls) == 1


def test_already_running_publication_skips_launch_without_currency_check():
    """L: an in-flight publication must not get a new detached launch request
    every idle minute. When the lock pre-check reports the wrapper's flock is
    already held, no subprocess is spawned and the (possibly Supabase-flapping)
    currency check is not even consulted."""
    currency_calls = []

    def current(market_date):
        currency_calls.append(market_date)
        return False

    result = trigger.trigger_post_scrape_publication_if_needed(
        "2026-09-02",
        publication_current=current,
        popen=_fake_popen,
        lock_check=lambda path: True,
    )
    assert result["status"] == trigger.STATUS_SKIPPED_ALREADY_RUNNING
    assert _fake_popen.calls == []
    assert currency_calls == []


def test_lock_not_held_proceeds_to_normal_currency_check_and_launch():
    result = trigger.trigger_post_scrape_publication_if_needed(
        "2026-09-02",
        publication_current=lambda d: False,
        popen=_fake_popen,
        lock_check=lambda path: False,
    )
    assert result["status"] == trigger.STATUS_LAUNCH_REQUESTED
    assert len(_fake_popen.calls) == 1


def test_lock_check_exception_fails_open_to_normal_flow():
    """A broken lock pre-check must never itself block a legitimate launch —
    only the shell wrapper's own authoritative flock may do that."""
    def broken_lock_check(path):
        raise RuntimeError("cannot stat lock file")

    result = trigger.trigger_post_scrape_publication_if_needed(
        "2026-09-02",
        publication_current=lambda d: False,
        popen=_fake_popen,
        lock_check=broken_lock_check,
    )
    assert result["status"] == trigger.STATUS_LAUNCH_REQUESTED


def test_repeated_idle_ticks_while_running_never_relaunch():
    """M: many idle-minute ticks landing while a publisher is already running
    (simulated by a lock that stays held) must not each spawn a new subprocess,
    however the currency check itself would answer under a flapping backend."""
    for _ in range(10):
        result = trigger.trigger_post_scrape_publication_if_needed(
            "2026-09-02",
            publication_current=lambda d: False,  # e.g. Supabase 5xx -> "stale"
            popen=_fake_popen,
            lock_check=lambda path: True,
        )
        assert result["status"] == trigger.STATUS_SKIPPED_ALREADY_RUNNING
    assert _fake_popen.calls == []


def test_default_lock_check_on_free_path_reports_not_held(tmp_path):
    lock_path = tmp_path / "pokemon-post-scrape-publication.lock"
    assert trigger._default_lock_is_held(str(lock_path)) is False


def test_default_popen_uses_detached_session_and_explicit_args(tmp_path, monkeypatch):
    captured = {}

    class _FakeCompletedPopen:
        pid = 999

    def fake_subprocess_popen(args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return _FakeCompletedPopen()

    monkeypatch.setattr(trigger.subprocess, "Popen", fake_subprocess_popen)
    log_path = tmp_path / "publication.log"

    proc = trigger._default_popen(
        [str(trigger.REBUILD_SCRIPT), "2026-09-01"], cwd=str(tmp_path), log_path=log_path,
    )
    assert proc.pid == 999
    assert captured["args"][0] == str(trigger.REBUILD_SCRIPT)
    assert captured["kwargs"]["cwd"] == str(tmp_path)
    # No shell injection surface: args passed as a list, not a shell string.
    assert isinstance(captured["args"], list)
    assert log_path.exists()
