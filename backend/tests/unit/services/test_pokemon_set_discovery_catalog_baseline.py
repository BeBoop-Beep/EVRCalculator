"""Cold-start catalog baseline: historical provider sets must not be reported as new."""

from pathlib import Path

import pytest

from backend.services import pokemon_new_set_discovery_service as service

# Stand-in for the production evidence: historical/inactive catalog products that the
# provider still returns (Base Set, EX/XY era, promos, Trainer Kits, Jumbo Cards).
HISTORICAL_CATALOG = [
    {"value": "Base Set", "count": 102},
    {"value": "EX Ruby & Sapphire", "count": 109},
    {"value": "XY Evolutions", "count": 113},
    {"value": "Nintendo Black Star Promos", "count": 53},
    {"value": "Team Rocket Trainer Kit", "count": 20},
    {"value": "Jumbo Cards", "count": 41},
]
RESOLVED_IDS = {
    "Base Set": 604,
    "EX Ruby & Sapphire": 1520,
    "XY Evolutions": 1842,
    "Nintendo Black Star Promos": 1418,
    "Team Rocket Trainer Kit": 1725,
    "Jumbo Cards": 2360,
}


@pytest.fixture
def empty_root(tmp_path: Path) -> Path:
    root = tmp_path / "pokemon"
    root.mkdir()
    return root


def _wire_provider(monkeypatch, aggregations, resolved=None):
    resolved = RESOLVED_IDS if resolved is None else resolved
    monkeypatch.setattr(service, "fetch_global_set_aggregations", lambda *_a, **_k: aggregations)
    monkeypatch.setattr(
        service, "validate_candidate_set_id",
        lambda _requester, _cache, name, *_a, **_k: (resolved.get(name), 0.99, "stable"),
    )


def _wire_store(monkeypatch, stored: dict):
    """Fake onboarding table keyed by provider identity, mirroring the unique constraint."""
    monkeypatch.setattr(
        service, "_database_catalog",
        lambda: (
            set(),
            set(stored),
            {key for key, row in stored.items() if row["status"] == service.BASELINE_STATUS},
        ),
    )
    monkeypatch.setattr(
        service.jobs, "upsert_discovery",
        lambda row: stored.__setitem__(row["source_set_id"], row) or row,
    )


def test_cold_start_discovery_reports_historical_catalog_as_detected(monkeypatch, empty_root):
    """Reproduces the defect: with no baseline, the whole back catalog looks new."""
    _wire_store(monkeypatch, {})
    _wire_provider(monkeypatch, HISTORICAL_CATALOG)
    result = service.discover_new_sets(commit=False, pokemon_root=empty_root)
    assert result["detected"] == len(HISTORICAL_CATALOG)


def test_baseline_dry_run_writes_nothing_and_reports_exact_count(monkeypatch, empty_root):
    stored: dict = {}
    _wire_store(monkeypatch, stored)
    _wire_provider(monkeypatch, HISTORICAL_CATALOG)
    monkeypatch.setattr(
        service.jobs, "upsert_discovery",
        lambda row: pytest.fail("baseline dry-run must not write"),
    )
    monkeypatch.setattr(service, "queue_alert", lambda *a, **k: pytest.fail("baseline must not alert"))

    result = service.baseline_current_catalog(commit=False, pokemon_root=empty_root)

    assert result["dry_run"] is True
    assert result["mode"] == "baseline"
    assert result["would_baseline"] == len(HISTORICAL_CATALOG)
    assert result["baselined"] == 0
    assert stored == {}


def test_baseline_commit_creates_only_ignored_non_runnable_identities(monkeypatch, empty_root):
    stored: dict = {}
    _wire_store(monkeypatch, stored)
    _wire_provider(monkeypatch, HISTORICAL_CATALOG)
    monkeypatch.setattr(service, "queue_alert", lambda *a, **k: pytest.fail("baseline must not alert"))

    result = service.baseline_current_catalog(commit=True, pokemon_root=empty_root)

    assert result["baselined"] == len(HISTORICAL_CATALOG)
    assert len(stored) == len(HISTORICAL_CATALOG)
    assert {row["status"] for row in stored.values()} == {"ignored"}
    assert {row["current_step"] for row in stored.values()} == {"catalog_baseline"}
    # Nothing runnable may be produced by a baseline pass.
    assert not {row["status"] for row in stored.values()} & {"detected", "ready", "retry"}

    row = stored["604"]
    assert row["metadata_json"]["onboarded"] is False
    assert "initial TCGplayer catalog baseline" in row["metadata_json"]["baseline_reason"]
    assert "NOT onboarded" in row["metadata_json"]["baseline_reason"]


def test_baseline_is_idempotent(monkeypatch, empty_root):
    stored: dict = {}
    _wire_store(monkeypatch, stored)
    _wire_provider(monkeypatch, HISTORICAL_CATALOG)

    first = service.baseline_current_catalog(commit=True, pokemon_root=empty_root)
    second = service.baseline_current_catalog(commit=True, pokemon_root=empty_root)

    assert first["baselined"] == len(HISTORICAL_CATALOG)
    assert second["baselined"] == 0
    assert second["would_baseline"] == 0
    assert second["already_baselined"] == len(HISTORICAL_CATALOG)
    assert len(stored) == len(HISTORICAL_CATALOG)


