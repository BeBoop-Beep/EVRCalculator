"""Orchestration tests for the one-time historical TCGplayer catalog backfill CLI."""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.db.repositories import pokemon_set_onboarding_repository as repo
from backend.scripts import backfill_ignored_pokemon_catalog_sets as cli
from backend.services import pokemon_historical_catalog_backfill_service as svc


BASE_CONFIG_SOURCE = "class BaseSetConfig:\n    ERA = 'Other'\n"
SET_MAP_SOURCE = "SET_CONFIG_MAP = {\n}\n\nSET_ALIAS_MAP = {\n}\n"


def _pokemon_root(tmp_path: Path) -> Path:
    root = tmp_path / "pokemon"
    era = root / "otherEra"
    era.mkdir(parents=True, exist_ok=True)
    (era / "__init__.py").write_text("", encoding="utf-8")
    (era / "baseConfig.py").write_text(BASE_CONFIG_SOURCE, encoding="utf-8")
    (era / "setMap.py").write_text(SET_MAP_SOURCE, encoding="utf-8")
    return root


def _row(source_set_id="24688", name="Jumbo Cards", metadata=None):
    return {
        "id": f"job-{source_set_id}",
        "tcg": "pokemon",
        "source_system": "tcgplayer",
        "source_set_id": source_set_id,
        "source_set_name": name,
        "status": "ignored",
        "current_step": "catalog_baseline",
        "metadata_json": metadata if metadata is not None else {"onboarded": False},
    }


class _Recorder:
    """Injected dependency double that records every side effect it is asked to make."""

    def __init__(self, rows, *, scrape_result=None, verify_result=None):
        self.rows = rows
        self.updates: list[tuple[str, dict]] = []
        self.synced: list[str] = []
        self.scraped: list[str] = []
        self.api_calls: list[str] = []
        self._scrape_result = scrape_result or {"status": "success", "cards_scraped": 41}
        self._verify_result = verify_result or {
            "set_row_exists": True, "cards_written": 41,
            "canonical_keys_touched": [], "empty_catalog": False,
        }

    def as_deps(self):
        return cli.BackfillDeps(
            list_rows=lambda: self.rows,
            fetch_api_rows=self._fetch_api_rows,
            update_job=self._update_job,
            sync_set=lambda key: self.synced.append(key) or {
                "canonical_key": key, "source_config_path": f"backend/x/{key}.py",
                "card_details_url": "card", "sealed_details_url": "sealed",
                "ready_for_daily_scrape": True, "pokemon_api_set_id": None,
            },
            scrape_set=self._scrape_set,
            verify_scrape=lambda key, report: dict(
                self._verify_result, canonical_keys_touched=[key]
            ),
        )

    def _fetch_api_rows(self, name):
        self.api_calls.append(name)
        return []

    def _update_job(self, job_id, fields):
        self.updates.append((job_id, fields))
        return {"id": job_id, **fields}

    def _scrape_set(self, key):
        self.scraped.append(key)
        return dict(self._scrape_result)


# ---------------------------------------------------------------------------
# 16. Stage ordering
# ---------------------------------------------------------------------------
def test_commit_mode_refuses_stage_all(tmp_path):
    recorder = _Recorder([_row()])

    with pytest.raises(cli.StageOrderError):
        cli.run_backfill(
            commit=True, stage="all", pokemon_root=_pokemon_root(tmp_path), deps=recorder.as_deps()
        )

    assert recorder.updates == []
    assert recorder.scraped == []


def test_dry_run_allows_stage_all_as_a_preview(tmp_path):
    recorder = _Recorder([_row()])

    result = cli.run_backfill(
        commit=False, stage="all", pokemon_root=_pokemon_root(tmp_path), deps=recorder.as_deps()
    )

    assert result["summary"]["dry_run"] is True
    assert result["summary"]["selected"] == 1


