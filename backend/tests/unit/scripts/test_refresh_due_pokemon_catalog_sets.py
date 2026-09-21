from backend.scripts import refresh_due_pokemon_catalog_sets as script


def _recheck_item(**overrides):
    item = {
        "source_set_id": "24831",
        "provider_error": None,
        "availability_changed": True,
        "card_quality": {"processable_card_listing_count": 30},
        "sealed_listing_count": 12,
    }
    item.update(overrides)
    return item


def _patch_common(monkeypatch, item=None, counts=None):
    monkeypatch.setattr(
        script,
        "run_recheck",
        lambda **kwargs: {
            "status": "ok",
            "identities": [item or _recheck_item()],
        },
    )
    monkeypatch.setattr(
        script,
        "_catalog_state",
        lambda client: {
            "24831": {
                "id": "set-1",
                "canonical_key": "me06DeltaReign",
                "catalog_only": True,
            }
        },
    )
    values = counts or {
        "cards": 0,
        "pokemon_canonical_cards": 0,
        "sealed_products": 12,
    }
    monkeypatch.setattr(
        script,
        "_row_count",
        lambda client, table, set_id: values[table],
    )


def test_dry_run_plans_refresh_without_running_commands(monkeypatch):
    _patch_common(monkeypatch)
    monkeypatch.setattr(
        script,
        "_run",
        lambda command: (_ for _ in ()).throw(AssertionError("dry-run must not execute commands")),
    )

    report = script.run(commit=False, limit=5, max_provider_requests=10)

    assert report["status"] == "ok"
    assert len(report["refreshes"]) == 1
    refresh = report["refreshes"][0]
    assert refresh["status"] == "would_refresh"
    assert refresh["canonical_key"] == "me06DeltaReign"
    assert any(
        any(part.endswith("run_pokemon_set_scrape.py") for part in cmd)
        for cmd in refresh["planned_commands"]
    )
    assert any(
        any(part.endswith("build_pokemon_set_desirability_inputs.py") for part in cmd)
        for cmd in refresh["planned_commands"]
    )
    assert any(
        any(part.endswith("build_pokemon_set_cards_snapshots.py") for part in cmd)
        for cmd in refresh["planned_commands"]
    )


def test_no_provider_change_and_no_db_lag_is_noop(monkeypatch):
    _patch_common(
        monkeypatch,
        item=_recheck_item(availability_changed=False),
        counts={
            "cards": 30,
            "pokemon_canonical_cards": 30,
            "sealed_products": 12,
        },
    )

    report = script.run(commit=True, limit=5, max_provider_requests=10)

    assert report["status"] == "ok"
    assert report["refreshes"] == []


def test_provider_failure_never_refreshes(monkeypatch):
    _patch_common(
        monkeypatch,
        item=_recheck_item(
            provider_error="provider_unreachable",
            availability_changed=False,
        ),
    )
    monkeypatch.setattr(
        script,
        "_run",
        lambda command: (_ for _ in ()).throw(AssertionError("provider failure must not refresh")),
    )

    report = script.run(commit=True, limit=5, max_provider_requests=10)

    assert report["status"] == "ok"
    assert report["refreshes"] == []


def test_scrape_failure_stops_downstream_and_remains_retryable(monkeypatch):
    _patch_common(monkeypatch)
    calls = []

    def fake_run(command):
        calls.append(command)
        return {"command": command, "exit_code": 1, "stdout_tail": "", "stderr_tail": "failed"}

    monkeypatch.setattr(script, "_run", fake_run)

    report = script.run(commit=True, limit=5, max_provider_requests=10)

    assert report["status"] == "failed"
    assert report["critical_failures"] == 1
    assert report["refreshes"][0]["status"] == "scrape_failed"
    assert len(calls) == 1
    assert any(part.endswith("run_pokemon_set_scrape.py") for part in calls[0])


def test_successful_card_refresh_runs_canonical_and_public_snapshots(monkeypatch):
    _patch_common(monkeypatch)
    calls = []

    def fake_run(command):
        calls.append(command)
        return {"command": command, "exit_code": 0, "stdout_tail": "", "stderr_tail": ""}

    monkeypatch.setattr(script, "_run", fake_run)

    report = script.run(commit=True, limit=5, max_provider_requests=10)

    assert report["status"] == "ok"
    assert report["refreshes"][0]["status"] == "refreshed"
    joined = [" ".join(command) for command in calls]
    assert any("run_pokemon_set_scrape.py" in line for line in joined)
    assert any("build_pokemon_set_desirability_inputs.py" in line for line in joined)
    assert any("build_pokemon_set_cards_snapshots.py" in line for line in joined)
    assert any("build_pokemon_set_sealed_market_snapshots.py" in line for line in joined)
    assert any("build_pokemon_set_page_snapshots.py" in line for line in joined)
