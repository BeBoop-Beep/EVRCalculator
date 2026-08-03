"""Runtime/database registry preflight.

These tests encode the 2026-08-03 failure directly: the database cohort named
canonical keys the deployed runtime could not resolve. The preflight must catch
that BEFORE a batch exists, and batch creation must refuse to proceed.
"""

from __future__ import annotations

import pytest

from backend.db.services.pokemon_scrape_runtime_preflight import (
    run_runtime_preflight,
)


class _Config:
    def __init__(self, url="https://www.tcgplayer.com/card", catalog_only=False, supports_sim=True):
        self.CARD_DETAILS_URL = url
        self.CATALOG_ONLY = catalog_only
        self.SUPPORTS_OPENING_SIMULATION = supports_sim


def _registry(config_map):
    return {
        "config_map": config_map,
        "valid_keys": sorted(config_map),
        "loaded_eras": ["testEra"],
    }


def _db_row(key, config, **overrides):
    row = {
        "id": f"id-{key}",
        "canonical_key": key,
        "card_details_url": config.CARD_DETAILS_URL,
        "has_card_details_url": True,
        "ready_for_daily_scrape": True,
        "catalog_only": False,
        "supports_opening_simulation": config.SUPPORTS_OPENING_SIMULATION,
    }
    row.update(overrides)
    return row


def test_preflight_passes_when_cohort_equals_runtime_registry():
    configs = {"setA": _Config(), "setB": _Config("https://www.tcgplayer.com/b")}
    rows = [_db_row(key, cfg) for key, cfg in configs.items()]

    report = run_runtime_preflight(
        registry_loader=lambda: _registry(configs), cohort_loader=lambda: rows
    )

    assert report.ok is True
    assert report.mismatch_count == 0
    assert report.local_eligible_key_count == 2
    assert report.database_cohort_count == 2
    assert report.registry_hashes_match is True


def test_preflight_fails_on_missing_runtime_key():
    """The exact August 3 condition: DB knows a key this runtime does not."""
    configs = {"setA": _Config()}
    rows = [_db_row("setA", configs["setA"]), _db_row("wotcPromo", _Config())]

    report = run_runtime_preflight(
        registry_loader=lambda: _registry(configs), cohort_loader=lambda: rows
    )

    assert report.ok is False
    assert report.missing_local_keys == ["wotcPromo"]
    assert report.registry_hashes_match is False


def test_preflight_fails_on_wrong_checkout_registry_mismatch():
    """A wholly different checkout: nothing lines up in either direction."""
    deployed = {"oldSet": _Config("https://www.tcgplayer.com/old")}
    rows = [_db_row("newSet", _Config("https://www.tcgplayer.com/new"))]

    report = run_runtime_preflight(
        registry_loader=lambda: _registry(deployed), cohort_loader=lambda: rows
    )

    assert report.ok is False
    assert "newSet" in report.missing_local_keys
    assert "oldSet" in report.unexpected_db_keys
    assert report.registry_hashes_match is False


def test_preflight_reports_url_mismatch():
    configs = {"setA": _Config("https://www.tcgplayer.com/correct")}
    rows = [_db_row("setA", configs["setA"], card_details_url="https://www.tcgplayer.com/WRONG")]

    report = run_runtime_preflight(
        registry_loader=lambda: _registry(configs), cohort_loader=lambda: rows
    )

    assert report.ok is False
    assert report.url_mismatches[0]["canonical_key"] == "setA"


def test_preflight_tolerates_benign_url_formatting_differences():
    configs = {"setA": _Config("https://www.tcgplayer.com/card")}
    rows = [_db_row("setA", configs["setA"], card_details_url="https://WWW.TCGplayer.com/card/ ")]

    report = run_runtime_preflight(
        registry_loader=lambda: _registry(configs), cohort_loader=lambda: rows
    )

    assert report.url_mismatches == []
    assert report.ok is True


def test_preflight_flags_catalog_only_row_in_cohort():
    configs = {"promoSet": _Config(catalog_only=True, supports_sim=False)}
    rows = [_db_row("promoSet", configs["promoSet"])]

    report = run_runtime_preflight(
        registry_loader=lambda: _registry(configs), cohort_loader=lambda: rows
    )

    assert report.ok is False
    # It is not locally eligible, so it reads as the DB being ahead of runtime.
    assert "promoSet" in report.missing_local_keys
    assert any(m["field"] == "catalog_only" for m in report.lifecycle_flag_mismatches)


def test_preflight_is_fail_closed_when_authority_is_unreadable():
    def _boom():
        raise RuntimeError("postgrest unavailable")

    report = run_runtime_preflight(
        registry_loader=lambda: _registry({"setA": _Config()}), cohort_loader=_boom
    )

    assert report.ok is False
    assert "postgrest unavailable" in (report.error or "")


def test_preflight_report_records_runtime_provenance():
    report = run_runtime_preflight(
        registry_loader=lambda: _registry({"setA": _Config()}),
        cohort_loader=lambda: [_db_row("setA", _Config())],
    )
    payload = report.to_dict()

    runtime = payload["runtime"]
    assert set(runtime) >= {
        "git_sha",
        "git_branch",
        "repository_root",
        "python_executable",
        "loaded_eras",
        "working_directory",
        "pythonpath",
    }
    assert payload["hashes"]["local_eligible_registry_sha256"]
    assert runtime["loaded_eras"] == ["testEra"]


def test_registry_hash_is_stable_and_order_independent():
    configs = {"b": _Config("https://x/b"), "a": _Config("https://x/a")}
    reversed_configs = {"a": configs["a"], "b": configs["b"]}

    first = run_runtime_preflight(
        registry_loader=lambda: _registry(configs), cohort_loader=lambda: []
    )
    second = run_runtime_preflight(
        registry_loader=lambda: _registry(reversed_configs), cohort_loader=lambda: []
    )

    assert first.local_registry_hash == second.local_registry_hash


# --- batch creation must refuse to run on a failed preflight -----------------
def test_batch_rpc_is_not_called_when_preflight_fails(monkeypatch):
    from backend.scripts import create_daily_scrape_batch as module

    called = {"batch": 0}

    def _fail_if_called(*args, **kwargs):
        called["batch"] += 1
        raise AssertionError("create_daily_scrape_batch must not be called after a failed preflight")

    monkeypatch.setattr(module, "create_daily_scrape_batch", _fail_if_called)
    monkeypatch.setattr(module, "alert_sent", None, raising=False)

    failing = run_runtime_preflight(
        registry_loader=lambda: _registry({"setA": _Config()}),
        cohort_loader=lambda: [_db_row("ghostSet", _Config())],
    )

    with pytest.raises(module.PreflightFailedError):
        module.run_preflight_or_fail("2026-08-03", preflight_runner=lambda: failing)

    assert called["batch"] == 0


def test_successful_preflight_allows_batch_creation():
    from backend.scripts import create_daily_scrape_batch as module

    passing = run_runtime_preflight(
        registry_loader=lambda: _registry({"setA": _Config()}),
        cohort_loader=lambda: [_db_row("setA", _Config())],
    )

    returned = module.run_preflight_or_fail("2026-08-03", preflight_runner=lambda: passing)
    assert returned.ok is True
