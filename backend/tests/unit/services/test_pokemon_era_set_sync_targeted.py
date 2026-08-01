from backend.db.services import pokemon_era_set_sync_service as service


def test_targeted_sync_filters_to_set_and_owning_era(monkeypatch, tmp_path):
    monkeypatch.setattr(service, "discover_pokemon_era_and_set_metadata", lambda: {
        "eras": [
            {"canonical_key": "eraA", "name": "Era A", "release_date": None, "sort_order": 1, "is_active": True},
            {"canonical_key": "eraB", "name": "Era B", "release_date": None, "sort_order": 2, "is_active": True},
        ],
        "sets": [
            {"canonical_key": "target", "era_canonical_key": "eraA", "name": "Target",
             "release_date": "2026-01-01", "set_type": None, "abbreviation": "T",
             "set_code": None, "pokemon_api_set_id": "api-target", "symbol_image_url": "s",
             "logo_image_url": "l", "source_config_path": "target.py",
             "card_details_url": "cards", "sealed_details_url": "sealed",
             "has_card_details_url": True, "has_sealed_details_url": True,
             "ready_for_daily_scrape": True},
            {"canonical_key": "other", "era_canonical_key": "eraB", "name": "Other",
             "release_date": None, "set_type": None, "abbreviation": None, "set_code": None,
             "pokemon_api_set_id": "api-other", "symbol_image_url": None, "logo_image_url": None,
             "source_config_path": "other.py", "card_details_url": None, "sealed_details_url": None,
             "has_card_details_url": False, "has_sealed_details_url": False,
             "ready_for_daily_scrape": False},
        ],
    })
    monkeypatch.setattr(service, "_resolve_tcg_row", lambda: {"id": "tcg"})
    monkeypatch.setattr(service, "get_eras_by_tcg_id", lambda tcg_id: [])
    monkeypatch.setattr(service, "get_sets_by_tcg_id", lambda tcg_id: [])
    report = service.sync_pokemon_era_and_set_metadata(
        apply_changes=False, report_path=tmp_path / "report.json", target_set_key="target",
    )
    assert report["summary"]["sets_discovered"] == 1
    assert report["summary"]["eras_discovered"] == 1
    assert [row["canonical_key"] for row in report["sets"]] == ["target"]
