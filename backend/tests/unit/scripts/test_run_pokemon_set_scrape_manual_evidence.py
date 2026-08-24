import backend.scripts.run_pokemon_set_scrape as runner
from backend.db.services.market_run_evidence import (
    resolve_run_set_id,
    run_metrics_qualify,
)


SET_ID = "00000000-0000-0000-0000-000000000123"
METRICS = {
    "sourceCoverageRatio": 1.0,
    "acceptedVariantGroups": 7,
    "positiveNmObservationCount": 7,
}


class _Config:
    SET_NAME = "Exact Set"
    SEALED_DETAILS_URL = "https://example.invalid/sealed"


class _FakeScraper:
    def __init__(self, enable_db_ingestion=True, target_market_date=None):
        self.enable_db_ingestion = enable_db_ingestion

    def get_request_metrics(self):
        return {}


def _run(monkeypatch, tmp_path, *, ingest=True, exact=True, target_count=1):
    keys = ["exactSet"] if target_count == 1 else ["exactSet", "otherSet"]
    config_map = {key: _Config for key in keys}
    monkeypatch.setattr(runner, "build_valid_set_key_registry", lambda _era: {
        "config_map": config_map,
        "alias_map": {},
        "loaded_eras": ["testEra"],
        "valid_keys": keys,
        "canonical_by_norm": {key.lower(): key for key in keys},
        "registry_source": "SET_CONFIG_MAP",
    })
    rows = [{"id": SET_ID if i == 0 else f"other-{i}",
             "canonical_key": key, "name": key}
            for i, key in enumerate(keys)]
    monkeypatch.setattr(runner, "_load_scrape_targets", lambda _key: rows)
    monkeypatch.setattr(runner, "_is_scraper_enabled", lambda: True)
    monkeypatch.setattr(runner, "_market_date_iso", lambda: "2026-08-24")
    monkeypatch.setattr(
        "backend.Scraper.services.orchestrators.tcg_player_orchestrator.TCGScraper",
        _FakeScraper,
    )
    monkeypatch.setattr(runner, "_jitter_sleep", lambda: None)
    monkeypatch.setattr(runner, "_scrape_one_set", lambda *args: {
        "canonical_key": args[2], "status": "success", "attempt": 1,
        "cards_scraped": 7, "sealed_scraped": 0, "error": None,
        "metadata": dict(METRICS),
    })

    created = []
    finalized = []
    monkeypatch.setattr(
        "backend.db.repositories.scrape_diagnostics_repository.create_scrape_job_run",
        lambda payload: created.append(payload) or {"id": "diag-1"},
    )
    monkeypatch.setattr(
        "backend.db.repositories.scrape_diagnostics_repository.finalize_scrape_job_run",
        lambda run_id, payload: finalized.append(payload) or {"ok": True},
    )
    monkeypatch.setattr(
        "backend.db.repositories.scrape_diagnostics_repository.insert_scrape_job_run_failures",
        lambda rows: rows,
    )

    report = runner.run_scraper(
        dry_run=False, era_filter=None,
        set_key_filter="exactSet" if exact else None,
        limit=None, enable_db_ingestion=ingest, shuffle_within_date=False,
        report_path=tmp_path / "report.json",
    )
    return report, created[0], finalized[0]


def _evidence_row(created, finalized):
    return {**created, **finalized}


def test_exact_manual_db_ingest_persists_authoritative_qualifying_evidence(
        monkeypatch, tmp_path):
    report, created, finalized = _run(monkeypatch, tmp_path)
    row = _evidence_row(created, finalized)

    assert created["queue_job_id"] is None
    assert created["market_date"] == report["market_date"] == "2026-08-24"
    assert finalized["metadata"]["set_id"] == SET_ID
    assert {key: finalized["metadata"][key] for key in METRICS} == METRICS
    assert run_metrics_qualify(row) is True
    assert resolve_run_set_id(row, {}) == SET_ID


def test_no_db_ingest_does_not_claim_identity_or_reconciliation(monkeypatch, tmp_path):
    _, created, finalized = _run(monkeypatch, tmp_path, ingest=False)
    row = _evidence_row(created, finalized)

    assert "set_id" not in finalized["metadata"]
    assert not any(key in finalized["metadata"] for key in METRICS)
    assert run_metrics_qualify(row) is False
    assert resolve_run_set_id(row, {}) is None


def test_multi_set_manual_run_does_not_attach_one_set_identity(monkeypatch, tmp_path):
    _, created, finalized = _run(
        monkeypatch, tmp_path, exact=False, target_count=2)
    row = _evidence_row(created, finalized)

    assert finalized["items_succeeded"] == 2
    assert "set_id" not in finalized["metadata"]
    assert not any(key in finalized["metadata"] for key in METRICS)
    assert run_metrics_qualify(row) is False
    assert resolve_run_set_id(row, {}) is None
