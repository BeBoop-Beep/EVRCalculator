from pathlib import Path

from backend.services import pokemon_new_set_discovery_service as service


def test_parse_tcgplayer_set_id_uses_url_identity():
    assert service.parse_tcgplayer_set_id(
        "https://infinite-api.tcgplayer.com/priceguide/set/24688/cards/?productTypeID=1"
    ) == "24688"
    assert service.parse_tcgplayer_set_id("https://example.test/no-id") is None


def test_discovery_is_idempotent_for_known_provider_id(monkeypatch, tmp_path: Path):
    root = tmp_path / "pokemon"
    root.mkdir()
    (root / "known.py").write_text(
        "SET_NAME = 'Known Set'\nCARD_DETAILS_URL = "
        "'https://infinite-api.tcgplayer.com/priceguide/set/42/cards/?productTypeID=1'\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(service, "_database_catalog", lambda: (set(), set()))
    monkeypatch.setattr(
        service, "fetch_global_set_aggregations",
        lambda requester, cache: [{"value": "Brand New Set", "count": 100}],
    )
    monkeypatch.setattr(
        service, "validate_candidate_set_id",
        lambda *args, **kwargs: (42, 0.99, "stable"),
    )
    result = service.discover_new_sets(commit=False, pokemon_root=root)
    assert result["detected"] == 0
    assert result["unchanged"] == 1


def test_dry_run_detects_without_writing(monkeypatch, tmp_path: Path):
    root = tmp_path / "pokemon"
    root.mkdir()
    monkeypatch.setattr(service, "_database_catalog", lambda: (set(), set()))
    monkeypatch.setattr(
        service, "fetch_global_set_aggregations",
        lambda requester, cache: [{"value": "Brand New Set", "count": 100}],
    )
    monkeypatch.setattr(
        service, "validate_candidate_set_id",
        lambda *args, **kwargs: (999, 0.95, "stable"),
    )
    monkeypatch.setattr(service.jobs, "upsert_discovery", lambda row: (_ for _ in ()).throw(AssertionError()))
    result = service.discover_new_sets(commit=False, pokemon_root=root)
    assert result["detected"] == 1
    assert result["dry_run"] is True


def test_commit_creates_one_stable_id_job_and_repeat_reuses_it(monkeypatch, tmp_path):
    root = tmp_path / "pokemon"
    root.mkdir()
    stored = {}
    monkeypatch.setattr(
        service, "_database_catalog",
        lambda: (set(), set(stored)),
    )
    monkeypatch.setattr(
        service, "fetch_global_set_aggregations",
        lambda requester, cache: [{"value": "Brand New Set", "count": 100}],
    )
    monkeypatch.setattr(
        service, "validate_candidate_set_id",
        lambda *args, **kwargs: (999, 0.95, "stable"),
    )
    monkeypatch.setattr(
        service.jobs, "upsert_discovery",
        lambda row: stored.setdefault(row["source_set_id"], row),
    )
    monkeypatch.setattr(service, "queue_alert", lambda *args, **kwargs: None)
    first = service.discover_new_sets(commit=True, pokemon_root=root)
    second = service.discover_new_sets(commit=True, pokemon_root=root)
    assert first["detected"] == 1
    assert second["detected"] == 0
    assert len(stored) == 1
    assert stored["999"]["source_set_id"] == "999"


def test_low_confidence_stable_id_becomes_manual_review(monkeypatch, tmp_path):
    root = tmp_path / "pokemon"
    root.mkdir()
    rows = []
    monkeypatch.setattr(service, "_database_catalog", lambda: (set(), set()))
    monkeypatch.setattr(
        service, "fetch_global_set_aggregations",
        lambda requester, cache: [{"value": "Ambiguous Set", "count": 10}],
    )
    monkeypatch.setattr(
        service, "validate_candidate_set_id",
        lambda *args, **kwargs: (123, 0.55, "ambiguous"),
    )
    monkeypatch.setattr(service.jobs, "upsert_discovery", lambda row: rows.append(row) or row)
    monkeypatch.setattr(service, "queue_alert", lambda *args, **kwargs: None)
    result = service.discover_new_sets(commit=True, pokemon_root=root)
    assert result["manual_review"] == 1
    assert rows[0]["status"] == "manual_review"