def test_baseline_leaves_local_and_database_identities_untouched(monkeypatch, empty_root):
    (empty_root / "base_set.py").write_text(
        "SET_NAME = 'Base Set'\nCARD_DETAILS_URL = "
        "'https://infinite-api.tcgplayer.com/priceguide/set/604/cards/?productTypeID=1'\n",
        encoding="utf-8",
    )
    stored: dict = {}
    monkeypatch.setattr(
        service, "_database_catalog",
        lambda: ({"1842"}, set(stored), set()),  # XY Evolutions already in public.sets
    )
    monkeypatch.setattr(
        service.jobs, "upsert_discovery",
        lambda row: stored.__setitem__(row["source_set_id"], row) or row,
    )
    _wire_provider(monkeypatch, HISTORICAL_CATALOG)

    result = service.baseline_current_catalog(commit=True, pokemon_root=empty_root)

    assert "604" not in stored, "locally configured set must not be baselined"
    assert "1842" not in stored, "public.sets identity must not be baselined"
    assert result["known_skipped"] == 2
    assert result["baselined"] == len(HISTORICAL_CATALOG) - 2
    assert result["dispositions"]["known_local"] == 1
    assert result["dispositions"]["known_database"] == 1


def test_baseline_skips_unresolvable_identities_without_manual_review(monkeypatch, empty_root):
    stored: dict = {}
    _wire_store(monkeypatch, stored)
    _wire_provider(monkeypatch, [{"value": "Mystery Product"}], resolved={})

    result = service.baseline_current_catalog(commit=True, pokemon_root=empty_root)

    assert result["unresolved"] == 1
    assert result["baselined"] == 0
    assert stored == {}, "baseline must not persist provisional manual_review rows"


def test_normal_discovery_does_not_rediscover_baselined_identities(monkeypatch, empty_root):
    stored: dict = {}
    _wire_store(monkeypatch, stored)
    _wire_provider(monkeypatch, HISTORICAL_CATALOG)
    service.baseline_current_catalog(commit=True, pokemon_root=empty_root)

    monkeypatch.setattr(service, "queue_alert", lambda *a, **k: pytest.fail("no alert expected"))
    result = service.discover_new_sets(commit=True, pokemon_root=empty_root)

    assert result["detected"] == 0
    assert result["manual_review"] == 0
    assert result["unchanged"] == len(HISTORICAL_CATALOG)
    assert result["baseline_ignored_known"] == len(HISTORICAL_CATALOG)
    assert len(stored) == len(HISTORICAL_CATALOG)


def test_genuinely_new_provider_id_after_baseline_is_detected(monkeypatch, empty_root):
    stored: dict = {}
    _wire_store(monkeypatch, stored)
    _wire_provider(monkeypatch, HISTORICAL_CATALOG)
    service.baseline_current_catalog(commit=True, pokemon_root=empty_root)

    resolved = {**RESOLVED_IDS, "Mega Evolution": 24688}
    _wire_provider(monkeypatch, HISTORICAL_CATALOG + [{"value": "Mega Evolution"}], resolved=resolved)
    alerts: list = []
    monkeypatch.setattr(service, "queue_alert", lambda *a, **k: alerts.append(a[0]))

    result = service.discover_new_sets(commit=True, pokemon_root=empty_root)

    assert result["detected"] == 1
    assert result["unchanged"] == len(HISTORICAL_CATALOG)
    assert stored["24688"]["status"] == "detected"
    assert stored["24688"]["source_set_name"] == "Mega Evolution"
    assert alerts == ["new_pokemon_set_detected"]


def test_low_confidence_new_identity_after_baseline_still_routes_to_manual_review(
    monkeypatch, empty_root
):
    """Baseline must not weaken existing stable-ID confidence behavior."""
    stored: dict = {}
    _wire_store(monkeypatch, stored)
    monkeypatch.setattr(
        service, "fetch_global_set_aggregations", lambda *_a, **_k: [{"value": "Ambiguous Set"}]
    )
    monkeypatch.setattr(service, "validate_candidate_set_id", lambda *a, **k: (777, 0.55, "ambiguous"))
    monkeypatch.setattr(service, "queue_alert", lambda *a, **k: None)

    result = service.discover_new_sets(commit=True, pokemon_root=empty_root)

    assert result["manual_review"] == 1
    assert result["detected"] == 0
    assert stored["777"]["status"] == "manual_review"


def test_json_evidence_carries_explicit_disposition_per_checked_item(monkeypatch, empty_root):
    (empty_root / "base_set.py").write_text(
        "SET_NAME = 'Base Set'\nCARD_DETAILS_URL = 'https://x/priceguide/set/604/cards/'\n",
        encoding="utf-8",
    )
    stored = {
        "1520": {"source_set_id": "1520", "status": service.BASELINE_STATUS},
        "1418": {"source_set_id": "1418", "status": "detected"},
    }
    monkeypatch.setattr(
        service, "_database_catalog",
        lambda: (
            {"1842"},
            set(stored),
            {key for key, row in stored.items() if row["status"] == service.BASELINE_STATUS},
        ),
    )
    resolved = {**RESOLVED_IDS, "Mystery Product": None}
    _wire_provider(
        monkeypatch, HISTORICAL_CATALOG + [{"value": "Mystery Product"}], resolved=resolved
    )

    result = service.discover_new_sets(commit=False, pokemon_root=empty_root)

    assert all("disposition" in item for item in result["evidence"])
    by_name = {item["source_set_name"]: item["disposition"] for item in result["evidence"]}
    assert by_name["Base Set"] == "known_local"
    assert by_name["XY Evolutions"] == "known_database"
    assert by_name["EX Ruby & Sapphire"] == "baseline_ignored"
    assert by_name["Nintendo Black Star Promos"] == "known_job"
    assert by_name["Team Rocket Trainer Kit"] == "detected"
    assert by_name["Mystery Product"] == "manual_review"
    # Dispositions must reconcile with the headline counters that operators read.
    assert result["dispositions"]["detected"] == result["detected"]
    assert sum(result["dispositions"].values()) == result["candidates_checked"]
