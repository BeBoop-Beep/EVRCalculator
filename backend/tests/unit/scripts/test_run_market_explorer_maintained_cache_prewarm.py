"""Tests for the lean, serial, resource-guarded, lockable maintained-cache
operational worker (backend/scripts/run_market_explorer_maintained_cache_prewarm.py).

This worker is the ONLY thing allowed to actually build a
``cache_kind='maintained'`` Market Explorer query cache -- see the P0
incident note in ``run_market_explorer_daily_publication.py``'s module
docstring. Tests here mock the DB-facing discovery/build call
(``advance_one_maintained_cache``) and the host guard so they never depend
on a real DB or a real Linux host.
"""
from __future__ import annotations

import os
import tempfile
from unittest.mock import patch

import backend.scripts.run_market_explorer_maintained_cache_prewarm as worker


# --- Fake client (discovery only; build path is mocked) ----------------------

class Client:
    def __init__(self, cache_rows=None):
        self.cache_rows = cache_rows or []


def _row(fingerprint, computed_through, status="ready", set_ids=None, label=None):
    return {
        "query_fingerprint": fingerprint,
        "normalized_spec": {"mode": "all", "setIds": set_ids or []},
        "status": status,
        "cache_kind": "maintained",
        "computed_through": computed_through,
        "label": label or fingerprint,
    }


def _ok_guard():
    return worker.HostGuardResult(ok=True, observed={})


def _fake_advance_factory(status="advanced"):
    def fake_advance(client, row, *, market_date, commit):
        return worker.CacheAdvanceReport(
            fingerprint=row["query_fingerprint"], label=row["label"],
            status=status, computed_through=market_date,
        )
    return fake_advance


# --- Discovery / staleness / ordering ----------------------------------------

def test_discovers_only_maintained_caches():
    client = Client(cache_rows=[_row("fp1", "2026-09-01")])
    with patch.object(worker, "discover_maintained_caches", return_value=client.cache_rows), \
         patch.object(worker, "resolve_latest_approved_market_date", return_value="2026-09-02"), \
         patch.object(worker, "advance_one_maintained_cache", side_effect=_fake_advance_factory()):
        result = worker.run_prewarm(client, commit=False, lock=worker.FileLock(_tmp_lock()))
    assert result["discoveredMaintained"] == 1


def test_already_current_caches_skip_and_dont_count_against_limit():
    rows = [_row("fp-current", "2026-09-02", status="ready"),
            _row("fp-stale", "2026-08-01", status="ready")]
    with patch.object(worker, "discover_maintained_caches", return_value=rows), \
         patch.object(worker, "resolve_latest_approved_market_date", return_value="2026-09-02"), \
         patch.object(worker, "advance_one_maintained_cache",
                      side_effect=_fake_advance_factory()) as mock_advance:
        result = worker.run_prewarm(client=Client(), commit=True, max_caches=5,
                                     lock=worker.FileLock(_tmp_lock()), guard=_ok_guard)
    assert result["discoveredMaintained"] == 2
    assert result["staleMaintained"] == 1
    assert result["alreadyCurrent"] == 1
    assert mock_advance.call_count == 1
    assert mock_advance.call_args.args[1]["query_fingerprint"] == "fp-stale"


def test_real_planner_build_path_invoked_exactly_once_for_a_stale_cache():
    rows = [_row("fp-stale", "2026-08-01")]
    with patch.object(worker, "discover_maintained_caches", return_value=rows), \
         patch.object(worker, "resolve_latest_approved_market_date", return_value="2026-09-02"), \
         patch.object(worker, "advance_one_maintained_cache",
                      side_effect=_fake_advance_factory()) as mock_advance:
        result = worker.run_prewarm(client=Client(), commit=True,
                                     lock=worker.FileLock(_tmp_lock()), guard=_ok_guard)
    assert mock_advance.call_count == 1
    assert result["advanced"] == 1
    assert result["attempted"] == 1


