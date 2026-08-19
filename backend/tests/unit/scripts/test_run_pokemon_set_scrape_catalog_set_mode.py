"""Contract tests for the manual catalog-only single-set scrape mode.

`--catalog-set` is an explicit auxiliary target mode: it scrapes a set that is
deliberately excluded from the coordinated daily cohort (ready_for_daily_scrape
= false, catalog_only = true). These tests pin the two things that make that
safe — it can ONLY select a genuinely catalog-only set, and it never touches a
lifecycle flag — plus the reuse guarantee that it runs through the same
TCGScraper execution path as an ordinary set.
"""

import pytest

import backend.scripts.run_pokemon_set_scrape as runner


CATALOG_KEY = "svScarletAndVioletPromoCards"
ORDINARY_KEY = "blackBolt"


def _db_row(canonical_key, **overrides):
    row = {
        "id": "00000000-0000-0000-0000-0000000000aa",
        "name": "SV: Scarlet & Violet Promo Cards",
        "canonical_key": canonical_key,
        "card_details_url": "https://infinite-api.tcgplayer.com/priceguide/set/22872/cards/?rows=5000&productTypeID=1",
        "sealed_details_url": "https://infinite-api.tcgplayer.com/priceguide/set/22872/cards/?rows=5000&productTypeID=25",
        "release_date": None,
        "era_id": None,
        "ready_for_daily_scrape": False,
        "catalog_only": True,
        "supports_opening_simulation": False,
    }
    row.update(overrides)
    return row


def _loader(row):
    def load(canonical_key):
        if row is None:
            return None
        return row if row.get("canonical_key") == canonical_key else None

    return load


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def test_catalog_set_argument_parses():
    args = runner._build_parser().parse_args(["--run", "--catalog-set", CATALOG_KEY])

    assert args.catalog_set_key == CATALOG_KEY
    assert args.run is True


@pytest.mark.parametrize(
    "conflicting",
    [["--set", ORDINARY_KEY], ["--era", "otherEra"], ["--limit", "3"]],
    ids=["set", "era", "limit"],
)
def test_catalog_set_conflicts_are_rejected(monkeypatch, capsys, conflicting):
    monkeypatch.setattr(
        "sys.argv",
        ["run_pokemon_set_scrape.py", "--catalog-set", CATALOG_KEY, *conflicting],
    )
    with pytest.raises(SystemExit) as excinfo:
        runner.main()

    assert excinfo.value.code == 2
    stderr = capsys.readouterr().err
    assert "--catalog-set" in stderr
    assert "cannot be combined" in stderr
    assert conflicting[0] in stderr


# ---------------------------------------------------------------------------
# Target resolution
# ---------------------------------------------------------------------------
def test_catalog_set_resolves_exact_catalog_only_set():
    registry = runner.build_valid_set_key_registry()

    target = runner.resolve_catalog_set_target(
        CATALOG_KEY, registry, load_set_row=_loader(_db_row(CATALOG_KEY))
    )

    assert target["canonical_key"] == CATALOG_KEY
    assert target["_config_cls"] is registry["config_map"][CATALOG_KEY]
    assert target["_config_cls"].CARD_DETAILS_URL


def test_catalog_set_refuses_a_non_catalog_set():
    registry = runner.build_valid_set_key_registry()
    row = _db_row(
        ORDINARY_KEY,
        ready_for_daily_scrape=True,
        catalog_only=False,
        supports_opening_simulation=True,
    )

    with pytest.raises(runner.CatalogSetResolutionError) as excinfo:
        runner.resolve_catalog_set_target(ORDINARY_KEY, registry, load_set_row=_loader(row))

    assert "catalog_only" in str(excinfo.value)


def test_catalog_set_refuses_unknown_key_clearly():
    registry = runner.build_valid_set_key_registry()

    with pytest.raises(runner.CatalogSetResolutionError) as excinfo:
        runner.resolve_catalog_set_target("fakeSet123", registry, load_set_row=_loader(None))

    message = str(excinfo.value)
    assert "fakeSet123" in message
    assert "SET_CONFIG_MAP" in message


def test_catalog_set_refuses_when_db_row_is_missing():
    registry = runner.build_valid_set_key_registry()

    with pytest.raises(runner.CatalogSetResolutionError) as excinfo:
        runner.resolve_catalog_set_target(CATALOG_KEY, registry, load_set_row=_loader(None))

    assert "no sets row" in str(excinfo.value)