# ---------------------------------------------------------------------------
# 1. Dry run performs no source, database, or scrape writes
# ---------------------------------------------------------------------------
def test_dry_run_performs_no_source_database_or_scrape_writes(tmp_path):
    root = _pokemon_root(tmp_path)
    set_map_before = (root / "otherEra" / "setMap.py").read_text(encoding="utf-8")
    files_before = sorted(path.name for path in (root / "otherEra").glob("*.py"))
    recorder = _Recorder([_row(), _row("30001", "Energy Catalog")])

    result = cli.run_backfill(commit=False, stage="all", pokemon_root=root, deps=recorder.as_deps())

    assert recorder.updates == []
    assert recorder.synced == []
    assert recorder.scraped == []
    assert sorted(path.name for path in (root / "otherEra").glob("*.py")) == files_before
    assert not (root / "otherEra" / "jumboCards.py").exists()
    assert (root / "otherEra" / "setMap.py").read_text(encoding="utf-8") == set_map_before
    assert result["summary"]["configs_generated"] == 2
    assert result["summary"]["catalog_only"] == 2


# ---------------------------------------------------------------------------
# 11. Report + summary contract
# ---------------------------------------------------------------------------
def test_configs_stage_reports_every_required_field_per_row(tmp_path):
    recorder = _Recorder([_row()])

    result = cli.run_backfill(
        commit=True, stage="configs", pokemon_root=_pokemon_root(tmp_path), deps=recorder.as_deps()
    )

    row = result["rows"][0]
    for field in (
        "source_set_id", "source_set_name", "canonical_key", "era_folder", "api_match_status",
        "pokemon_api_set_id", "card_details_url", "sealed_details_url", "collision",
        "config_path", "set_map_path", "readiness", "error",
    ):
        assert field in row, field
    assert set(result["summary"]) >= {
        "selected", "already_completed", "configs_generated", "api_backed", "catalog_only",
        "synced", "scraped_successfully", "empty_catalogs", "failed", "remaining", "dry_run",
    }


# ---------------------------------------------------------------------------
# 15. Status transitions
# ---------------------------------------------------------------------------
def test_configs_stage_commit_keeps_rows_ignored_and_unonboarded(tmp_path):
    recorder = _Recorder([_row()])

    cli.run_backfill(
        commit=True, stage="configs", pokemon_root=_pokemon_root(tmp_path), deps=recorder.as_deps()
    )

    (_job_id, fields) = recorder.updates[0]
    assert fields["status"] == "ignored"
    assert fields["metadata_json"]["onboarded"] is False
    assert fields["metadata_json"]["historical_backfill"]["canonical_key"] == "jumboCards"


def test_successful_scrape_marks_the_row_completed(tmp_path):
    metadata = {
        "onboarded": False,
        "historical_backfill": {"canonical_key": "jumboCards", "config_status": "generated"},
    }
    recorder = _Recorder([_row(metadata=metadata)])

    result = cli.run_backfill(
        commit=True, stage="scrape", pokemon_root=_pokemon_root(tmp_path), deps=recorder.as_deps()
    )

    assert recorder.scraped == ["jumboCards"]
    (_job_id, fields) = recorder.updates[-1]
    assert fields["status"] == "completed"
    assert fields["current_step"] == "historical_scrape_complete"
    assert fields["metadata_json"]["onboarded"] is True
    assert fields["completed_at"]
    assert result["summary"]["scraped_successfully"] == 1


def test_failed_scrape_leaves_the_row_ignored_and_retryable(tmp_path):
    metadata = {
        "onboarded": False,
        "historical_backfill": {"canonical_key": "jumboCards", "config_status": "generated"},
    }
    recorder = _Recorder(
        [_row(metadata=metadata)], scrape_result={"status": "failed", "error": "provider 500"}
    )

    result = cli.run_backfill(
        commit=True, stage="scrape", pokemon_root=_pokemon_root(tmp_path), deps=recorder.as_deps()
    )

    (_job_id, fields) = recorder.updates[-1]
    assert fields["status"] == "ignored"
    assert fields["metadata_json"]["onboarded"] is False
    assert result["summary"]["failed"] == 1
    assert result["summary"]["scraped_successfully"] == 0