def test_max_caches_default_one_builds_at_most_one():
    rows = [_row("fp-1", "2026-08-01"), _row("fp-2", "2026-08-02"), _row("fp-3", "2026-08-03")]
    with patch.object(worker, "discover_maintained_caches", return_value=rows), \
         patch.object(worker, "resolve_latest_approved_market_date", return_value="2026-09-02"), \
         patch.object(worker, "advance_one_maintained_cache",
                      side_effect=_fake_advance_factory()) as mock_advance:
        result = worker.run_prewarm(client=Client(), commit=True,
                                     lock=worker.FileLock(_tmp_lock()), guard=_ok_guard)
    assert mock_advance.call_count == 1
    assert result["attempted"] == 1
    assert result["advanced"] == 1
    assert sorted(result["deferred"]) == ["fp-2", "fp-3"]
    assert result["stopReason"] == "max_caches_reached"


def test_deterministic_oldest_first_then_fingerprint_order():
    rows = [_row("fp-z", "2026-08-01"), _row("fp-a", "2026-08-01"), _row("fp-m", "2026-07-01")]
    ordered = worker.select_stale_caches(rows, target_market_date="2026-09-02")
    assert [r["query_fingerprint"] for r in ordered] == ["fp-m", "fp-a", "fp-z"]


def test_no_maintained_caches_exits_cleanly():
    with patch.object(worker, "discover_maintained_caches", return_value=[]), \
         patch.object(worker, "resolve_latest_approved_market_date", return_value="2026-09-02"):
        result = worker.run_prewarm(client=Client(), commit=True, lock=worker.FileLock(_tmp_lock()))
    assert result["stopReason"] == "no_maintained_caches"
    assert result["attempted"] == 0


def test_no_stale_caches_exits_cleanly():
    rows = [_row("fp-1", "2026-09-02", status="ready")]
    with patch.object(worker, "discover_maintained_caches", return_value=rows), \
         patch.object(worker, "resolve_latest_approved_market_date", return_value="2026-09-02"):
        result = worker.run_prewarm(client=Client(), commit=True, lock=worker.FileLock(_tmp_lock()))
    assert result["stopReason"] == "no_stale_caches"
    assert result["alreadyCurrent"] == 1


def test_only_set_id_restricts_to_overlapping_caches():
    rows = [_row("fp-a", "2026-08-01", set_ids=["set-a"]),
            _row("fp-b", "2026-08-01", set_ids=["set-b"])]
    with patch.object(worker, "discover_maintained_caches", return_value=rows), \
         patch.object(worker, "resolve_latest_approved_market_date", return_value="2026-09-02"), \
         patch.object(worker, "advance_one_maintained_cache",
                      side_effect=_fake_advance_factory()) as mock_advance:
        result = worker.run_prewarm(client=Client(), commit=True, only_set_ids=["set-a"],
                                     lock=worker.FileLock(_tmp_lock()), guard=_ok_guard)
    assert result["discoveredMaintained"] == 1
    assert mock_advance.call_args.args[1]["query_fingerprint"] == "fp-a"


# --- Resource guard -----------------------------------------------------------

def test_memory_guard_defers_before_build():
    rows = [_row("fp-1", "2026-08-01")]
    failing_guard = lambda: worker.HostGuardResult(
        ok=False, reason="available memory 100.0MB below threshold 512.0MB", observed={})
    with patch.object(worker, "discover_maintained_caches", return_value=rows), \
         patch.object(worker, "resolve_latest_approved_market_date", return_value="2026-09-02"), \
         patch.object(worker, "advance_one_maintained_cache") as mock_advance:
        result = worker.run_prewarm(client=Client(), commit=True, guard=failing_guard,
                                     lock=worker.FileLock(_tmp_lock()))
    mock_advance.assert_not_called()
    assert result["attempted"] == 0
    assert result["deferred"] == ["fp-1"]
    assert "host_guard" in result["stopReason"]