def test_catalog_set_refuses_when_db_and_config_disagree():
    """DB says catalog-only, runtime config does not: fail closed."""
    registry = runner.build_valid_set_key_registry()
    config_map = dict(registry["config_map"])

    class _DisagreeingConfig(config_map[CATALOG_KEY]):
        CATALOG_ONLY = False

    config_map[CATALOG_KEY] = _DisagreeingConfig
    registry = {**registry, "config_map": config_map}

    with pytest.raises(runner.CatalogSetResolutionError) as excinfo:
        runner.resolve_catalog_set_target(
            CATALOG_KEY, registry, load_set_row=_loader(_db_row(CATALOG_KEY))
        )

    assert "disagree" in str(excinfo.value)


# ---------------------------------------------------------------------------
# The ordinary daily path is untouched
# ---------------------------------------------------------------------------
def test_ordinary_set_filter_cannot_select_a_catalog_only_set(monkeypatch):
    """The daily path reads the ready-only accessor, which never returns it."""
    ready_rows = [_db_row(ORDINARY_KEY, ready_for_daily_scrape=True,
                          catalog_only=False, supports_opening_simulation=True)]

    monkeypatch.setattr(
        "backend.db.repositories.tcgs_repository.get_tcg_by_name",
        lambda name: {"id": "tcg-1"} if name == "Pokemon" else None,
    )
    monkeypatch.setattr(
        "backend.db.repositories.sets_repository.get_scrape_ready_sets_by_tcg_id",
        lambda tcg_id: list(ready_rows),
    )

    assert runner._load_scrape_targets(CATALOG_KEY) == []


def test_normal_daily_target_loading_is_unchanged(monkeypatch):
    ready_rows = [
        _db_row("a", ready_for_daily_scrape=True, catalog_only=False),
        _db_row("b", ready_for_daily_scrape=True, catalog_only=False),
    ]
    calls = {}

    monkeypatch.setattr(
        "backend.db.repositories.tcgs_repository.get_tcg_by_name",
        lambda name: {"id": "tcg-1"} if name == "Pokemon" else None,
    )

    def _fake_ready(tcg_id):
        calls["tcg_id"] = tcg_id
        return list(ready_rows)

    monkeypatch.setattr(
        "backend.db.repositories.sets_repository.get_scrape_ready_sets_by_tcg_id",
        _fake_ready,
    )

    assert [r["canonical_key"] for r in runner._load_scrape_targets(None)] == ["a", "b"]
    assert calls["tcg_id"] == "tcg-1"


# ---------------------------------------------------------------------------
# Run modes
# ---------------------------------------------------------------------------
def _no_lifecycle_writes(monkeypatch):
    def _explode(*args, **kwargs):
        raise AssertionError("catalog-set mode must never write to the sets table")

    monkeypatch.setattr("backend.db.repositories.sets_repository.update_set_by_id", _explode)
    monkeypatch.setattr("backend.db.repositories.sets_repository.insert_set", _explode)


def test_catalog_set_dry_run_reports_catalog_target_mode(monkeypatch, tmp_path):
    _no_lifecycle_writes(monkeypatch)
    monkeypatch.setattr(
        runner,
        "_scrape_one_set",
        lambda *a, **k: pytest.fail("dry-run must not scrape"),
    )

    report = runner.run_scraper(
        dry_run=True,
        era_filter=None,
        set_key_filter=None,
        limit=None,
        enable_db_ingestion=True,
        shuffle_within_date=False,
        report_path=tmp_path / "report.json",
        catalog_set_key=CATALOG_KEY,
        set_row_loader=_loader(_db_row(CATALOG_KEY)),
    )

    assert report["mode"] == "dry_run"
    assert report["sets_selected"] == 1
    assert report["target_mode"] == "catalog_set_manual"
    assert report["catalog_set"] == CATALOG_KEY
    assert report["catalog_only"] is True
    assert report["ready_for_daily_scrape"] is False
    assert report["supports_opening_simulation"] is False
    assert report["daily_cohort_modified"] is False


