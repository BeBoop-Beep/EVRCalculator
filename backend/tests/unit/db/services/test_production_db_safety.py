from __future__ import annotations

import json
import os
from pathlib import Path
import pwd

from backend.db.services.production_db_safety import (
    HOLD_ABSENT,
    HOLD_ACTIVE_VALID,
    HOLD_INVALID_EMPTY,
    HOLD_INVALID_MALFORMED,
    inspect_maintenance_hold,
    maintenance_hold_active,
    repair_invalid_empty_hold_if_safe,
)


class _Result:
    def __init__(self, data):
        self.data = data


class _Query:
    def select(self, *_args, **_kwargs):
        return self

    def order(self, *_args, **_kwargs):
        return self

    def limit(self, *_args, **_kwargs):
        return self

    def execute(self):
        return _Result(
            [{"id": 1, "market_date": "2026-10-02", "status": "complete"}]
        )


class _Client:
    def table(self, name):
        assert name == "pokemon_scrape_batches"
        return _Query()


def _owner() -> str:
    return pwd.getpwuid(os.getuid()).pw_name


def _write_guard(path: Path, pressure: str | None = None) -> None:
    path.write_text(
        "def live_pressure():\n"
        + f"    return {pressure!r}\n",
        encoding="utf-8",
    )
    path.chmod(0o700)


def test_hold_inspection_preserves_fail_closed_shapes(tmp_path, monkeypatch):
    hold = tmp_path / "hold.json"
    monkeypatch.setenv("INDEX_DB_SAFETY_HOLD_PATH", str(hold))

    assert inspect_maintenance_hold().state == HOLD_ABSENT
    assert maintenance_hold_active() is False

    hold.write_bytes(b"")
    hold.chmod(0o600)
    assert inspect_maintenance_hold().state == HOLD_INVALID_EMPTY
    assert maintenance_hold_active() is True

    hold.write_text("{broken", encoding="utf-8")
    hold.chmod(0o600)
    assert inspect_maintenance_hold().state == HOLD_INVALID_MALFORMED
    assert maintenance_hold_active() is True

    hold.write_text(json.dumps({"reason": "operator_hold"}), encoding="utf-8")
    hold.chmod(0o600)
    inspection = inspect_maintenance_hold()
    assert inspection.state == HOLD_ACTIVE_VALID
    assert inspection.reason == "operator_hold"
    assert maintenance_hold_active() is True


def test_safe_repair_clears_only_empty_hold_after_all_gates(tmp_path):
    hold = tmp_path / "hold.json"
    hold.write_bytes(b"")
    hold.chmod(0o600)
    guard = tmp_path / "db_workload_guard.py"
    _write_guard(guard)
    backup_dir = tmp_path / "backups"

    result = repair_invalid_empty_hold_if_safe(
        _Client(),
        path=hold,
        guard_path=guard,
        backup_dir=backup_dir,
        expected_owner=_owner(),
        root_free_loader=lambda: 10 * 1024 * 1024 * 1024,
        crontab_loader=lambda: "*/5 * * * * sentinel\n",
        sleep=lambda _seconds: None,
        probe_attempts=1,
    )

    assert result["status"] == "cleared_invalid_empty_hold"
    assert result["mutation_performed"] is True
    assert result["database_probe_market_date"] == "2026-10-02"
    assert not hold.exists()
    backups = list(backup_dir.glob("hold.invalid-empty.*.bak"))
    assert len(backups) == 1
    assert backups[0].stat().st_mode & 0o777 == 0o600


def test_safe_repair_never_clears_valid_or_nonempty_malformed_hold(tmp_path):
    for payload in (
        json.dumps({"reason": "operator_hold"}).encode(),
        b"{broken",
    ):
        hold = tmp_path / "hold.json"
        hold.write_bytes(payload)
        hold.chmod(0o600)

        result = repair_invalid_empty_hold_if_safe(
            _Client(),
            path=hold,
            expected_owner=_owner(),
        )

        assert result["status"] == "blocked"
        assert result["reason"] == "hold_not_invalid_empty"
        assert hold.exists()
        hold.unlink()


def test_safe_repair_blocks_when_disk_headroom_is_low(tmp_path):
    hold = tmp_path / "hold.json"
    hold.write_bytes(b"")
    hold.chmod(0o600)

    result = repair_invalid_empty_hold_if_safe(
        _Client(),
        path=hold,
        expected_owner=_owner(),
        root_free_loader=lambda: 1024,
    )

    assert result["status"] == "blocked"
    assert result["reason"] == "insufficient_root_headroom"
    assert hold.exists()


def test_safe_repair_blocks_when_live_pressure_is_active(tmp_path):
    hold = tmp_path / "hold.json"
    hold.write_bytes(b"")
    hold.chmod(0o600)
    guard = tmp_path / "db_workload_guard.py"
    _write_guard(guard, "available_memory_below_15_percent")

    result = repair_invalid_empty_hold_if_safe(
        _Client(),
        path=hold,
        guard_path=guard,
        expected_owner=_owner(),
        root_free_loader=lambda: 10 * 1024 * 1024 * 1024,
        live_pressure_loader=lambda _path: "available_memory_below_15_percent",
    )

    assert result["status"] == "blocked"
    assert result["reason"] == "live_db_pressure_active"
    assert hold.exists()


def test_safe_repair_blocks_when_code_red_scheduler_is_disabled(tmp_path):
    hold = tmp_path / "hold.json"
    hold.write_bytes(b"")
    hold.chmod(0o600)
    guard = tmp_path / "db_workload_guard.py"
    _write_guard(guard)

    result = repair_invalid_empty_hold_if_safe(
        _Client(),
        path=hold,
        guard_path=guard,
        expected_owner=_owner(),
        root_free_loader=lambda: 10 * 1024 * 1024 * 1024,
        live_pressure_loader=lambda _path: None,
        crontab_loader=lambda: "# CODE_RED_DISABLED * * * * * publisher\n",
    )

    assert result["status"] == "blocked"
    assert result["reason"] == "code_red_scheduler_still_disabled"
    assert hold.exists()