def test_load_guard_defers_before_build():
    rows = [_row("fp-1", "2026-08-01")]
    failing_guard = lambda: worker.HostGuardResult(
        ok=False, reason="load-per-cpu 3.00 above threshold 1.50", observed={})
    with patch.object(worker, "discover_maintained_caches", return_value=rows), \
         patch.object(worker, "resolve_latest_approved_market_date", return_value="2026-09-02"), \
         patch.object(worker, "advance_one_maintained_cache") as mock_advance:
        result = worker.run_prewarm(client=Client(), commit=True, guard=failing_guard,
                                     lock=worker.FileLock(_tmp_lock()))
    mock_advance.assert_not_called()
    assert "host_guard" in result["stopReason"]


def test_guard_is_never_consulted_in_dry_run():
    """A dry-run never touches the host guard -- there is nothing to protect
    against when nothing is actually going to build."""
    rows = [_row("fp-1", "2026-08-01")]
    called = {"n": 0}

    def counting_guard():
        called["n"] += 1
        return worker.HostGuardResult(ok=True, observed={})

    with patch.object(worker, "discover_maintained_caches", return_value=rows), \
         patch.object(worker, "resolve_latest_approved_market_date", return_value="2026-09-02"), \
         patch.object(worker, "advance_one_maintained_cache",
                      side_effect=_fake_advance_factory()):
        worker.run_prewarm(client=Client(), commit=False, guard=counting_guard,
                            lock=worker.FileLock(_tmp_lock()))
    assert called["n"] == 0


def test_host_metrics_unavailable_does_not_crash_and_does_not_block():
    with patch.object(worker, "available_memory_mb", return_value=None), \
         patch.object(worker, "total_memory_mb", return_value=None), \
         patch.object(worker, "load_average_per_cpu", return_value=None):
        result = worker.evaluate_host_guard()
    assert result.ok is True
    assert result.observed["availableMemoryMb"] == "unavailable"
    assert result.observed["loadPerCpu"] == "unavailable"


def test_guard_blocks_on_low_memory_with_real_thresholds():
    with patch.object(worker, "available_memory_mb", return_value=100.0), \
         patch.object(worker, "total_memory_mb", return_value=2000.0), \
         patch.object(worker, "load_average_per_cpu", return_value=0.1):
        result = worker.evaluate_host_guard(min_available_memory_mb=512.0,
                                             min_available_memory_percent=25.0)
    assert result.ok is False
    assert "memory" in result.reason


def test_guard_blocks_on_high_load_with_real_thresholds():
    with patch.object(worker, "available_memory_mb", return_value=4000.0), \
         patch.object(worker, "total_memory_mb", return_value=8000.0), \
         patch.object(worker, "load_average_per_cpu", return_value=3.0):
        result = worker.evaluate_host_guard(max_load_per_cpu=1.5)
    assert result.ok is False
    assert "load" in result.reason


# --- Singleton lock ------------------------------------------------------------

def test_second_instance_defers_cleanly_when_lock_held():
    lock_path = _tmp_lock()
    holder = worker.FileLock(lock_path)
    assert holder.acquire() is True
    try:
        rows = [_row("fp-1", "2026-08-01")]
        with patch.object(worker, "discover_maintained_caches", return_value=rows), \
             patch.object(worker, "resolve_latest_approved_market_date", return_value="2026-09-02"), \
             patch.object(worker, "advance_one_maintained_cache") as mock_advance:
            result = worker.run_prewarm(client=Client(), commit=True,
                                         lock=worker.FileLock(lock_path), guard=_ok_guard)
        assert result["stopReason"] == "already_running"
        mock_advance.assert_not_called()
    finally:
        holder.release()