def test_catalog_set_run_uses_the_same_scraper_execution_path(monkeypatch, tmp_path):
    _no_lifecycle_writes(monkeypatch)
    seen = {}

    class _FakeScraper:
        def __init__(self, enable_db_ingestion=True, target_market_date=None):
            seen["enable_db_ingestion"] = enable_db_ingestion
            seen["target_market_date"] = target_market_date

        def get_request_metrics(self):
            return {"http_requests_total": 1}

    monkeypatch.setattr(
        "backend.Scraper.services.orchestrators.tcg_player_orchestrator.TCGScraper",
        _FakeScraper,
    )
    monkeypatch.setattr(
        "backend.db.repositories.scrape_diagnostics_repository.create_scrape_job_run",
        lambda payload: None,
    )

    original = runner._scrape_one_set

    def _spy(scraper, config_cls, canonical_key, index, total, market_date):
        seen["canonical_key"] = canonical_key
        seen["config_cls"] = config_cls
        seen["scraper"] = scraper
        seen["market_date"] = market_date
        return {
            "canonical_key": canonical_key,
            "status": "success",
            "attempt": 1,
            "cards_scraped": 42,
            "sealed_scraped": 0,
            "error": None,
        }

    assert callable(original)
    monkeypatch.setattr(runner, "_scrape_one_set", _spy)

    report = runner.run_scraper(
        dry_run=False,
        era_filter=None,
        set_key_filter=None,
        limit=None,
        enable_db_ingestion=True,
        shuffle_within_date=False,
        report_path=tmp_path / "report.json",
        catalog_set_key=CATALOG_KEY,
        set_row_loader=_loader(_db_row(CATALOG_KEY)),
    )

    assert seen["canonical_key"] == CATALOG_KEY
    assert isinstance(seen["scraper"], _FakeScraper)
    assert seen["config_cls"].CARD_DETAILS_URL
    assert seen["enable_db_ingestion"] is True
    assert seen["target_market_date"] == seen["market_date"] == report["market_date"]
    assert report["sets_succeeded"] == 1
    assert report["target_mode"] == "catalog_set_manual"
    assert report["daily_cohort_modified"] is False


def test_catalog_set_run_honors_no_db_ingest(monkeypatch, tmp_path):
    _no_lifecycle_writes(monkeypatch)
    seen = {}

    class _FakeScraper:
        def __init__(self, enable_db_ingestion=True, target_market_date=None):
            seen["enable_db_ingestion"] = enable_db_ingestion
            seen["target_market_date"] = target_market_date

        def get_request_metrics(self):
            return {}

    monkeypatch.setattr(
        "backend.Scraper.services.orchestrators.tcg_player_orchestrator.TCGScraper",
        _FakeScraper,
    )
    monkeypatch.setattr(
        "backend.db.repositories.scrape_diagnostics_repository.create_scrape_job_run",
        lambda payload: None,
    )
    monkeypatch.setattr(
        runner,
        "_scrape_one_set",
        lambda *a, **k: {
            "canonical_key": CATALOG_KEY,
            "status": "success",
            "attempt": 1,
            "cards_scraped": 1,
            "sealed_scraped": 0,
            "error": None,
        },
    )

    report = runner.run_scraper(
        dry_run=False,
        era_filter=None,
        set_key_filter=None,
        limit=None,
        enable_db_ingestion=False,
        shuffle_within_date=False,
        report_path=tmp_path / "report.json",
        catalog_set_key=CATALOG_KEY,
        set_row_loader=_loader(_db_row(CATALOG_KEY)),
    )

    assert seen["enable_db_ingestion"] is False
    assert report["db_ingestion_enabled"] is False


def test_catalog_set_run_fails_closed_on_a_non_catalog_set(monkeypatch, tmp_path):
    _no_lifecycle_writes(monkeypatch)
    monkeypatch.setattr(
        runner,
        "_scrape_one_set",
        lambda *a, **k: pytest.fail("must not scrape a non-catalog set"),
    )
    row = _db_row(ORDINARY_KEY, ready_for_daily_scrape=True, catalog_only=False,
                  supports_opening_simulation=True)

    report = runner.run_scraper(
        dry_run=False,
        era_filter=None,
        set_key_filter=None,
        limit=None,
        enable_db_ingestion=True,
        shuffle_within_date=False,
        report_path=tmp_path / "report.json",
        catalog_set_key=ORDINARY_KEY,
        set_row_loader=_loader(row),
    )

    assert report["run_aborted_early"] is True
    assert report["run_abort_reason"] == "invalid_catalog_set"
    assert report["sets_selected"] == 0


def test_normal_run_report_is_not_labelled_catalog(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "backend.db.repositories.tcgs_repository.get_tcg_by_name",
        lambda name: {"id": "tcg-1"} if name == "Pokemon" else None,
    )
    monkeypatch.setattr(
        "backend.db.repositories.sets_repository.get_scrape_ready_sets_by_tcg_id",
        lambda tcg_id: [],
    )

    report = runner.run_scraper(
        dry_run=True,
        era_filter=None,
        set_key_filter=None,
        limit=None,
        enable_db_ingestion=True,
        shuffle_within_date=False,
        report_path=tmp_path / "report.json",
    )

    assert report["target_mode"] == "daily_scrape_ready"
    assert report.get("catalog_set") is None
    assert report["daily_cohort_modified"] is False
