from backend.scripts import refresh_due_pokemon_catalog_sets as script


def _due_row(**overrides):
    row = {
        "job_id": "job-1",
        "source_set_id": "24831",
        "source_set_name": "ME06: Delta Reign",
    }
    row.update(overrides)
    return row


def _recheck_item(**overrides):
    item = {
        "job_id": "job-1",
        "source_set_id": "24831",
        "provider_error": None,
        "availability_changed": True,
        "card_quality": {
            "raw_card_listing_count": 30,
            "processable_card_listing_count": 30,
        },
        "sealed_listing_count": 12,
    }
    item.update(overrides)
    return item


def _catalog_set(**overrides):
    row = {
        "id": "set-1",
        "name": "ME06: Delta Reign",
        "canonical_key": "me06DeltaReign",
        "catalog_only": True,
        "ready_for_daily_scrape": False,
    }
    row.update(overrides)
    return row


def _patch_common(monkeypatch, *, item=None, counts=None, due=None, set_row=None):
    due_rows = [_due_row()] if due is None else due
    monkeypatch.setattr(
        script.onboarding_jobs,
        "list_rechecks_v2",
        lambda **kwargs: due_rows,
    )
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
        "_provider_set_state",
        lambda client: {"24831": set_row or _catalog_set()},
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
    timer_calls = []
    monkeypatch.setattr(
        script,
        "_set_provider_next_check_at",
        lambda client, job_id, value: timer_calls.append((job_id, value)),
    )
    return timer_calls


def test_dry_run_plans_refresh_without_running_commands(monkeypatch):
    _patch_common(monkeypatch)
    monkeypatch.setattr(
        script,
        "_run",
        lambda command: (_ for _ in ()).throw(
            AssertionError("dry-run must not execute commands")
        ),
    )

    report = script.run(commit=False, limit=5, max_provider_requests=10)

    assert report["status"] == "ok"
    assert len(report["refreshes"]) == 1
    refresh = report["refreshes"][0]
    assert refresh["status"] == "would_refresh"
    assert refresh["canonical_key"] == "me06DeltaReign"
    assert refresh["scheduled_price_refresh"] is True
    assert any(
        any(part.endswith("run_pokemon_set_scrape.py") for part in cmd)
        for cmd in refresh["planned_commands"]
    )
    assert any(
        any(part.endswith("sync_pokemon_images.py") for part in cmd)
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


def test_due_catalog_identity_refreshes_prices_even_when_counts_are_unchanged(monkeypatch):
    _patch_common(
        monkeypatch,
        item=_recheck_item(availability_changed=False),
        counts={
            "cards": 30,
            "pokemon_canonical_cards": 30,
            "sealed_products": 12,
        },
    )

    report = script.run(commit=False, limit=5, max_provider_requests=10)

    assert report["status"] == "ok"
    assert len(report["refreshes"]) == 1
    assert report["refreshes"][0]["scheduled_price_refresh"] is True
    assert report["refreshes"][0]["availability_changed"] is False
    assert report["refreshes"][0]["status"] == "would_refresh"


def test_code_cards_only_catalog_still_refreshes_sealed_without_card_projection(monkeypatch):
    _patch_common(
        monkeypatch,
        item=_recheck_item(
            availability_changed=False,
            card_quality={
                "raw_card_listing_count": 3,
                "processable_card_listing_count": 0,
                "excluded_code_card_count": 3,
                "card_catalog_status": "code_cards_only",
            },
            sealed_listing_count=9,
        ),
        counts={
            "cards": 0,
            "pokemon_canonical_cards": 0,
            "sealed_products": 9,
        },
        set_row=_catalog_set(canonical_key="firstPartnerCollection2026"),
    )

    report = script.run(commit=False, limit=5, max_provider_requests=10)

    refresh = report["refreshes"][0]
    commands = [" ".join(command) for command in refresh["planned_commands"]]
    assert refresh["status"] == "would_refresh"
    assert any("run_pokemon_set_scrape.py" in line for line in commands)
    assert any("build_pokemon_set_sealed_market_snapshots.py" in line for line in commands)
    assert any("build_pokemon_set_page_snapshots.py" in line for line in commands)
    assert not any("sync_pokemon_images.py" in line for line in commands)
    assert not any("build_pokemon_set_desirability_inputs.py" in line for line in commands)
    assert not any("build_pokemon_set_cards_snapshots.py" in line for line in commands)


def test_genuinely_empty_provider_catalog_does_not_run_scraper(monkeypatch):
    _patch_common(
        monkeypatch,
        item=_recheck_item(
            availability_changed=False,
            card_quality={
                "raw_card_listing_count": 0,
                "processable_card_listing_count": 0,
                "card_catalog_status": "empty",
            },
            sealed_listing_count=0,
        ),
        counts={
            "cards": 0,
            "pokemon_canonical_cards": 0,
            "sealed_products": 0,
        },
    )

    report = script.run(commit=False, limit=5, max_provider_requests=10)

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
        lambda command: (_ for _ in ()).throw(
            AssertionError("provider failure must not refresh")
        ),
    )

    report = script.run(commit=True, limit=5, max_provider_requests=10)

    assert report["status"] == "ok"
    assert report["refreshes"] == []


def test_scrape_failure_stops_downstream_and_reschedules_short_retry(monkeypatch):
    timer_calls = _patch_common(monkeypatch)
    calls = []

    def fake_run(command):
        calls.append(command)
        return {
            "command": command,
            "exit_code": 1,
            "stdout_tail": "",
            "stderr_tail": "failed",
        }

    monkeypatch.setattr(script, "_run", fake_run)
    monkeypatch.setattr(script, "_retry_at", lambda: "2026-09-21T18:00:00+00:00")

    report = script.run(commit=True, limit=5, max_provider_requests=10)

    assert report["status"] == "failed"
    assert report["critical_failures"] == 1
    assert report["refreshes"][0]["status"] == "scrape_failed"
    assert report["refreshes"][0]["retry_scheduled_at"] == "2026-09-21T18:00:00+00:00"
    assert timer_calls == [("job-1", "2026-09-21T18:00:00+00:00")]
    assert len(calls) == 1
    assert any(part.endswith("run_pokemon_set_scrape.py") for part in calls[0])