def test_lock_is_released_after_a_run_allowing_a_subsequent_run():
    lock_path = _tmp_lock()
    rows = [_row("fp-1", "2026-08-01")]
    with patch.object(worker, "discover_maintained_caches", return_value=rows), \
         patch.object(worker, "resolve_latest_approved_market_date", return_value="2026-09-02"), \
         patch.object(worker, "advance_one_maintained_cache",
                      side_effect=_fake_advance_factory()):
        first = worker.run_prewarm(client=Client(), commit=True,
                                    lock=worker.FileLock(lock_path), guard=_ok_guard)
        second = worker.run_prewarm(client=Client(), commit=True,
                                     lock=worker.FileLock(lock_path), guard=_ok_guard)
    assert first["stopReason"] != "already_running"
    assert second["stopReason"] != "already_running"


# --- Build isolation / dry-run / no-approved-date ----------------------------

def test_one_build_failure_does_not_corrupt_other_cache_metadata():
    rows = [_row("fp-bad", "2026-08-01"), _row("fp-good", "2026-08-02")]

    def flaky_advance(client, row, *, market_date, commit):
        if row["query_fingerprint"] == "fp-bad":
            raise RuntimeError("boom")
        return worker.CacheAdvanceReport(fingerprint=row["query_fingerprint"],
                                          label=row["label"], status="advanced")

    with patch.object(worker, "discover_maintained_caches", return_value=rows), \
         patch.object(worker, "resolve_latest_approved_market_date", return_value="2026-09-02"), \
         patch.object(worker, "advance_one_maintained_cache", side_effect=flaky_advance):
        result = worker.run_prewarm(client=Client(), commit=True, max_caches=2,
                                     lock=worker.FileLock(_tmp_lock()), guard=_ok_guard)
    assert result["failed"] == 1
    assert result["advanced"] == 1
    assert result["attempted"] == 2


def test_dry_run_performs_no_cache_writes_or_builds():
    rows = [_row("fp-1", "2026-08-01")]
    with patch.object(worker, "discover_maintained_caches", return_value=rows), \
         patch.object(worker, "resolve_latest_approved_market_date", return_value="2026-09-02"), \
         patch.object(worker, "advance_one_maintained_cache",
                      side_effect=_fake_advance_factory()) as mock_advance:
        result = worker.run_prewarm(client=Client(), commit=False, lock=worker.FileLock(_tmp_lock()))
    # advance_one_maintained_cache itself is commit-gated (no planner import
    # happens when commit=False); the worker must still call through with
    # commit=False rather than skip the row silently.
    mock_advance.assert_called_once()
    assert mock_advance.call_args.kwargs["commit"] is False


def test_no_approved_market_date_exits_cleanly():
    with patch.object(worker, "resolve_latest_approved_market_date", return_value=None), \
         patch.object(worker, "discover_maintained_caches") as mock_discover:
        result = worker.run_prewarm(client=Client(), commit=True, lock=worker.FileLock(_tmp_lock()))
    assert result["stopReason"] == "no_approved_market_date"
    mock_discover.assert_not_called()


def test_summary_contains_required_keys():
    rows = [_row("fp-1", "2026-08-01")]
    with patch.object(worker, "discover_maintained_caches", return_value=rows), \
         patch.object(worker, "resolve_latest_approved_market_date", return_value="2026-09-02"), \
         patch.object(worker, "advance_one_maintained_cache",
                      side_effect=_fake_advance_factory()):
        result = worker.run_prewarm(client=Client(), commit=True,
                                     lock=worker.FileLock(_tmp_lock()), guard=_ok_guard)
    for key in ("targetMarketDate", "discoveredMaintained", "staleMaintained", "alreadyCurrent",
                "attempted", "advanced", "failed", "deferred", "stopReason", "reports",
                "elapsedSeconds"):
        assert key in result


def _tmp_lock() -> str:
    return os.path.join(tempfile.gettempdir(),
                         f"market_explorer_cache_prewarm_test_{os.getpid()}_{id(object())}.lock")
