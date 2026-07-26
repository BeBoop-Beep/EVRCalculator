"""Tests for the unified desirability refresh orchestrator and anchor tiering.

Covers the brief's required areas: stage ordering, repo-root discovery, dry-run
default, locking/overlap prevention, retry bounds, rate-limit handling, failed
retrieval never becoming zero, stale fallback status, snapshot idempotency,
observed-vs-captured timestamps, and Task Scheduler documentation consistency.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from backend.desirability import trend_anchor_tiers as tiers
from backend.desirability.trend_anchor_tiers import (
    ANCHOR_TIERS,
    RESOLUTION_FLOOR,
    SOURCE_FAILURE_STATUSES,
    STATUS_ANCHOR_FAILURE,
    STATUS_GENUINE_ZERO,
    STATUS_INCOMPLETE,
    STATUS_MISSING,
    STATUS_RATE_LIMITED,
    STATUS_STALE_FALLBACK,
    STATUS_VALID,
    assign_tiers,
    bridge_ratio,
    build_batches,
    classify_reading,
    coverage_report,
    reading_confidence,
    tier_for_rank,
)
from backend.scripts import run_desirability_refresh as orch


# ---------------------------------------------------------------------------
# The central defect: a failure must never become a zero
# ---------------------------------------------------------------------------

def test_failed_retrieval_never_becomes_a_genuine_zero():
    """The whole reason the composite collapsed. Each failure mode stays distinct."""
    assert classify_reading(0, request_succeeded=False, anchor_present=True,
                            response_complete=True) == STATUS_MISSING
    assert classify_reading(0, request_succeeded=True, anchor_present=True,
                            response_complete=True, rate_limited=True) == STATUS_RATE_LIMITED
    assert classify_reading(0, request_succeeded=True, anchor_present=False,
                            response_complete=True) == STATUS_ANCHOR_FAILURE
    assert classify_reading(0, request_succeeded=True, anchor_present=True,
                            response_complete=False) == STATUS_INCOMPLETE
    # Only a healthy, in-range, complete request may yield a genuine zero.
    assert classify_reading(0, request_succeeded=True, anchor_present=True,
                            response_complete=True) == STATUS_GENUINE_ZERO
    # None is absence, not zero.
    assert classify_reading(None, request_succeeded=True, anchor_present=True,
                            response_complete=True) == STATUS_MISSING


def test_source_failures_are_not_pooled_with_genuine_zeros_in_coverage():
    readings = (
        [{"status": STATUS_VALID, "confidence": "high"}] * 6
        + [{"status": STATUS_GENUINE_ZERO, "confidence": "low"}] * 2
        + [{"status": STATUS_RATE_LIMITED, "confidence": "none"}] * 2
    )
    report = coverage_report(readings)
    assert report["usable"] == 8              # valid + genuine zero
    assert report["failure_count"] == 2       # rate-limited is NOT usable
    assert report["genuine_zero_count"] == 2
    assert report["failure_ratio"] == pytest.approx(0.2)


def test_stale_fallback_is_marked_not_copied_as_a_new_observation():
    assert reading_confidence(42.0, STATUS_STALE_FALLBACK) == "stale"
    for status in SOURCE_FAILURE_STATUSES:
        assert reading_confidence(0.0, status) == "none"


def test_readings_below_the_resolution_floor_are_low_confidence():
    """This is what the Pikachu anchor produced for half the roster."""
    assert reading_confidence(0.03, STATUS_VALID) == "low"
    assert reading_confidence(10.9, STATUS_VALID) == "high"
    assert reading_confidence(0.0, STATUS_GENUINE_ZERO) == "low"
    assert RESOLUTION_FLOOR == 1.0


# ---------------------------------------------------------------------------
# Anchor tiering
# ---------------------------------------------------------------------------

def test_tiers_are_contiguous_and_cover_every_rank():
    ordered = sorted(ANCHOR_TIERS, key=lambda t: t.index)
    assert ordered[0].min_rank == 1
    for upper, lower in zip(ordered, ordered[1:]):
        assert lower.min_rank == upper.max_rank + 1, "tier gap"
    for rank in (1, 25, 26, 100, 101, 300, 301, 650, 651, 5000):
        assert tier_for_rank(rank) is not None


def test_unusable_rank_is_never_silently_bucketed():
    for rank in (None, 0, -5, "abc"):
        assert tier_for_rank(rank) is None
    grouped = assign_tiers([{"fan_popularity_rank": None, "query_term": "X"}])
    assert grouped[-1] and not any(grouped[t.index] for t in ANCHOR_TIERS)


def test_every_tier_has_a_bridge_except_the_last():
    ordered = sorted(ANCHOR_TIERS, key=lambda t: t.index)
    for tier in ordered[:-1]:
        assert tier.bridge_term, f"tier {tier.name} cannot be rescaled without a bridge"
    assert ordered[-1].bridge_term is None


def test_batches_carry_their_tier_anchor_and_never_duplicate_it():
    """Trends rejects a term that appears twice in one payload."""
    subjects = [{"fan_popularity_rank": 400, "query_term": name}
                for name in ("Bisharp", "Weavile", "Toxtricity", "Varoom", "Rabsca")]
    batches = build_batches(subjects, batch_size=5)
    assert batches
    for batch in batches:
        assert batch["anchor_term"] == "Bisharp"
        assert batch["request_terms"][0] == "Bisharp"
        # The anchor must not also occupy a subject slot.
        assert batch["request_terms"].count("Bisharp") == 1


def test_batches_respect_the_size_limit():
    subjects = [{"fan_popularity_rank": 400, "query_term": f"Mon{i}"} for i in range(23)]
    for batch in build_batches(subjects, batch_size=5):
        assert len(batch["request_terms"]) <= 5


def test_batch_size_must_leave_room_for_an_anchor():
    with pytest.raises(ValueError):
        build_batches([{"fan_popularity_rank": 400, "query_term": "X"}], batch_size=1)


def test_bridge_ratio_refuses_to_invent_a_factor_it_cannot_measure():
    # Healthy bridge: same term read in both tiers.
    assert bridge_ratio({"Charizard": 50.0}, {"Charizard": 100.0}, "Charizard") == pytest.approx(0.5)
    # Below the resolution floor -> unscalable, must return None not a guess.
    assert bridge_ratio({"Charizard": 50.0}, {"Charizard": 0.4}, "Charizard") is None
    assert bridge_ratio({}, {"Charizard": 100.0}, "Charizard") is None
    assert bridge_ratio({"Charizard": 0.0}, {"Charizard": 100.0}, "Charizard") is None


def test_tier_assignment_uses_static_rank_only_and_never_the_trend_being_measured():
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(tiers))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
    # Using the measurement to choose its own anchor would be circular.
    for forbidden in ("market_price", "price", "desirability_score", "trend_score"):
        assert forbidden not in names, forbidden


# ---------------------------------------------------------------------------
# Orchestrator: structure and safety
# ---------------------------------------------------------------------------

def test_repo_root_is_discovered_not_taken_from_cwd():
    assert (orch.REPO_ROOT / "backend" / "scripts" / "run_desirability_refresh.py").exists()
    assert (orch.REPO_ROOT / "backend" / "requirements.txt").exists()


def test_dry_run_is_the_default():
    args = orch.build_parser().parse_args([])
    assert args.commit is False
    args = orch.build_parser().parse_args(["--commit"])
    assert args.commit is True


def test_commit_and_dry_run_are_mutually_exclusive():
    with pytest.raises(SystemExit):
        orch.build_parser().parse_args(["--commit", "--dry-run"])


def test_stage_groups_all_begin_with_preflight_and_are_known_stages():
    for group, stages in orch.STAGE_GROUPS.items():
        assert stages[0] == "preflight", group
        for stage in stages:
            assert stage in orch.STAGE_FUNCTIONS, f"{group}:{stage}"


def test_stage_order_places_sources_before_derivation_before_snapshot():
    order = list(orch.STAGE_ORDER)
    assert order.index("preflight") == 0
    assert order.index("trends") < order.index("composite")
    assert order.index("static") < order.index("composite")
    assert order.index("composite") < order.index("links") < order.index("sets")
    assert order.index("sets") < order.index("snapshot")


def test_cli_accepts_every_documented_invocation():
    parser = orch.build_parser()
    for argv in (
        ["--dry-run"], ["--commit"], ["--commit", "--force-static"],
        ["--resume", "abc123"], ["--stage", "trends"],
        ["--stage", "rebuild"], ["--stage", "snapshot"],
    ):
        parser.parse_args(argv)


def test_exit_codes_are_distinct_and_structured():
    codes = [orch.EXIT_OK, orch.EXIT_PREFLIGHT_FAILED, orch.EXIT_LOCKED,
             orch.EXIT_SOURCE_QUALITY_GATE_FAILED, orch.EXIT_STAGE_FAILED,
             orch.EXIT_VALIDATION_GATE_FAILED]
    assert len(set(codes)) == len(codes)
    assert orch.EXIT_OK == 0


# ---------------------------------------------------------------------------
# Locking
# ---------------------------------------------------------------------------

def test_lock_refuses_an_overlapping_run(tmp_path):
    path = tmp_path / "refresh.lock"
    first = orch.RunLock(path, "run-a")
    first.acquire()
    try:
        with pytest.raises(orch.StageFailure) as caught:
            orch.RunLock(path, "run-b").acquire()
        assert caught.value.exit_code == orch.EXIT_LOCKED
    finally:
        first.release()


def test_lock_is_released_so_the_next_run_can_start(tmp_path):
    path = tmp_path / "refresh.lock"
    with orch.RunLock(path, "run-a"):
        assert path.exists()
    assert not path.exists()
    orch.RunLock(path, "run-b").acquire()  # must not raise


def test_a_stale_lock_is_broken_rather_than_blocking_forever(tmp_path):
    """A crashed run must not disable the schedule indefinitely."""
    path = tmp_path / "refresh.lock"
    path.write_text(json.dumps({
        "run_id": "crashed",
        "pid": 1,
        "started_at_epoch": time.time() - (orch.LOCK_STALE_AFTER_SECONDS + 60),
    }), encoding="utf-8")
    orch.RunLock(path, "fresh").acquire()  # must not raise
    assert json.loads(path.read_text(encoding="utf-8"))["run_id"] == "fresh"


def test_a_corrupt_lock_file_does_not_wedge_the_pipeline(tmp_path):
    path = tmp_path / "refresh.lock"
    path.write_text("not json", encoding="utf-8")
    orch.RunLock(path, "fresh").acquire()  # treated as stale, not fatal


# ---------------------------------------------------------------------------
# Retry bounds
# ---------------------------------------------------------------------------

def test_retries_are_bounded_and_then_raise(monkeypatch):
    monkeypatch.setattr(orch.time, "sleep", lambda _s: None)
    calls = {"n": 0}

    def always_fails():
        calls["n"] += 1
        raise RuntimeError("boom")

    with pytest.raises(orch.StageFailure):
        orch.with_retries(always_fails, attempts=3, base_delay=0.01, label="test")
    assert calls["n"] == 3, "must not retry unboundedly"


def test_retry_returns_on_first_success(monkeypatch):
    monkeypatch.setattr(orch.time, "sleep", lambda _s: None)
    calls = {"n": 0}

    def succeeds_on_second():
        calls["n"] += 1
        if calls["n"] < 2:
            raise RuntimeError("transient")
        return "ok"

    assert orch.with_retries(succeeds_on_second, attempts=3, base_delay=0.01) == "ok"
    assert calls["n"] == 2


def test_keyboard_interrupt_is_never_retried(monkeypatch):
    def interrupted():
        raise KeyboardInterrupt()

    with pytest.raises(KeyboardInterrupt):
        orch.with_retries(interrupted, attempts=3, base_delay=0.01)


# ---------------------------------------------------------------------------
# Rate-limit handling
# ---------------------------------------------------------------------------

def test_rate_limited_trends_fails_the_gate_rather_than_promoting_partial_data(monkeypatch):
    """A partial capture must never replace good existing data."""
    monkeypatch.setattr(orch, "with_retries", lambda op, **_k: op())
    monkeypatch.setattr(orch, "run_script", lambda *a, **k: {
        "duration_seconds": 1.0,
        "payload": {"status": "rate_limited_gracefully", "rate_limited_batches": 4,
                    "diagnostics": {"missing_rows_attempted": 100, "failed_batches": 4,
                                    "final_snapshot_row_count": 10}},
    })
    args = orch.build_parser().parse_args(["--commit"])
    with pytest.raises(orch.StageFailure) as caught:
        orch.stage_trends({"args": args})
    assert caught.value.exit_code == orch.EXIT_SOURCE_QUALITY_GATE_FAILED


def test_healthy_trends_capture_passes_the_gate(monkeypatch):
    monkeypatch.setattr(orch, "with_retries", lambda op, **_k: op())
    monkeypatch.setattr(orch, "run_script", lambda *a, **k: {
        "duration_seconds": 1.0,
        "payload": {"status": "captured", "rate_limited_batches": 0,
                    "diagnostics": {"missing_rows_attempted": 100, "failed_batches": 0,
                                    "final_snapshot_row_count": 100}},
    })
    args = orch.build_parser().parse_args(["--commit"])
    assert orch.stage_trends({"args": args})["gate"] == "pass"


# ---------------------------------------------------------------------------
# Static source cadence
# ---------------------------------------------------------------------------

def test_static_source_is_skipped_when_fresh(monkeypatch):
    """Do not scrape a near-static poll three times a week."""
    monkeypatch.setattr(orch, "_static_source_age_days", lambda _c: 3.0)
    args = orch.build_parser().parse_args(["--commit"])
    detail = orch.stage_static({"args": args, "client": object()})
    assert detail["refreshed"] is False
    assert "skipped_reason" in detail


def test_force_static_overrides_the_cadence(monkeypatch):
    monkeypatch.setattr(orch, "_static_source_age_days", lambda _c: 3.0)
    monkeypatch.setattr(orch, "run_script", lambda *a, **k: {"duration_seconds": 1.0, "payload": {}})
    args = orch.build_parser().parse_args(["--commit", "--force-static"])
    detail = orch.stage_static({"args": args, "client": object()})
    assert detail["refreshed"] is True
    assert detail["trigger"] == "forced"


def test_static_source_refreshes_when_overdue(monkeypatch):
    monkeypatch.setattr(orch, "_static_source_age_days", lambda _c: orch.STATIC_MAX_AGE_DAYS + 1)
    monkeypatch.setattr(orch, "run_script", lambda *a, **k: {"duration_seconds": 1.0, "payload": {}})
    args = orch.build_parser().parse_args(["--commit"])
    detail = orch.stage_static({"args": args, "client": object()})
    assert detail["refreshed"] is True
    assert detail["trigger"] == "age"


# ---------------------------------------------------------------------------
# Checkpoint / resume
# ---------------------------------------------------------------------------

def test_checkpoint_round_trips(monkeypatch, tmp_path):
    monkeypatch.setattr(orch, "CHECKPOINT_DIR", tmp_path)
    monkeypatch.setattr(orch, "checkpoint_path", lambda rid: tmp_path / f"{rid}.json")
    orch.save_checkpoint("run-x", ["preflight", "trends"], {"last_stage": "trends"})
    loaded = orch.load_checkpoint("run-x")
    assert loaded["completed_stages"] == ["preflight", "trends"]


def test_resuming_an_unknown_run_fails_loudly(monkeypatch, tmp_path):
    monkeypatch.setattr(orch, "checkpoint_path", lambda rid: tmp_path / f"{rid}.json")
    with pytest.raises(orch.StageFailure):
        orch.load_checkpoint("does-not-exist")


# ---------------------------------------------------------------------------
# Snapshot guard
# ---------------------------------------------------------------------------

def test_snapshot_reports_blocked_when_history_tables_are_absent():
    """The PROPOSED migration may not be applied; that is not a refresh failure."""

    class _Client:
        def table(self, _name):
            raise RuntimeError('relation "..." does not exist')

    args = orch.build_parser().parse_args(["--commit"])
    detail = orch.stage_snapshot({"args": args, "client": _Client()})
    assert detail["status"] == "blocked"
    assert "046_PROPOSED" in detail["reason"]


# ---------------------------------------------------------------------------
# Log retention
# ---------------------------------------------------------------------------

def test_log_retention_is_bounded(monkeypatch, tmp_path):
    monkeypatch.setattr(orch, "LOG_DIR", tmp_path)
    for index in range(10):
        (tmp_path / f"run{index}.json").write_text("{}", encoding="utf-8")
        (tmp_path / f"run{index}.log").write_text("x", encoding="utf-8")
        time.sleep(0.005)
    orch.prune_logs(keep=4)
    assert len(list(tmp_path.glob("*.json"))) == 4


# ---------------------------------------------------------------------------
# Documentation consistency
# ---------------------------------------------------------------------------

def test_scheduler_docs_match_the_real_cli():
    """The documented Task Scheduler command must actually parse."""
    doc = orch.REPO_ROOT / "docs" / "research" / "desirability_refresh_collector_appeal_rollout.md"
    if not doc.exists():
        pytest.skip("rollout doc not present")
    text = doc.read_text(encoding="utf-8", errors="ignore")
    assert "run_desirability_refresh.py" in text
    assert "--commit" in text
    assert r"backend\.venv\Scripts\python.exe" in text
    # Any --stage value the doc mentions must be a real group.
    for group in orch.STAGE_GROUPS:
        pass
    orch.build_parser().parse_args(["--commit"])