def test_successful_card_refresh_runs_canonical_and_public_snapshots(monkeypatch):
    timer_calls = _patch_common(monkeypatch)
    calls = []

    def fake_run(command):
        calls.append(command)
        return {
            "command": command,
            "exit_code": 0,
            "stdout_tail": "",
            "stderr_tail": "",
        }

    monkeypatch.setattr(script, "_run", fake_run)

    report = script.run(commit=True, limit=5, max_provider_requests=10)

    assert report["status"] == "ok"
    assert report["refreshes"][0]["status"] == "refreshed"
    assert timer_calls == []
    joined = [" ".join(command) for command in calls]
    assert any("run_pokemon_set_scrape.py" in line for line in joined)
    assert any("sync_pokemon_images.py" in line for line in joined)
    assert any("build_pokemon_set_desirability_inputs.py" in line for line in joined)
    image_index = next(i for i, line in enumerate(joined) if "sync_pokemon_images.py" in line)
    canonical_index = next(i for i, line in enumerate(joined) if "build_pokemon_set_desirability_inputs.py" in line)
    assert image_index < canonical_index
    assert any("build_pokemon_set_cards_snapshots.py" in line for line in joined)
    assert any("build_pokemon_set_sealed_market_snapshots.py" in line for line in joined)
    assert any("build_pokemon_set_page_snapshots.py" in line for line in joined)


def test_graduated_identity_is_pruned_before_provider_recheck_dry_run(monkeypatch):
    due = [_due_row(source_set_id="24722")]
    captured = {}
    monkeypatch.setattr(script.onboarding_jobs, "list_rechecks_v2", lambda **kwargs: due)
    monkeypatch.setattr(
        script,
        "_provider_set_state",
        lambda client: {
            "24722": _catalog_set(
                canonical_key="me30thCelebration",
                catalog_only=False,
                ready_for_daily_scrape=True,
            )
        },
    )

    def fake_recheck(**kwargs):
        captured["due_rows"] = kwargs["due_rows"]
        return {"status": "ok", "identities": []}

    monkeypatch.setattr(script, "run_recheck", fake_recheck)
    monkeypatch.setattr(
        script,
        "_set_provider_next_check_at",
        lambda *args: (_ for _ in ()).throw(
            AssertionError("dry-run must not clear DB timers")
        ),
    )

    report = script.run(commit=False, limit=5, max_provider_requests=10)

    assert captured["due_rows"] == []
    assert report["refreshes"] == []
    assert report["graduated_rechecks"] == [
        {
            "job_id": "job-1",
            "source_set_id": "24722",
            "canonical_key": "me30thCelebration",
            "ready_for_daily_scrape": True,
            "status": "would_clear_recheck",
        }
    ]


def test_graduated_identity_clears_recheck_timer_in_commit_mode(monkeypatch):
    due = [_due_row(source_set_id="24837")]
    timer_calls = []
    captured = {}
    monkeypatch.setattr(script.onboarding_jobs, "list_rechecks_v2", lambda **kwargs: due)
    monkeypatch.setattr(
        script,
        "_provider_set_state",
        lambda client: {
            "24837": _catalog_set(
                canonical_key="me30thCelebrationClassicCollection",
                catalog_only=False,
                ready_for_daily_scrape=True,
            )
        },
    )
    monkeypatch.setattr(
        script,
        "_set_provider_next_check_at",
        lambda client, job_id, value: timer_calls.append((job_id, value)),
    )

    def fake_recheck(**kwargs):
        captured["due_rows"] = kwargs["due_rows"]
        return {"status": "ok", "identities": []}

    monkeypatch.setattr(script, "run_recheck", fake_recheck)

    report = script.run(commit=True, limit=5, max_provider_requests=10)

    assert captured["due_rows"] == []
    assert timer_calls == [("job-1", None)]
    assert report["graduated_rechecks"][0]["status"] == "recheck_cleared"


def test_image_sync_failure_is_critical_and_reschedules_short_retry(monkeypatch):
    _patch_common(monkeypatch)
    calls = []

    def fake_run(command):
        calls.append(command)
        is_image = any(str(part).endswith("sync_pokemon_images.py") for part in command)
        # The contract under test is order-sensitive: scrape succeeds first and
        # image hydration is the next critical operation.
        if len(calls) == 2:
            assert is_image, command
        return {
            "command": command,
            "exit_code": 1 if len(calls) == 2 else 0,
            "stdout_tail": "",
            "stderr_tail": "image sync failed" if len(calls) == 2 else "",
        }

    monkeypatch.setattr(script, "_run", fake_run)
    monkeypatch.setattr(script, "_retry_at", lambda: "2026-09-22T20:00:00+00:00")

    report = script.run(commit=True, limit=5, max_provider_requests=10)

    assert report["status"] == "failed"
    assert report["critical_failures"] == 1
    refresh = report["refreshes"][0]
    assert refresh["status"] == "pokemon_api_image_sync_failed"
    assert refresh["retry_scheduled_at"] == "2026-09-22T20:00:00+00:00"
    joined = [" ".join(command) for command in calls]
    assert any("sync_pokemon_images.py" in line for line in joined)
    assert not any("build_pokemon_set_desirability_inputs.py" in line for line in joined)