def test_scrape_that_touched_an_unrelated_set_is_recorded_as_a_failure(tmp_path):
    metadata = {
        "onboarded": False,
        "historical_backfill": {"canonical_key": "jumboCards", "config_status": "generated"},
    }
    recorder = _Recorder([_row(metadata=metadata)])
    deps = recorder.as_deps()
    deps.verify_scrape = lambda key, report: {
        "set_row_exists": True, "cards_written": 41,
        "canonical_keys_touched": [key, "surgingSparks"], "empty_catalog": False,
    }

    result = cli.run_backfill(
        commit=True, stage="scrape", pokemon_root=_pokemon_root(tmp_path), deps=deps
    )

    assert result["summary"]["failed"] == 1
    (_job_id, fields) = recorder.updates[-1]
    assert fields["status"] == "ignored"


def test_genuinely_empty_provider_catalog_still_completes_the_row(tmp_path):
    metadata = {
        "onboarded": False,
        "historical_backfill": {"canonical_key": "jumboCards", "config_status": "generated"},
    }
    recorder = _Recorder(
        [_row(metadata=metadata)],
        scrape_result={"status": "success", "cards_scraped": 0},
        verify_result={
            "set_row_exists": True, "cards_written": 0,
            "canonical_keys_touched": [], "empty_catalog": True,
        },
    )

    result = cli.run_backfill(
        commit=True, stage="scrape", pokemon_root=_pokemon_root(tmp_path), deps=recorder.as_deps()
    )

    assert result["summary"]["empty_catalogs"] == 1
    assert result["summary"]["scraped_successfully"] == 1
    assert recorder.updates[-1][1]["status"] == "completed"


# ---------------------------------------------------------------------------
# 10. Resume
# ---------------------------------------------------------------------------
def test_resume_skips_rows_a_previous_run_already_scraped(tmp_path):
    done = _row("111", "Done Catalog", metadata={
        "onboarded": False,
        "historical_backfill": {"canonical_key": "doneCatalog", "scrape_status": "success"},
    })
    pending = _row("222", "Pending Catalog", metadata={
        "onboarded": False,
        "historical_backfill": {"canonical_key": "pendingCatalog", "config_status": "generated"},
    })
    recorder = _Recorder([done, pending])

    result = cli.run_backfill(
        commit=True, stage="scrape", resume=True,
        pokemon_root=_pokemon_root(tmp_path), deps=recorder.as_deps(),
    )

    assert recorder.scraped == ["pendingCatalog"]
    assert result["summary"]["already_completed"] == 1


# ---------------------------------------------------------------------------
# 12. Sync stage delegates to the existing constants -> public.sets sync
# ---------------------------------------------------------------------------
def test_sync_stage_only_syncs_generated_canonical_keys(tmp_path):
    generated = _row("222", "Pending Catalog", metadata={
        "onboarded": False,
        "historical_backfill": {"canonical_key": "pendingCatalog", "config_status": "generated"},
    })
    not_generated = _row("333", "Untouched Catalog")
    recorder = _Recorder([generated, not_generated])

    result = cli.run_backfill(
        commit=True, stage="sync", pokemon_root=_pokemon_root(tmp_path), deps=recorder.as_deps()
    )

    assert recorder.synced == ["pendingCatalog"]
    assert result["summary"]["synced"] == 1


def test_sync_stage_flags_a_row_whose_public_set_is_not_scrape_ready(tmp_path):
    generated = _row("222", "Pending Catalog", metadata={
        "onboarded": False,
        "historical_backfill": {"canonical_key": "pendingCatalog", "config_status": "generated"},
    })
    recorder = _Recorder([generated])
    deps = recorder.as_deps()
    deps.sync_set = lambda key: {
        "canonical_key": key, "source_config_path": None, "card_details_url": None,
        "sealed_details_url": None, "ready_for_daily_scrape": False, "pokemon_api_set_id": None,
    }

    result = cli.run_backfill(
        commit=True, stage="sync", pokemon_root=_pokemon_root(tmp_path), deps=deps
    )

    assert result["summary"]["synced"] == 0
    assert result["summary"]["failed"] == 1


# ---------------------------------------------------------------------------
# 11 / repository guards: normal discovery and the onboarding worker are untouched
# ---------------------------------------------------------------------------
def test_baseline_selector_reads_only_ignored_catalog_baseline_rows(monkeypatch):
    recorder: dict = {}

    class _Query:
        def select(self, *_a, **_k):
            return self

        def eq(self, column, value):
            recorder[column] = value
            return self

        def order(self, *_a, **_k):
            return self

        def limit(self, *_a, **_k):
            return self

        def execute(self):
            return type("R", (), {"data": []})()

    monkeypatch.setattr(repo, "supabase", type("S", (), {"table": lambda _s, _n: _Query()})())

    repo.list_baseline_catalog_jobs()

    assert recorder["status"] == svc.BASELINE_STATUS == "ignored"
    assert recorder["current_step"] == svc.BASELINE_STEP == "catalog_baseline"
    assert recorder["source_system"] == "tcgplayer"


def test_baseline_job_update_is_guarded_to_rows_that_are_still_ignored(monkeypatch):
    recorder: dict = {"eq": []}

    class _Query:
        def update(self, payload):
            recorder["payload"] = payload
            return self

        def eq(self, column, value):
            recorder["eq"].append((column, value))
            return self

        def execute(self):
            return type("R", (), {"data": [{"id": "job-1"}]})()

    monkeypatch.setattr(repo, "supabase", type("S", (), {"table": lambda _s, _n: _Query()})())

    repo.update_baseline_job("job-1", {"status": "completed"})

    assert ("id", "job-1") in recorder["eq"]
    assert ("status", "ignored") in recorder["eq"]
    assert ("current_step", "catalog_baseline") in recorder["eq"]


def test_api_lookup_retries_transient_provider_failures_before_giving_up():
    attempts = []

    def _flaky(name, key):
        attempts.append(name)
        if len(attempts) < 3:
            raise RuntimeError("500 Server Error")
        return [{"id": "base1", "name": name}]

    rows = cli.fetch_api_rows_with_retry(
        "Expedition", api_key="k", fetch=_flaky, attempts=3, sleep=lambda _s: None
    )

    assert rows == [{"id": "base1", "name": "Expedition"}]
    assert len(attempts) == 3


def test_api_lookup_returns_none_only_after_every_attempt_failed():
    def _always_500(_name, _key):
        raise RuntimeError("500 Server Error")

    rows = cli.fetch_api_rows_with_retry(
        "Expedition", api_key="k", fetch=_always_500, attempts=3, sleep=lambda _s: None
    )

    assert rows is None


def test_api_lookup_does_not_retry_a_genuine_empty_result():
    calls = []

    def _empty(name, _key):
        calls.append(name)
        return []

    assert cli.fetch_api_rows_with_retry(
        "Jumbo Cards", api_key="k", fetch=_empty, attempts=3, sleep=lambda _s: None
    ) == []
    assert len(calls) == 1


def test_backfill_never_writes_a_worker_claimable_status(tmp_path):
    claimable = {"detected", "ready", "retry", "running", "waiting", "manual_review"}
    rows = [
        _row("1", "A"),
        _row("2", "B", metadata={
            "onboarded": False,
            "historical_backfill": {"canonical_key": "b", "config_status": "generated"},
        }),
    ]
    recorder = _Recorder(rows, scrape_result={"status": "failed", "error": "boom"})

    cli.run_backfill(
        commit=True, stage="configs", pokemon_root=_pokemon_root(tmp_path), deps=recorder.as_deps()
    )
    cli.run_backfill(
        commit=True, stage="scrape", pokemon_root=_pokemon_root(tmp_path), deps=recorder.as_deps()
    )

    assert recorder.updates
    for _job_id, fields in recorder.updates:
        assert fields["status"] not in claimable
