from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from backend.scripts import refresh_stale_public_snapshots as refresh
from backend.scripts.pokemon_snapshot_builders import SIMULATION_DEPENDENT_SECTIONS


def _market_enforcement(*, allowed=True, proceed=True, status="READY"):
    return SimpleNamespace(
        proceed=proceed,
        decision=SimpleNamespace(
            allowed=allowed, status=status, market_date="2026-08-23",
            reason=f"status={status}",
            evaluation={"qualifyingSetCount": 22, "cohortSetCount": 22},
        ),
    )


def test_market_quality_phase_dry_run_carries_computed_date_without_write(monkeypatch):
    captured = {}
    monkeypatch.setattr(refresh, "enforce_market_publication_gate",
                        lambda *_a, **_k: _market_enforcement())
    monkeypatch.setattr(refresh, "market_index_accepted_dates",
                        lambda *_a, **_k: {"2026-08-22"})
    from backend.db.services import pokemon_market_index_service as index_service
    def build_index(_client, **kwargs):
        captured["accepted"] = kwargs["accepted_dates"]
        return [
            {"market_date": "2026-08-23", "index_key": "pokemon_raw"},
            {"market_date": "2026-08-23", "index_key": "pokemon_top10"},
        ]
    monkeypatch.setattr(index_service, "build_market_index_history", build_index)
    monkeypatch.setattr(index_service, "persist_index_rows",
                        lambda *_a, **_k: pytest.fail("dry-run wrote index"))
    summary = refresh.RefreshSummary()

    ready, rows = refresh._run_market_quality_index_phase(
        object(), market_date="2026-08-23", commit=False, summary=summary)

    assert ready is True
    assert captured["accepted"] == {"2026-08-22", "2026-08-23"}
    assert rows is not None


def test_market_quality_phase_commit_uses_persisted_accepted_authority(monkeypatch):
    order = []
    monkeypatch.setattr(refresh, "enforce_market_publication_gate",
                        lambda *_a, **_k: order.append("quality") or _market_enforcement())
    monkeypatch.setattr(refresh, "market_index_accepted_dates",
                        lambda *_a, **_k: order.append("read-quality") or {"2026-08-23"})
    from backend.db.services import pokemon_market_index_service as index_service
    monkeypatch.setattr(
        index_service, "build_market_index_history",
        lambda _client, **kwargs: order.append(("build", kwargs["accepted_dates"])) or [
            {"market_date": "2026-08-23", "index_key": "pokemon_raw"},
            {"market_date": "2026-08-23", "index_key": "pokemon_top10"},
        ])
    monkeypatch.setattr(index_service, "persist_index_rows",
                        lambda *_a, **_k: order.append("persist-index"))
    summary = refresh.RefreshSummary()

    ready, rows = refresh._run_market_quality_index_phase(
        object(), market_date="2026-08-23", commit=True, summary=summary)

    assert ready is True and rows is None
    assert order == ["quality", "read-quality", ("build", {"2026-08-23"}), "persist-index"]


@pytest.mark.parametrize("status", ["INCOMPLETE", "DEGRADED"])
def test_market_quality_phase_blocks_unaccepted_target(monkeypatch, status):
    monkeypatch.setattr(
        refresh, "enforce_market_publication_gate",
        lambda *_a, **_k: _market_enforcement(allowed=False, proceed=False, status=status))
    summary = refresh.RefreshSummary()

    ready, rows = refresh._run_market_quality_index_phase(
        object(), market_date="2026-08-23", commit=True, summary=summary)

    assert ready is False and rows is None
    assert summary.global_failed and status in summary.global_failed[0]


def test_rankings_rebuild_uses_canonical_publisher(monkeypatch):
    calls = []
    monkeypatch.setattr(
        refresh, "publish_explore_rip_rankings_snapshot",
        lambda client, **kwargs: calls.append((client, kwargs)),
    )
    summary = refresh.RefreshSummary()
    client = object()
    refresh._maybe_rebuild_rankings(
        client, refresh.FreshnessResult("explore_rankings", True, "invalid"),
        commit=True, summary=summary,
    )
    assert calls == [(client, {"commit": True})]
    assert summary.global_rebuilt == ["explore_rankings"]


def test_rankings_publication_failure_is_recorded_without_fallback(monkeypatch):
    monkeypatch.setattr(
        refresh, "publish_explore_rip_rankings_snapshot",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("incomplete cohort")),
    )
    summary = refresh.RefreshSummary()
    refresh._maybe_rebuild_rankings(
        object(), refresh.FreshnessResult("explore_rankings", True, "invalid"),
        commit=True, summary=summary,
    )
    assert summary.global_rebuilt == []
    assert summary.global_failed == ["explore_rankings: incomplete cohort"]


def test_rankings_without_canonical_metadata_is_stale(monkeypatch):
    monkeypatch.setattr(refresh, "_latest_for_explore_rankings", lambda _client: (None, []))
    monkeypatch.setattr(
        refresh, "_read_snapshot_row",
        lambda *_args, **_kwargs: {
            "updated_at": "2026-08-01T08:00:00Z",
            "ranking_payload_json": {"meta": {"snapshot": {"builtAt": "2026-08-01T08:00:00Z"}}},
        },
    )
    result = refresh._global_snapshot_staleness(object(), family="explore_rankings")
    assert result.stale is True
    assert result.reason == "canonical publication metadata missing"


def _canonical_rankings_payload():
    return {
        "targets": [{
            "overallRipV10": {"rank": 1},
            "overallRipRankComparisonStatus1d": "unavailable",
        }],
        "meta": {
            "snapshot": {
                "publicationId": "publication-1", "marketDate": "2026-08-01",
                "builtAt": "2026-08-01T08:00:00Z",
            },
            "publicAnalyticsCohort": {"overallRanked": {"rankedSetCount": 1}},
        },
    }


def _stub_structural_reads(monkeypatch):
    monkeypatch.setattr(refresh, "_latest_for_explore_rankings", lambda _client: (None, []))
    payload = _canonical_rankings_payload()

    def read(_client, table, *_args, **_kwargs):
        if table == "pokemon_explore_rankings_snapshot_latest":
            return {"updated_at": "2026-08-01T08:00:00Z", "ranking_payload_json": payload}
        return {"id": "publication-1", "publication_status": "complete"}

    monkeypatch.setattr(refresh, "_read_snapshot_row", read)
    return payload


def _stub_rankings_payload(monkeypatch, payload):
    monkeypatch.setattr(refresh, "_latest_for_explore_rankings", lambda _client: (None, []))
    monkeypatch.setattr(refresh, "_leaderboard_contract_staleness", lambda _client: ([], []))

    def read(_client, table, *_args, **_kwargs):
        if table == "pokemon_explore_rankings_snapshot_latest":
            return {"updated_at": "2026-08-01T08:00:00Z", "ranking_payload_json": payload}
        return {"id": "publication-1", "publication_status": "complete"}

    monkeypatch.setattr(refresh, "_read_snapshot_row", read)


def _rankings_payload_with_cohort(*, ranked_targets, ranked_set_count=22):
    payload = _canonical_rankings_payload()
    payload["targets"] = [
        {
            "targetId": f"ranked-{index}",
            "overallRipV10": {"rank": index + 1},
            "overallRipRankComparisonStatus1d": "unavailable",
        }
        for index in range(ranked_targets)
    ] + [
        {
            "targetId": f"discovery-{index}",
            "overallRipRankComparisonStatus1d": "unavailable",
        }
        for index in range(12)
    ]
    payload["meta"]["publicAnalyticsCohort"]["overallRanked"]["rankedSetCount"] = ranked_set_count
    return payload


def test_rankings_allows_34_total_targets_when_only_22_are_canonically_ranked(monkeypatch):
    payload = _rankings_payload_with_cohort(ranked_targets=22)
    original_targets = payload["targets"]
    _stub_rankings_payload(monkeypatch, payload)

    result = refresh._global_snapshot_staleness(object(), family="explore_rankings")

    assert result.stale is False
    assert len(payload["targets"]) == 34
    assert payload["targets"] is original_targets
    assert all("overallRipV10" not in target for target in payload["targets"][22:])


@pytest.mark.parametrize("ranked_targets", [21, 23])
def test_rankings_ranked_target_count_must_match_ranked_set_count(monkeypatch, ranked_targets):
    payload = _rankings_payload_with_cohort(ranked_targets=ranked_targets)
    _stub_rankings_payload(monkeypatch, payload)

    result = refresh._global_snapshot_staleness(object(), family="explore_rankings")

    assert result.stale is True
    assert result.reason == "complete public ranked cohort marker/count invalid"


@pytest.mark.parametrize("marker_state", ["zero", "absent"])
def test_rankings_requires_a_positive_ranked_set_count(monkeypatch, marker_state):
    payload = _rankings_payload_with_cohort(ranked_targets=22, ranked_set_count=0)
    if marker_state == "absent":
        payload["meta"]["publicAnalyticsCohort"]["overallRanked"].pop("rankedSetCount")
    _stub_rankings_payload(monkeypatch, payload)

    result = refresh._global_snapshot_staleness(object(), family="explore_rankings")

    assert result.stale is True
    assert result.reason == "complete public ranked cohort marker/count invalid"


def test_canonical_rankings_shape_is_fresh(monkeypatch):
    """Structurally complete AND on the canonical scoring contract."""
    _stub_structural_reads(monkeypatch)
    monkeypatch.setattr(
        refresh, "_leaderboard_contract_staleness", lambda _client: ([], [])
    )
    result = refresh._global_snapshot_staleness(object(), family="explore_rankings")
    assert result.stale is False


def test_a_structurally_perfect_snapshot_on_an_obsolete_contract_is_stale(monkeypatch):
    """THE gap this closes.

    Every structural marker is present, the publication row is complete, and no
    dependency timestamp is newer - the exact state a leaderboard published under
    Financial RIP V2 / Overall RIP v4 was in while 22 Financial RIP V3
    simulations sat underneath it. A scoring-version change moves NO timestamp,
    so the timestamp comparison could never have caught it.
    """
    _stub_structural_reads(monkeypatch)
    monkeypatch.setattr(
        refresh,
        "_leaderboard_contract_staleness",
        lambda _client: (
            [{
                "code": "financial_rip_version_not_canonical",
                "detail": "Published Financial RIP version is 'financial_rip_v2_60_25_15'.",
            }],
            [],
        ),
    )
    result = refresh._global_snapshot_staleness(object(), family="explore_rankings")
    assert result.stale is True
    assert "published scoring contract is not canonical" in result.reason
    assert "financial_rip_v2_60_25_15" in result.reason


def test_a_matching_market_date_alone_never_establishes_freshness(monkeypatch):
    """Market date says when the PRICES were promoted, not which formula scored them."""
    _stub_structural_reads(monkeypatch)
    reasons = [
        {"code": "overall_rip_version_not_canonical", "detail": "Overall RIP is v4."},
        {"code": "public_rip_contract_version_not_canonical", "detail": "Contract is v6."},
    ]
    monkeypatch.setattr(
        refresh, "_leaderboard_contract_staleness", lambda _client: (reasons, [])
    )
    result = refresh._global_snapshot_staleness(object(), family="explore_rankings")
    assert result.stale is True
    # Every reason is reported, not just the first: one rebuild resolves all of
    # them, and naming only one sends an operator to a partial fix.
    assert "Overall RIP is v4." in result.reason
    assert "Contract is v6." in result.reason


def _iso(dt):
    return dt.astimezone(timezone.utc).isoformat()


def _row(set_id: str, set_updated: str, rankings_embedded: str, *, include_ranks: bool = True):
    summary = {
        "target_id": set_id,
        "set_id": set_id,
        "name": "Set",
    }
    if include_ranks:
        summary["pack_rank"] = 3
        summary["profit_rank"] = 4
    return {
        "set_id": set_id,
        "updated_at": set_updated,
        "payload_json": {
            "target": {"target_type": "set", "target_id": set_id, "id": set_id, "name": "Set"},
            "summary": summary,
            "meta": {
                "snapshot": {"type": "pokemon_set_page", "builtAt": set_updated},
                "simulationAvailability": {"available": True, "unavailableSections": []},
                "snapshotCompleteness": {
                    "explore_rankings_snapshot_updated_at": rankings_embedded,
                },
                "sectionFreshness": {
                    "decisionSignalRanks": {
                        "status": "fresh",
                    }
                },
                "warnings": [],
                "sources": {"simulation_input_cards": "OK"},
            },
            "top_hits": [{"card_name": "Chase"}],
        },
    }


def test_verify_set_page_no_false_positive_when_set_page_newer_than_rankings_and_ranks_present(monkeypatch):
    t0 = datetime(2026, 6, 25, 10, 0, tzinfo=timezone.utc)
    rankings_updated = _iso(t0)
    set_updated = _iso(t0 + timedelta(minutes=12))

    monkeypatch.setattr(
        refresh,
        "_read_snapshot_row",
        lambda _client, table, _select_fields, _filters: (
            {"updated_at": rankings_updated} if table == "pokemon_explore_rankings_snapshot_latest" else _row("set-1", set_updated, rankings_updated)
        ),
    )
    monkeypatch.setattr(refresh, "_has_known_stale_warning", lambda _warnings: False)
    monkeypatch.setattr(refresh, "_source_rows_exist_for_set_page", lambda _client, _set_id: True)

    problems = refresh._verify_set_page(None, {"id": "set-1", "canonical_key": "whiteFlare"}, rankings_updated_at=rankings_updated)

    assert problems == []


def test_verify_set_page_stale_when_rankings_rebuilt_after_set_page(monkeypatch):
    t0 = datetime(2026, 6, 25, 10, 0, tzinfo=timezone.utc)
    set_updated = _iso(t0)
    rankings_updated = _iso(t0 + timedelta(minutes=15))

    monkeypatch.setattr(
        refresh,
        "_read_snapshot_row",
        lambda _client, table, _select_fields, _filters: (
            {"updated_at": rankings_updated} if table == "pokemon_explore_rankings_snapshot_latest" else _row("set-1", set_updated, set_updated)
        ),
    )
    monkeypatch.setattr(refresh, "_has_known_stale_warning", lambda _warnings: False)
    monkeypatch.setattr(refresh, "_source_rows_exist_for_set_page", lambda _client, _set_id: True)

    problems = refresh._verify_set_page(None, {"id": "set-1", "canonical_key": "whiteFlare"}, rankings_updated_at=rankings_updated)

    assert any("rankings snapshot rebuilt after set page snapshot" in problem for problem in problems)


def test_verify_set_page_stale_when_rank_fields_missing(monkeypatch):
    t0 = datetime(2026, 6, 25, 10, 0, tzinfo=timezone.utc)
    rankings_updated = _iso(t0)

    monkeypatch.setattr(
        refresh,
        "_read_snapshot_row",
        lambda _client, table, _select_fields, _filters: (
            {"updated_at": rankings_updated}
            if table == "pokemon_explore_rankings_snapshot_latest"
            else _row("set-1", rankings_updated, rankings_updated, include_ranks=False)
        ),
    )
    monkeypatch.setattr(refresh, "_has_known_stale_warning", lambda _warnings: False)
    monkeypatch.setattr(refresh, "_source_rows_exist_for_set_page", lambda _client, _set_id: True)

    problems = refresh._verify_set_page(None, {"id": "set-1", "canonical_key": "whiteFlare"}, rankings_updated_at=rankings_updated)

    assert any("rank fields missing" in problem for problem in problems)


def _market_row(*, updated_at="2026-06-21T00:00:00+00:00", latest_market_date="2026-06-20"):
    histories = {
        "standard": [{"date": "2026-06-20", "setValue": 100}],
        "hits": [{"date": "2026-06-20", "setValue": 50}],
        "top10": [{"date": "2026-06-20", "setValue": 25}],
    }
    return {
        "set_id": "set-1",
        "window_key": "365d",
        "updated_at": updated_at,
        "latest_market_date": latest_market_date,
        "set_value_histories_json": histories,
        "payload_json": {
            "latestMarketDate": latest_market_date,
            "setValueHistoriesByScope": histories,
            "meta": {
                "snapshot": {"type": "pokemon_set_market_dashboard"},
                "setValueHistoryLatestDateByScope": {
                    "standard": "2026-06-20",
                    "hits": "2026-06-20",
                    "top10": "2026-06-20",
                },
            },
        },
    }


def test_market_dashboard_stale_when_raw_set_value_snapshot_date_newer(monkeypatch):
    monkeypatch.setattr(refresh, "_latest_for_market_dashboard", lambda _client, _set_id: (None, []))
    monkeypatch.setattr(refresh, "_latest_simulation_history_date", lambda _client, _set_id: (None, []))

    def latest_by_scope(_client, _set_id, *, column):
        if column == "updated_at":
            return {"standard": "2026-06-20T00:00:00+00:00", "hits": "2026-06-20T00:00:00+00:00", "top10": "2026-06-20T00:00:00+00:00"}, []
        return {"standard": "2026-06-24", "hits": "2026-06-24", "top10": "2026-06-23"}, []

    monkeypatch.setattr(refresh, "_latest_set_value_history_by_scope", latest_by_scope)
    monkeypatch.setattr(refresh, "_read_snapshot_row", lambda *_args, **_kwargs: _market_row())

    result = refresh._market_snapshot_staleness(None, "set-1", "365d")

    assert result.stale is True
    assert result.family == "market_dashboard"
    assert "latest_market_date" in result.reason


def test_market_dashboard_missing_row_is_stale(monkeypatch):
    monkeypatch.setattr(refresh, "_latest_for_market_dashboard", lambda _client, _set_id: (None, []))
    monkeypatch.setattr(refresh, "_latest_simulation_history_date", lambda _client, _set_id: (None, []))
    monkeypatch.setattr(
        refresh,
        "_latest_set_value_history_by_scope",
        lambda _client, _set_id, *, column: ({"standard": "2026-06-25", "hits": None, "top10": None}, []),
    )
    monkeypatch.setattr(refresh, "_read_snapshot_row", lambda *_args, **_kwargs: None)

    result = refresh._market_snapshot_staleness(None, "set-1", "365d")

    assert result.stale is True
    assert result.reason == "snapshot row missing"


def test_market_dashboard_stale_when_one_scope_history_lags(monkeypatch):
    monkeypatch.setattr(refresh, "_latest_for_market_dashboard", lambda _client, _set_id: (None, []))
    monkeypatch.setattr(refresh, "_latest_simulation_history_date", lambda _client, _set_id: (None, []))

    def latest_by_scope(_client, _set_id, *, column):
        if column == "updated_at":
            return {"standard": "2026-06-20T00:00:00+00:00", "hits": "2026-06-20T00:00:00+00:00", "top10": "2026-06-20T00:00:00+00:00"}, []
        return {"standard": "2026-06-25", "hits": "2026-06-25", "top10": "2026-06-25"}, []

    row = _market_row(latest_market_date="2026-06-25")
    row["set_value_histories_json"]["standard"] = [{"date": "2026-06-25", "setValue": 100}]
    row["set_value_histories_json"]["hits"] = [{"date": "2026-06-20", "setValue": 50}]
    row["set_value_histories_json"]["top10"] = [{"date": "2026-06-25", "setValue": 25}]
    row["payload_json"]["meta"]["setValueHistoryLatestDateByScope"] = {
        "standard": "2026-06-25",
        "hits": "2026-06-20",
        "top10": "2026-06-25",
    }

    monkeypatch.setattr(refresh, "_latest_set_value_history_by_scope", latest_by_scope)
    monkeypatch.setattr(refresh, "_read_snapshot_row", lambda *_args, **_kwargs: row)

    result = refresh._market_snapshot_staleness(None, "set-1", "365d")

    assert result.stale is True
    assert result.reason == "hits set value history newer than dashboard history"


def test_market_dashboard_stale_when_raw_set_value_updated_after_dashboard(monkeypatch):
    monkeypatch.setattr(refresh, "_latest_for_market_dashboard", lambda _client, _set_id: (None, []))
    monkeypatch.setattr(refresh, "_latest_simulation_history_date", lambda _client, _set_id: (None, []))

    def latest_by_scope(_client, _set_id, *, column):
        if column == "updated_at":
            return {"standard": "2026-06-22T00:00:00+00:00", "hits": "2026-06-25T00:00:00+00:00", "top10": "2026-06-22T00:00:00+00:00"}, []
        return {"standard": "2026-06-20", "hits": "2026-06-20", "top10": "2026-06-20"}, []

    monkeypatch.setattr(refresh, "_latest_set_value_history_by_scope", latest_by_scope)
    monkeypatch.setattr(refresh, "_read_snapshot_row", lambda *_args, **_kwargs: _market_row(updated_at="2026-06-24T00:00:00+00:00"))

    result = refresh._market_snapshot_staleness(None, "set-1", "365d")

    assert result.stale is True
    assert result.reason == "set value daily history updated after market dashboard"


def test_build_plan_all_reports_multiple_stale_market_dashboards(monkeypatch):
    monkeypatch.setattr(refresh, "_cards_snapshot_staleness", lambda _client, set_id: refresh.FreshnessResult("cards", False, "fresh"))
    monkeypatch.setattr(refresh, "_set_page_snapshot_staleness", lambda _client, set_id: refresh.FreshnessResult("set_page", False, "fresh"))
    monkeypatch.setattr(
        refresh,
        "_market_snapshot_staleness",
        lambda _client, set_id, window: refresh.FreshnessResult(
            "market_dashboard",
            set_id in {"set-1", "set-2"},
            "stale" if set_id in {"set-1", "set-2"} else "fresh",
        ),
    )
    monkeypatch.setattr(refresh, "_global_snapshot_staleness", lambda _client, *, family: refresh.FreshnessResult(family, False, "fresh"))

    plans, rankings, validation, _source_checks = refresh._build_plan(
        None,
        set_rows=[{"id": "set-1"}, {"id": "set-2"}, {"id": "set-3"}],
        window="365d",
    )

    assert [plan.set_row["id"] for plan in plans if plan.market_dashboard.stale] == ["set-1", "set-2"]
    assert rankings.stale is False
    assert validation.stale is False


def test_market_dashboard_staleness_plans_set_page_rebuild_in_same_run(monkeypatch):
    # Stale-flatline regression: the set page embeds market/performance
    # context, so a market dashboard rebuilt in THIS run must trigger the set
    # page rebuild in the same run — deferring it to the next invocation left
    # set pages one refresh behind their market dashboards.
    rebuilt = []
    monkeypatch.setattr(refresh, "build_set_page_snapshot_row", lambda set_row, client=None: {"set_id": set_row["id"]})
    monkeypatch.setattr(refresh, "upsert_row", lambda _client, table, _row, *, on_conflict, commit: rebuilt.append(table))
    summary = refresh.RefreshSummary()
    plan = refresh.SetRefreshPlan(
        set_row={"id": "set-1", "canonical_key": "shroudedFable"},
        cards=refresh.FreshnessResult("cards", False, "fresh", "2026-06-24T00:00:00+00:00"),
        market_dashboard=refresh.FreshnessResult("market_dashboard", True, "set value daily history date newer than latest_market_date", "2026-06-24T00:00:00+00:00"),
        set_page=refresh.FreshnessResult("set_page", False, "fresh", "2026-06-24T00:00:00+00:00"),
    )

    refresh._maybe_rebuild_set_page(None, plan, rankings_updated_at=None, commit=True, summary=summary)

    assert rebuilt == ["pokemon_set_page_snapshot_latest"]
    assert summary.rebuilt_sets["set_page"] == ["shroudedFable"]


def test_desirability_validation_freshness_does_not_depend_on_market_dashboard(monkeypatch):
    tables = []

    def latest_timestamp(_client, *, table, timestamp_columns, filters=(), in_filters=()):
        tables.append(table)
        return None, [f"{table}: ok"]

    monkeypatch.setattr(refresh, "_latest_timestamp", latest_timestamp)

    refresh._latest_for_desirability_validation(None)

    assert "pokemon_set_market_dashboard_snapshot_latest" not in tables


# ---------------------------------------------------------------------------
# Stale set-page pipeline fix: staleness detection from newer simulation /
# market dashboard sources, post-run freshness audit, strict gating, and
# per-set failure isolation.
# ---------------------------------------------------------------------------


def _set_page_row(set_id: str, updated_at: str):
    return {
        "set_id": set_id,
        "updated_at": updated_at,
        "payload_json": {
            "summary": {"set_id": set_id, "pack_rank": 3},
            "meta": {
                "snapshotCompleteness": {"explore_rankings_snapshot_updated_at": updated_at},
                "warnings": [],
                "sources": {"simulation_input_cards": "OK"},
            },
            "top_hits": [{"card_name": "Chase"}],
        },
    }


def test_set_page_stale_when_simulation_run_newer(monkeypatch):
    t0 = datetime(2026, 6, 30, 10, 0, tzinfo=timezone.utc)
    snapshot_updated = _iso(t0)
    simulation_run = _iso(t0 + timedelta(days=10))

    monkeypatch.setattr(refresh, "_latest_for_set_page", lambda _client, _set_id: (simulation_run, []))
    monkeypatch.setattr(refresh, "_read_snapshot_row", lambda *_args, **_kwargs: _set_page_row("set-1", snapshot_updated))
    monkeypatch.setattr(refresh, "_latest_timestamp", lambda _client, **_kwargs: (None, []))
    monkeypatch.setattr(refresh, "_has_known_stale_warning", lambda _warnings: False)
    monkeypatch.setattr(refresh, "_source_rows_exist_for_set_page", lambda _client, _set_id: True)
    monkeypatch.setattr(refresh, "_set_page_has_rank_fields", lambda _payload: False)

    result = refresh._set_page_snapshot_staleness(None, "set-1")

    assert result.stale is True
    assert result.reason == "dependency newer than snapshot"


def test_set_page_stale_when_market_dashboard_snapshot_newer(monkeypatch):
    t0 = datetime(2026, 6, 30, 10, 0, tzinfo=timezone.utc)
    snapshot_updated = _iso(t0)
    market_updated = _iso(t0 + timedelta(days=9))

    def latest_timestamp(_client, *, table, timestamp_columns, filters=(), in_filters=()):
        if table == "pokemon_set_market_dashboard_snapshot_latest":
            return market_updated, [f"{table}: ok"]
        return None, [f"{table}: ok"]

    monkeypatch.setattr(refresh, "_latest_timestamp", latest_timestamp)
    monkeypatch.setattr(refresh, "_latest_run_id_for_set", lambda _client, _set_id: None)
    monkeypatch.setattr(refresh, "_read_snapshot_row", lambda *_args, **_kwargs: _set_page_row("set-1", snapshot_updated))
    monkeypatch.setattr(refresh, "_has_known_stale_warning", lambda _warnings: False)
    monkeypatch.setattr(refresh, "_source_rows_exist_for_set_page", lambda _client, _set_id: True)
    monkeypatch.setattr(refresh, "_set_page_has_rank_fields", lambda _payload: False)

    result = refresh._set_page_snapshot_staleness(None, "set-1")

    assert result.stale is True
    assert result.reason == "dependency newer than snapshot"


def _audit_latest_timestamp_factory(*, simulation=None, rip=None, market=None):
    def latest_timestamp(_client, *, table, timestamp_columns, filters=(), in_filters=()):
        if table == "simulation_latest_by_target":
            return simulation, []
        if table == "explore_rip_statistics_latest":
            return rip, []
        if table == "pokemon_set_market_dashboard_snapshot_latest":
            return market, []
        return None, []

    return latest_timestamp


def test_audit_reports_stale_set_when_simulation_newer(monkeypatch):
    t0 = datetime(2026, 6, 30, 10, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(refresh, "_read_snapshot_row", lambda *_args, **_kwargs: {"updated_at": _iso(t0)})
    monkeypatch.setattr(
        refresh,
        "_latest_timestamp",
        _audit_latest_timestamp_factory(simulation=_iso(t0 + timedelta(days=10))),
    )

    audit = refresh._audit_set_page_freshness(None, [{"id": "set-1", "canonical_key": "prismaticEvolutions"}])

    assert audit.total == 1
    assert audit.fresh == 0
    assert audit.stale == 1
    assert "prismaticEvolutions" in audit.stale_details[0]
    assert "simulation newer" in audit.stale_details[0]
    assert audit.max_staleness_set == "prismaticEvolutions"
    assert audit.max_staleness_seconds == timedelta(days=10).total_seconds()


def test_audit_reports_stale_set_when_market_dashboard_newer(monkeypatch):
    t0 = datetime(2026, 6, 30, 10, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(refresh, "_read_snapshot_row", lambda *_args, **_kwargs: {"updated_at": _iso(t0)})
    monkeypatch.setattr(
        refresh,
        "_latest_timestamp",
        _audit_latest_timestamp_factory(market=_iso(t0 + timedelta(days=9))),
    )

    audit = refresh._audit_set_page_freshness(None, [{"id": "set-1", "canonical_key": "ascendedHeroes"}])

    assert audit.stale == 1
    assert "market dashboard newer" in audit.stale_details[0]


def test_audit_marks_rebuilt_set_page_fresh(monkeypatch):
    t0 = datetime(2026, 7, 10, 10, 0, tzinfo=timezone.utc)
    # Snapshot rebuilt AFTER the latest simulation and market dashboard.
    monkeypatch.setattr(refresh, "_read_snapshot_row", lambda *_args, **_kwargs: {"updated_at": _iso(t0 + timedelta(minutes=30))})
    monkeypatch.setattr(
        refresh,
        "_latest_timestamp",
        _audit_latest_timestamp_factory(simulation=_iso(t0), rip=_iso(t0), market=_iso(t0 + timedelta(minutes=10))),
    )

    audit = refresh._audit_set_page_freshness(None, [{"id": "set-1", "canonical_key": "prismaticEvolutions"}])

    assert audit.total == 1
    assert audit.fresh == 1
    assert audit.stale == 0
    assert audit.stale_details == []


def test_audit_counts_missing_set_page_snapshot_as_stale(monkeypatch):
    monkeypatch.setattr(refresh, "_read_snapshot_row", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(refresh, "_latest_timestamp", _audit_latest_timestamp_factory())

    audit = refresh._audit_set_page_freshness(None, [{"id": "set-1", "canonical_key": "newSet"}])

    assert audit.stale == 1
    assert "set page snapshot missing" in audit.stale_details[0]


def test_strict_fails_when_audit_reports_stale_sets():
    summary = refresh.RefreshSummary()
    summary.set_page_audit = refresh.SetPageFreshnessAudit(
        total=2,
        fresh=1,
        stale_details=["prismaticEvolutions: simulation newer"],
    )

    assert refresh._strict_should_fail(summary, commit=True) is True


def test_strict_passes_when_audit_is_clean():
    summary = refresh.RefreshSummary()
    summary.set_page_audit = refresh.SetPageFreshnessAudit(total=2, fresh=2)

    assert refresh._strict_should_fail(summary, commit=True) is False


def test_strict_fails_in_dry_run_when_stale_families_detected():
    summary = refresh.RefreshSummary()
    summary.stale_snapshot_families.add("set_page")
    summary.set_page_audit = refresh.SetPageFreshnessAudit(total=1, fresh=1)

    assert refresh._strict_should_fail(summary, commit=False) is True


def test_one_failed_set_page_rebuild_does_not_prevent_later_sets(monkeypatch):
    def build_row(set_row, client=None):
        if set_row["id"] == "set-1":
            raise RuntimeError("boom")
        return {"set_id": set_row["id"]}

    upserted = []
    monkeypatch.setattr(refresh, "build_set_page_snapshot_row", build_row)
    monkeypatch.setattr(refresh, "upsert_row", lambda _client, table, row, *, on_conflict, commit: upserted.append(row["set_id"]))

    summary = refresh.RefreshSummary()
    plans = [
        refresh.SetRefreshPlan(
            set_row={"id": "set-1", "canonical_key": "failingSet"},
            cards=refresh.FreshnessResult("cards", False, "fresh"),
            market_dashboard=refresh.FreshnessResult("market_dashboard", False, "fresh"),
            set_page=refresh.FreshnessResult("set_page", True, "dependency newer than snapshot"),
        ),
        refresh.SetRefreshPlan(
            set_row={"id": "set-2", "canonical_key": "healthySet"},
            cards=refresh.FreshnessResult("cards", False, "fresh"),
            market_dashboard=refresh.FreshnessResult("market_dashboard", False, "fresh"),
            set_page=refresh.FreshnessResult("set_page", True, "dependency newer than snapshot"),
        ),
    ]

    for plan in plans:
        refresh._maybe_rebuild_set_page(None, plan, rankings_updated_at=None, commit=True, summary=summary)

    assert upserted == ["set-2"]
    assert summary.rebuilt_sets["set_page"] == ["healthySet"]
    assert len(summary.failed_sets["set_page"]) == 1
    assert summary.failed_sets["set_page"][0].startswith("failingSet:")


# ---------------------------------------------------------------------------
# I/O-safe resumable recovery: nonzero exit on failure, batch-gated promotion
# ---------------------------------------------------------------------------


def test_has_hard_failures_true_when_any_set_failed():
    summary = refresh.RefreshSummary()
    summary.failed_sets["set_page"].append("failingSet: boom")
    assert refresh._has_hard_failures(summary) is True


def test_has_hard_failures_true_when_global_failed():
    summary = refresh.RefreshSummary()
    summary.global_failed.append("explore_rankings: boom")
    assert refresh._has_hard_failures(summary) is True


def test_has_hard_failures_false_for_only_staleness_warnings():
    summary = refresh.RefreshSummary()
    summary.warnings_remaining = ["set-1: rankings snapshot rebuilt after set page snapshot"]
    summary.stale_snapshot_families.add("set_page")
    assert refresh._has_hard_failures(summary) is False


def _patch_main_pipeline(monkeypatch, *, gate_allowed=True, override=False, fail_set=False):
    """Stub the whole main() pipeline so exit-status/gating logic can be exercised."""
    monkeypatch.setattr(refresh, "get_client", lambda: object())
    monkeypatch.setattr(
        refresh,
        "evaluate_publication_gate",
        lambda _client, **_kwargs: _GateDecision(allowed=gate_allowed, override=override),
    )
    monkeypatch.setattr(refresh, "_resolve_sets", lambda _client, set_id=None: [{"id": "set-1", "canonical_key": "alpha"}])

    def _build_plan(_client, *, set_rows, window):
        plan = refresh.SetRefreshPlan(
            set_row=set_rows[0],
            cards=refresh.FreshnessResult("cards", True, "stale"),
            market_dashboard=refresh.FreshnessResult("market_dashboard", False, "fresh"),
            set_page=refresh.FreshnessResult("set_page", False, "fresh"),
        )
        return [plan], refresh.FreshnessResult("explore_rankings", False, "fresh"), refresh.FreshnessResult("desirability_validation", False, "fresh"), 0

    monkeypatch.setattr(refresh, "_build_plan", _build_plan)

    def _rebuild_coordinated(_client, plan, *, commit, days, window, summary):
        if fail_set:
            summary.failed_sets["cards"].append("alpha: boom")
        else:
            summary.rebuilt_sets["cards"].append("alpha")

    monkeypatch.setattr(refresh, "_maybe_rebuild_coordinated_market", _rebuild_coordinated)
    monkeypatch.setattr(refresh, "_maybe_rebuild_explore_set_values", lambda *_a, **_k: None)
    monkeypatch.setattr(refresh, "_maybe_rebuild_explore_card_movers", lambda *_a, **_k: None)
    monkeypatch.setattr(refresh, "_maybe_rebuild_rankings", lambda *_a, **_k: None)
    monkeypatch.setattr(refresh, "_maybe_rebuild_set_page", lambda *_a, **_k: None)
    monkeypatch.setattr(refresh, "_build_validation_snapshot", lambda *_a, **_k: None)
    monkeypatch.setattr(refresh, "_verify_after_build", lambda *_a, **_k: None)
    monkeypatch.setattr(refresh, "_audit_set_page_freshness", lambda *_a, **_k: refresh.SetPageFreshnessAudit(total=1, fresh=1))
    monkeypatch.setattr(refresh, "_read_snapshot_row", lambda *_a, **_k: None)


class _GateDecision:
    def __init__(self, *, allowed=True, override=False):
        self.allowed = allowed
        self.override = override
        self.reason = "test"
        self.reason_code = "allowed_complete" if allowed else "blocked_incomplete"
        self.mode = "required"
        self.market_date = "2026-07-25"
        self.batch_status = "complete" if allowed else "incomplete"
        self.missing_set_count = None if allowed else 3
        self.expected_set_count = 166
        self.promoted_at = "2026-07-25T09:00:00Z" if allowed else None


def test_main_exits_nonzero_when_a_set_fails_even_without_strict(monkeypatch):
    _patch_main_pipeline(monkeypatch, fail_set=True)
    monkeypatch.setattr("sys.argv", ["refresh", "--commit"])
    try:
        refresh.main()
    except SystemExit as exc:
        assert exc.code == 1
    else:
        raise AssertionError("expected nonzero exit on a failed set")


def test_main_exits_zero_on_clean_commit(monkeypatch):
    _patch_main_pipeline(monkeypatch, fail_set=False)
    monkeypatch.setattr("sys.argv", ["refresh", "--commit"])
    # No SystemExit(1) means a clean success.
    refresh.main()


def test_main_gate_closed_defers_with_exit_3_and_skips_rebuild(monkeypatch, capsys):
    # A closed gate DEFERS publication: exit code 3 (not 0, not 1), zero writes,
    # previous good snapshots preserved.
    rebuilt = []
    _patch_main_pipeline(monkeypatch, gate_allowed=False)
    monkeypatch.setattr(
        refresh,
        "_maybe_rebuild_coordinated_market",
        lambda *_a, **_k: rebuilt.append("should-not-run"),
    )
    monkeypatch.setattr("sys.argv", ["refresh", "--commit"])

    with pytest.raises(SystemExit) as excinfo:
        refresh.main()

    assert excinfo.value.code == refresh.GATE_DEFERRED_EXIT_CODE == 3
    out = capsys.readouterr().out
    assert "publication gate CLOSED" in out
    assert "PUBLICATION_DEFERRED" in out
    assert rebuilt == []


def test_main_dry_run_reports_gate_decision_and_performs_no_writes(monkeypatch, capsys):
    # Dry-run reports what the gate decision WOULD be and never enters the
    # commit-only deferral branch (exit 0, no rebuild attempted with commit=True).
    _patch_main_pipeline(monkeypatch, gate_allowed=False)
    committed = []
    monkeypatch.setattr(
        refresh,
        "_maybe_rebuild_coordinated_market",
        lambda _client, plan, *, commit, **_k: committed.append(commit),
    )
    monkeypatch.setattr("sys.argv", ["refresh", "--dry-run"])

    refresh.main()

    out = capsys.readouterr().out
    assert "publication gate decision (dry-run)" in out
    # The pipeline ran read-only: every rebuild call saw commit=False.
    assert committed and all(value is False for value in committed)


# ===========================================================================
# Simulation-aware strict set-page verification (Area 4).
# A partial page explicitly labeled simulation-unavailable must PASS; a page
# that claims availability keeps the stricter checks; malformed pages fail.
# ===========================================================================

_UNAVAILABLE_WARNING = (
    "Simulation data is unavailable for this set; simulation-derived sections "
    "are published as unavailable."
)


def _partial_page_row(set_id="set-1", *, updated="2026-07-25T00:00:00+00:00", carried=False, **meta_overrides):
    availability = {
        "available": False,
        "reason": "No simulation data found for this target",
        "asOfDate": None,
        # The REAL declaration list the set-page builder writes. Imported rather
        # than hand-listed so the fixture cannot drift from production.
        "unavailableSections": list(SIMULATION_DEPENDENT_SECTIONS),
        "carryForward": carried,
        "carriedForwardSections": (["simulationDrivers"] if carried else []),
    }
    section_freshness = {
        "simulationDrivers": (
            {"status": "stale", "dataAsOf": "2026-07-17T00:00:00+00:00", "source": "simulation_input_cards"}
            if carried
            else {"status": "missing", "dataAsOf": None}
        )
    }
    meta = {
        "snapshot": {"type": "pokemon_set_page", "builtAt": updated},
        "snapshotCompleteness": {"ok": True},
        "sectionFreshness": section_freshness,
        "simulationAvailability": availability,
        "sources": {"simulation_input_cards": "NO_ROW"},
        "warnings": [_UNAVAILABLE_WARNING],
    }
    meta.update(meta_overrides)
    return {
        "set_id": set_id,
        "updated_at": updated,
        "payload_json": {
            "target": {"target_type": "set", "target_id": set_id, "id": set_id, "name": "Alpha"},
            "summary": {},
            "top_hits": [],
            "meta": meta,
        },
    }


def _patch_page_row(monkeypatch, row):
    monkeypatch.setattr(
        refresh,
        "_read_snapshot_row",
        lambda _client, table, _sel, _filters: (row if table == "pokemon_set_page_snapshot_latest" else None),
    )
    monkeypatch.setattr(refresh, "_has_known_stale_warning", lambda _warnings: False)
    monkeypatch.setattr(refresh, "_source_rows_exist_for_set_page", lambda _client, _set_id: False)


def _verify(row_or_none):
    return refresh._verify_set_page(None, {"id": "set-1", "canonical_key": "alpha"}, rankings_updated_at=None)


# 24 + 25. A valid simulation-unavailable partial page passes strict verification;
# empty top_hits / NO_ROW simulation source do not fail when available is false.
def test_24_valid_partial_page_passes_strict(monkeypatch):
    _patch_page_row(monkeypatch, _partial_page_row())
    assert _verify(None) == []


def test_25_empty_simulation_sections_ok_when_unavailable(monkeypatch):
    row = _partial_page_row()
    # Explicitly the empty/unavailable simulation drivers.
    assert row["payload_json"]["top_hits"] == []
    assert row["payload_json"]["meta"]["sources"]["simulation_input_cards"] == "NO_ROW"
    _patch_page_row(monkeypatch, row)
    assert _verify(None) == []


# 26. The same empty sections FAIL when simulation availability is true.
def test_26_empty_sections_fail_when_available_true(monkeypatch):
    row = _partial_page_row()
    row["payload_json"]["meta"]["simulationAvailability"]["available"] = True
    row["payload_json"]["meta"]["simulationAvailability"]["unavailableSections"] = []
    row["payload_json"]["meta"]["sources"]["simulation_input_cards"] = "NO_ROWS"
    _patch_page_row(monkeypatch, row)
    problems = _verify(None)
    assert any("top_hits missing" in p for p in problems)
    assert any("simulation_input_cards source=NO_ROWS" in p for p in problems)


# 27. Missing simulationAvailability metadata fails for a partial page.
def test_27_missing_availability_metadata_fails(monkeypatch):
    row = _partial_page_row()
    del row["payload_json"]["meta"]["simulationAvailability"]
    _patch_page_row(monkeypatch, row)
    problems = _verify(None)
    assert any("simulationAvailability metadata missing" in p for p in problems)


# 28. Missing unavailable-section declarations fail.
def test_28_missing_unavailable_sections_fail(monkeypatch):
    row = _partial_page_row()
    row["payload_json"]["meta"]["simulationAvailability"]["unavailableSections"] = []
    _patch_page_row(monkeypatch, row)
    problems = _verify(None)
    assert any("unavailableSections must be nonempty" in p for p in problems)


def test_28b_incomplete_unavailable_sections_fail(monkeypatch):
    row = _partial_page_row()
    # Declares only one section — misses the required simulation-derived ones.
    row["payload_json"]["meta"]["simulationAvailability"]["unavailableSections"] = ["pull_rate_assumptions"]
    _patch_page_row(monkeypatch, row)
    problems = _verify(None)
    assert any("unavailableSections missing" in p for p in problems)


# 29. A supposedly unavailable page containing fresh/current simulation fields fails.
def test_29_unavailable_page_with_fresh_simulation_section_fails(monkeypatch):
    row = _partial_page_row()
    row["payload_json"]["meta"]["sectionFreshness"]["simulationDrivers"] = {
        "status": "fresh",
        "dataAsOf": "2026-07-25T00:00:00+00:00",
    }
    _patch_page_row(monkeypatch, row)
    problems = _verify(None)
    assert any("labeled fresh while simulation is unavailable" in p for p in problems)


# 30. A carried-forward simulation section passes only when marked stale with a date.
def test_30_carried_forward_stale_with_source_date_passes(monkeypatch):
    _patch_page_row(monkeypatch, _partial_page_row(carried=True))
    assert _verify(None) == []


def test_30b_carried_forward_not_stale_fails(monkeypatch):
    row = _partial_page_row(carried=True)
    row["payload_json"]["meta"]["sectionFreshness"]["simulationDrivers"]["status"] = "current"
    _patch_page_row(monkeypatch, row)
    problems = _verify(None)
    assert any("not labeled stale" in p for p in problems)


def test_30c_carried_forward_stale_without_source_date_fails(monkeypatch):
    row = _partial_page_row(carried=True)
    row["payload_json"]["meta"]["sectionFreshness"]["simulationDrivers"]["dataAsOf"] = None
    _patch_page_row(monkeypatch, row)
    problems = _verify(None)
    assert any("has no source/data-as-of date" in p for p in problems)


# 31. A malformed / identity-less partial page fails.
def test_31_identityless_partial_page_fails(monkeypatch):
    row = _partial_page_row()
    row["payload_json"]["target"] = {}
    _patch_page_row(monkeypatch, row)
    problems = _verify(None)
    assert any("set identity missing" in p for p in problems)


def test_31b_missing_snapshot_marker_fails(monkeypatch):
    row = _partial_page_row()
    del row["payload_json"]["meta"]["snapshot"]
    _patch_page_row(monkeypatch, row)
    problems = _verify(None)
    assert any("meta.snapshot missing" in p for p in problems)


# ---------------------------------------------------------------------------
# Opening Profit vs Cost stale-dashboard regression: the market dashboard's
# performance_vs_cost_history_json is built from the set's simulation history,
# so simulation sources must participate in market-dashboard freshness.
# ---------------------------------------------------------------------------


class _FakeQuery:
    def __init__(self, store, table, column):
        self._store = store
        self._table = table
        self._column = column
        self._filters = {}

    def eq(self, field, value):
        self._filters[field] = value
        return self

    def in_(self, field, values):
        self._filters[field] = list(values)
        return self

    def order(self, *_args, **_kwargs):
        return self

    def limit(self, *_args, **_kwargs):
        return self

    def execute(self):
        self._store["queries"].append((self._table, self._column, dict(self._filters)))
        rows = self._store["rows"].get((self._table, self._column), [])
        matched = [
            row for row in rows
            if all(row.get(field) == value for field, value in self._filters.items())
        ]
        data = [{self._column: row[self._column]} for row in matched if row.get(self._column)]
        return type("Result", (), {"data": data})()


class _FakeTable:
    def __init__(self, store, table):
        self._store = store
        self._table = table

    def select(self, column):
        return _FakeQuery(self._store, self._table, column)


class _FakeClient:
    def __init__(self, rows):
        self.store = {"rows": rows, "queries": []}

    def table(self, name):
        return _FakeTable(self.store, name)


def test_latest_for_market_dashboard_reads_simulation_sources_scoped_to_set(monkeypatch):
    seen = []

    def latest_timestamp(_client, *, table, timestamp_columns, filters=(), in_filters=()):
        seen.append((table, tuple(filters)))
        return None, [f"{table}: ok"]

    monkeypatch.setattr(refresh, "_latest_timestamp", latest_timestamp)
    monkeypatch.setattr(refresh, "_variant_ids_for_set", lambda _client, _set_id: [])
    monkeypatch.setattr(refresh, "_canonical_selected_variant_ids", lambda _client, _set_id: [])

    refresh._latest_for_market_dashboard(None, "set-1")

    assert ("simulation_latest_by_target", (("target_type", "set"), ("target_id", "set-1"))) in seen
    assert ("calculation_history_trend", (("target_type", "set"), ("target_id", "set-1"))) in seen


def test_latest_for_market_dashboard_ignores_other_sets_simulation_runs():
    rows = {
        ("simulation_latest_by_target", "updated_at"): [
            {"target_type": "set", "target_id": "set-2", "updated_at": "2026-08-02T00:00:00+00:00"},
        ],
        ("simulation_latest_by_target", "run_at"): [
            {"target_type": "set", "target_id": "set-2", "run_at": "2026-08-02T00:00:00+00:00"},
        ],
        ("calculation_history_trend", "run_created_at"): [
            {"target_type": "set", "target_id": "set-2", "run_created_at": "2026-08-02T00:00:00+00:00"},
        ],
    }
    client = _FakeClient(rows)

    latest, _checks = refresh._latest_for_market_dashboard(client, "set-1")

    assert latest is None
    simulation_filters = [
        filters for table, _column, filters in client.store["queries"]
        if table in {"simulation_latest_by_target", "calculation_history_trend"}
    ]
    assert simulation_filters
    assert all(filters.get("target_id") == "set-1" for filters in simulation_filters)


def _market_row_with_performance(performance_history, **kwargs):
    row = _market_row(**kwargs)
    row["performance_vs_cost_history_json"] = performance_history
    return row


def _no_set_value_history(_client, _set_id, *, column):
    return {"standard": None, "hits": None, "top10": None}, []


def test_market_dashboard_stale_when_simulation_run_newer_than_dashboard(monkeypatch):
    monkeypatch.setattr(
        refresh, "_latest_for_market_dashboard",
        lambda _client, _set_id: ("2026-08-02T00:00:00+00:00", []),
    )
    monkeypatch.setattr(refresh, "_latest_simulation_history_date", lambda _client, _set_id: ("2026-06-20", []))
    monkeypatch.setattr(refresh, "_latest_set_value_history_by_scope", _no_set_value_history)
    monkeypatch.setattr(
        refresh, "_read_snapshot_row",
        lambda *_args, **_kwargs: _market_row_with_performance(
            [{"date": "2026-06-20", "meanValueToCostRatio": 0.8}],
            updated_at="2026-06-21T00:00:00+00:00",
        ),
    )

    result = refresh._market_snapshot_staleness(None, "set-1", "365d")

    assert result.stale is True
    assert result.reason == "dependency newer than snapshot"


def test_market_dashboard_stale_when_simulation_history_date_newer_than_performance_history(monkeypatch):
    monkeypatch.setattr(refresh, "_latest_for_market_dashboard", lambda _client, _set_id: (None, []))
    monkeypatch.setattr(refresh, "_latest_simulation_history_date", lambda _client, _set_id: ("2026-08-02", []))
    monkeypatch.setattr(refresh, "_latest_set_value_history_by_scope", _no_set_value_history)
    monkeypatch.setattr(
        refresh, "_read_snapshot_row",
        lambda *_args, **_kwargs: _market_row_with_performance(
            [{"date": "2026-07-20", "meanValueToCostRatio": 0.8}],
        ),
    )

    result = refresh._market_snapshot_staleness(None, "set-1", "365d")

    assert result.stale is True
    assert result.reason == "simulation history newer than dashboard performance history"


def test_market_dashboard_matching_simulation_and_performance_dates_are_not_stale_for_that_reason(monkeypatch):
    monkeypatch.setattr(refresh, "_latest_for_market_dashboard", lambda _client, _set_id: (None, []))
    monkeypatch.setattr(refresh, "_latest_simulation_history_date", lambda _client, _set_id: ("2026-07-20", []))
    monkeypatch.setattr(refresh, "_latest_set_value_history_by_scope", _no_set_value_history)
    monkeypatch.setattr(
        refresh, "_read_snapshot_row",
        lambda *_args, **_kwargs: _market_row_with_performance(
            [
                {"date": "2026-07-19", "meanValueToCostRatio": 0.7},
                {"date": "2026-07-20", "meanValueToCostRatio": 0.8},
            ],
        ),
    )

    result = refresh._market_snapshot_staleness(None, "set-1", "365d")

    assert result.reason != "simulation history newer than dashboard performance history"


def test_simulation_stale_market_dashboard_triggers_set_page_rebuild_in_same_run(monkeypatch):
    rebuilt = []
    monkeypatch.setattr(refresh, "build_set_page_snapshot_row", lambda set_row, client=None: {"set_id": set_row["id"]})
    monkeypatch.setattr(refresh, "upsert_row", lambda _client, table, _row, *, on_conflict, commit: rebuilt.append(table))
    summary = refresh.RefreshSummary()
    plan = refresh.SetRefreshPlan(
        set_row={"id": "set-1", "canonical_key": "pitchBlack"},
        cards=refresh.FreshnessResult("cards", False, "fresh", "2026-08-01T00:00:00+00:00"),
        market_dashboard=refresh.FreshnessResult(
            "market_dashboard", True, "simulation history newer than dashboard performance history",
            "2026-08-01T00:00:00+00:00",
        ),
        set_page=refresh.FreshnessResult("set_page", False, "fresh", "2026-08-01T00:00:00+00:00"),
    )

    refresh._maybe_rebuild_set_page(None, plan, rankings_updated_at=None, commit=True, summary=summary)

    assert rebuilt == ["pokemon_set_page_snapshot_latest"]
    assert summary.rebuilt_sets["set_page"] == ["pitchBlack"]


def test_carried_forward_dashboard_point_does_not_establish_opvc_freshness(monkeypatch):
    # A carried-forward point exists for chart continuity only. Letting one
    # count as the history end date would make a frozen dashboard look current.
    monkeypatch.setattr(refresh, "_latest_for_market_dashboard", lambda _client, _set_id: (None, []))
    monkeypatch.setattr(refresh, "_latest_simulation_history_date", lambda _client, _set_id: ("2026-08-02", []))
    monkeypatch.setattr(refresh, "_latest_set_value_history_by_scope", _no_set_value_history)
    monkeypatch.setattr(
        refresh, "_read_snapshot_row",
        lambda *_args, **_kwargs: _market_row_with_performance(
            [
                {"date": "2026-08-01", "meanValueToCostRatio": 0.8},
                {"date": "2026-08-02", "meanValueToCostRatio": 0.8, "isCarriedForward": True},
            ],
        ),
    )

    result = refresh._market_snapshot_staleness(None, "set-1", "365d")

    assert result.stale is True
    assert result.reason == "simulation history newer than dashboard performance history"


def test_malformed_dashboard_history_still_stale_via_timestamp_comparison(monkeypatch):
    # Requirement: a simulation run_at newer than the dashboard updated_at must
    # mark it stale even when the history is unusable for a date comparison.
    monkeypatch.setattr(
        refresh, "_latest_for_market_dashboard",
        lambda _client, _set_id: ("2026-08-02T00:00:00+00:00", []),
    )
    monkeypatch.setattr(refresh, "_latest_simulation_history_date", lambda _client, _set_id: (None, []))
    monkeypatch.setattr(refresh, "_latest_set_value_history_by_scope", _no_set_value_history)
    monkeypatch.setattr(
        refresh, "_read_snapshot_row",
        lambda *_args, **_kwargs: _market_row_with_performance(
            "not-a-list",
            updated_at="2026-08-01T00:00:00+00:00",
        ),
    )

    result = refresh._market_snapshot_staleness(None, "set-1", "365d")

    assert result.stale is True
    assert result.reason == "dependency newer than snapshot"


def test_performance_history_latest_real_date_ignores_carried_points():
    history = [
        {"date": "2026-08-01"},
        {"snapshot_date": "2026-08-02", "is_carried_forward": True},
        {"snapshotDate": "2026-07-31"},
    ]
    assert refresh._performance_history_latest_real_date(history) == "2026-08-01"
    assert refresh._performance_history_latest_real_date(None) is None
    assert refresh._performance_history_latest_real_date([{"date": None}]) is None


# ---------------------------------------------------------------------------
# Variable-precision Postgres timestamps.
#
# Postgres trims trailing zeros from fractional seconds, so it emits 1-6 digits.
# datetime.fromisoformat on Python 3.8 accepts only 3 or 6, and an unparseable
# right-hand side makes _is_newer return True — reporting current snapshots as
# stale. One --strict run mis-flagged 25 sets this way.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "2026-08-03T04:59:35.25412+00:00",
        "2026-08-03T04:59:35.2+00:00",
        "2026-08-03T04:59:35.25+00:00",
        "2026-08-03T04:59:35.254+00:00",
        "2026-08-03T04:59:35.2541+00:00",
        "2026-08-03T04:59:35.254120+00:00",
        "2026-08-03T04:59:35.2541209+00:00",
        "2026-08-03T04:59:35+00:00",
        "2026-08-03T04:59:35.25412Z",
    ],
)
def test_every_postgres_fractional_second_precision_parses(text):
    assert refresh._parse_datetime(text) is not None, text


def test_a_five_digit_fraction_is_not_treated_as_newer_than_an_earlier_timestamp():
    older = "2026-08-02T23:37:20.771845+00:00"
    newer = "2026-08-03T04:59:35.25412+00:00"

    assert refresh._is_newer(newer, older) is True
    assert refresh._is_newer(older, newer) is False, (
        "an unparseable right-hand side must not make an older timestamp look newer"
    )


def test_fraction_normalization_preserves_ordering_within_the_same_second():
    assert refresh._is_newer("2026-08-03T04:59:35.9+00:00", "2026-08-03T04:59:35.25412+00:00") is True
    assert refresh._is_newer("2026-08-03T04:59:35.25412+00:00", "2026-08-03T04:59:35.9+00:00") is False


def test_genuinely_malformed_timestamps_still_parse_to_none():
    assert refresh._parse_datetime("not-a-timestamp") is None
    assert refresh._parse_datetime("") is None
    assert refresh._parse_datetime(None) is None


# ---------------------------------------------------------------------------
# Post-scrape publication continuity: BOTH families must advance together.
#
# The August-4 failure was a set page on the promoted date while Explore and
# Sealed Market stayed a day behind. These pin the orchestrator dependency edges
# that make a single refresh run carry every market surface forward.
# ---------------------------------------------------------------------------
def test_explore_rankings_freshness_depends_on_the_coordinated_market_dashboard():
    """A newer coordinated market snapshot must make Explore rankings stale."""
    reads = []

    def _latest_timestamp(_client, *, table, timestamp_columns, filters=None):
        reads.append(table)
        return ("2026-08-04T13:00:00Z" if table == "pokemon_set_market_dashboard_snapshot_latest" else None), []

    original = refresh._latest_timestamp
    try:
        refresh._latest_timestamp = _latest_timestamp
        latest, _checks = refresh._latest_for_explore_rankings(object())
    finally:
        refresh._latest_timestamp = original

    assert "pokemon_set_market_dashboard_snapshot_latest" in reads
    assert latest == "2026-08-04T13:00:00Z", "the dashboard rebuild must drive rankings staleness"


def test_set_page_freshness_depends_on_the_explore_rankings_snapshot(monkeypatch):
    """Set pages must rebuild AFTER Explore rankings, never before."""
    reads = []

    def _latest_timestamp(_client, *, table, timestamp_columns, filters=None):
        reads.append(table)
        return ("2026-08-04T13:30:00Z" if table == "pokemon_explore_rankings_snapshot_latest" else None), []

    monkeypatch.setattr(refresh, "_latest_timestamp", _latest_timestamp)
    monkeypatch.setattr(refresh, "_latest_run_id_for_set", lambda *_a, **_k: None)

    latest, _checks = refresh._latest_for_set_page(object(), "set-1")

    assert "pokemon_explore_rankings_snapshot_latest" in reads
    assert latest == "2026-08-04T13:30:00Z"


def test_generic_set_page_freshness_does_not_query_ranked_only_authorities(monkeypatch):
    reads = []

    def latest_timestamp(_client, *, table, timestamp_columns, filters=None):
        reads.append((table, tuple(filters or ())))
        return None, []

    monkeypatch.setattr(refresh, "_latest_timestamp", latest_timestamp)
    monkeypatch.setattr(refresh, "_latest_run_id_for_set", lambda *_a, **_k: "run-1")
    latest, _checks = refresh._latest_for_set_page(object(), "set-1")

    assert not any(table == "simulation_sealed_product_results" for table, _ in reads)
    assert not any(table == "pokemon_set_sealed_market_snapshot_latest" for table, _ in reads)
    assert latest is None


class _AuthorityResponse:
    def __init__(self, data):
        self.data = data


class _AuthorityQuery:
    def __init__(self, client, table):
        self.client, self.name = client, table

    def select(self, fields):
        self.fields = fields
        return self

    def eq(self, *_args):
        return self

    def limit(self, *_args):
        return self

    def execute(self):
        self.client.calls.append(self.name)
        return _AuthorityResponse(self.client.rows[self.name])


class _AuthorityClient:
    def __init__(self):
        self.calls = []
        self.rows = {
            "pokemon_set_sealed_market_snapshot_latest": [{
                "classification_version": "classification-v3",
                "updated_at": "2026-08-18T10:00:00Z",
                "payload_json": {"meta": {"snapshotContractVersion": "market-v3"}},
            }],
            "simulation_sealed_product_results": [
                {"sealed_product_id": "product-1", "updated_at": "2026-08-18T10:00:00Z"}
            ],
        }

    def table(self, name):
        return _AuthorityQuery(self, name)


def _current_ranked_decision():
    return {
        "contractVersion": "rip-decision-contract-v1",
        "currentRunAvailable": True,
        "sourceCalculationRunId": "run-1",
        "sourceSealedMarketClassificationVersion": "classification-v3",
        "sourceSealedMarketSnapshotContractVersion": "market-v3",
        "sourceSealedProductResultCount": 1,
        "sourceSealedProductResultsUpdatedAt": "2026-08-18T10:00:00Z",
        "sealedProducts": {"sourceCalculationRunId": "run-1", "productCount": 1},
        "topChase": {"sourceCalculationRunId": "run-1"},
    }


def test_non_ranked_page_avoids_new_authority_reads(monkeypatch):
    client = _AuthorityClient()
    row = _set_page_row("set-1", "2026-08-18T11:00:00Z")
    row["payload_json"]["summary"].pop("pack_rank")
    monkeypatch.setattr(refresh, "_latest_for_set_page", lambda *_a: (None, []))
    monkeypatch.setattr(refresh, "_read_snapshot_row", lambda *_a, **_k: row)
    monkeypatch.setattr(refresh, "_latest_timestamp", lambda *_a, **_k: (None, []))
    monkeypatch.setattr(refresh, "_latest_run_id_for_set", lambda *_a: "run-1")
    result = refresh._set_page_snapshot_staleness(client, "set-1")
    assert result.stale is False
    assert client.calls == []


def test_ranked_page_reads_each_authority_once_and_reuses_timestamps(monkeypatch):
    client = _AuthorityClient()
    row = _set_page_row("set-1", "2026-08-18T11:00:00Z")
    row["payload_json"]["ripDecision"] = _current_ranked_decision()
    monkeypatch.setattr(refresh, "_latest_for_set_page", lambda *_a: (None, []))
    monkeypatch.setattr(refresh, "_read_snapshot_row", lambda *_a, **_k: row)
    monkeypatch.setattr(refresh, "_latest_timestamp", lambda *_a, **_k: (None, []))
    monkeypatch.setattr(refresh, "_latest_run_id_for_set", lambda *_a: "run-1")
    result = refresh._set_page_snapshot_staleness(client, "set-1")
    assert result.stale is False
    assert client.calls.count("pokemon_set_sealed_market_snapshot_latest") == 1
    assert client.calls.count("simulation_sealed_product_results") == 1


@pytest.mark.parametrize(
    ("table", "expected_reason"),
    [
        ("pokemon_set_sealed_market_snapshot_latest", "sealed-market snapshot newer than Set page"),
        ("simulation_sealed_product_results", "sealed-product results newer than Set page"),
    ],
)
def test_ranked_authority_timestamp_invalidates_set_page(monkeypatch, table, expected_reason):
    client = _AuthorityClient()
    client.rows[table][0]["updated_at"] = "2026-08-18T12:00:00Z"
    row = _set_page_row("set-1", "2026-08-18T11:00:00Z")
    row["payload_json"]["ripDecision"] = _current_ranked_decision()
    monkeypatch.setattr(refresh, "_latest_for_set_page", lambda *_a: (None, []))
    monkeypatch.setattr(refresh, "_read_snapshot_row", lambda *_a, **_k: row)
    monkeypatch.setattr(refresh, "_latest_timestamp", lambda *_a, **_k: (None, []))
    monkeypatch.setattr(refresh, "_latest_run_id_for_set", lambda *_a: "run-1")
    result = refresh._set_page_snapshot_staleness(client, "set-1")
    assert result.stale is True
    assert result.reason == expected_reason


def test_a_failed_sealed_market_rebuild_is_a_hard_failure():
    """Sealed Market has no simulation dependency, so its failure is never soft."""
    summary = refresh.RefreshSummary()
    summary.failed_sets["sealed_market"].append("ascendedHeroes: boom")
    assert refresh._has_hard_failures(summary) is True


def test_a_failed_explore_rankings_rebuild_is_a_hard_failure():
    summary = refresh.RefreshSummary()
    summary.global_failed.append("explore_rankings: boom")
    assert refresh._has_hard_failures(summary) is True
    assert refresh._strict_should_fail(summary, commit=True) is True


def test_main_exits_nonzero_when_the_sealed_market_family_fails(monkeypatch):
    """A refresh must never report success while Sealed Market is unpublished."""
    _patch_main_pipeline(monkeypatch, fail_set=False)

    def _sealed_boom(_set_row, _commit):
        raise RuntimeError("sealed build failed")

    monkeypatch.setattr(
        "backend.scripts.build_pokemon_set_sealed_market_snapshots.build_one", _sealed_boom
    )
    monkeypatch.setattr(
        refresh, "_resolve_sets",
        lambda _client, set_id=None: [
            {"id": "11111111-1111-1111-1111-111111111111", "canonical_key": "alpha"}
        ],
    )
    monkeypatch.setattr("sys.argv", ["refresh", "--commit"])

    with pytest.raises(SystemExit) as excinfo:
        refresh.main()
    assert excinfo.value.code == 1


# ---------------------------------------------------------------------------
# Planning-phase read cost, observability, and plan-before-write safety
# ---------------------------------------------------------------------------


class _RecordingQuery:
    def __init__(self, recorder, table, rows):
        self._recorder = recorder
        self._table = table
        self._rows = rows

    def select(self, columns):
        self._recorder.append((self._table, columns))
        return self

    def eq(self, *_args, **_kwargs):
        return self

    def limit(self, *_args, **_kwargs):
        return self

    def execute(self):
        rows = self._rows

        class _Result:
            data = rows

        return _Result()


class _RecordingClient:
    def __init__(self, rows_by_table):
        self.selects = []
        self._rows_by_table = rows_by_table

    def table(self, name):
        return _RecordingQuery(self.selects, name, self._rows_by_table.get(name, []))


def _full_marker_market_row(generation_id="gen-1", **kwargs):
    row = _market_row(**kwargs)
    row["payload_json"]["meta"]["snapshot"] = {
        "type": "pokemon_set_market_dashboard",
        "movementContractVersion": "v1",
        "generationId": generation_id,
        "windowConvention": "trailing",
        "movementAsOfDate": "2026-06-20",
        "builtAt": "2026-06-21T00:00:00+00:00",
    }
    return row


def _patch_market_dependencies(monkeypatch, row):
    monkeypatch.setattr(refresh, "_latest_for_market_dashboard", lambda _client, _set_id: (None, []))
    monkeypatch.setattr(refresh, "_latest_simulation_history_date", lambda _client, _set_id: (None, []))
    monkeypatch.setattr(refresh, "_latest_set_value_history_by_scope", _no_set_value_history)
    monkeypatch.setattr(refresh, "_read_snapshot_row", lambda *_args, **_kwargs: row)


def test_market_staleness_never_downloads_the_cards_payload_for_generation_comparison(monkeypatch):
    """THE read-cost regression: one string, not a multi-megabyte document."""
    _patch_market_dependencies(monkeypatch, _full_marker_market_row())
    client = _RecordingClient(
        {"pokemon_set_cards_snapshot_latest": [{"generation_id": "gen-1"}]}
    )

    result = refresh._market_snapshot_staleness(client, "set-1", "365d")

    cards_selects = [
        columns for table, columns in client.selects
        if table == "pokemon_set_cards_snapshot_latest"
    ]
    assert cards_selects, "the cards generation marker must still be read"
    for columns in cards_selects:
        requested = [column.strip() for column in columns.split(",")]
        assert "payload_json" not in requested
    assert result.stale is False


def test_cards_generation_read_uses_a_narrow_server_side_json_projection():
    client = _RecordingClient(
        {"pokemon_set_cards_snapshot_latest": [{"generation_id": "gen-9"}]}
    )

    read = refresh._read_cards_snapshot_generation_id(client, "set-1")

    assert client.selects == [
        ("pokemon_set_cards_snapshot_latest", refresh.CARDS_GENERATION_ID_PROJECTION)
    ]
    assert refresh.CARDS_GENERATION_ID_PROJECTION == (
        "generation_id:payload_json->meta->snapshot->>generationId"
    )
    assert read.generation_id == "gen-9"
    assert read.row_found is True
    assert read.readable is True
    assert read.checks == ["pokemon_set_cards_snapshot_latest.generation_id: ok"]


def test_missing_cards_snapshot_generation_id_is_reported_explicitly():
    client = _RecordingClient({"pokemon_set_cards_snapshot_latest": []})

    read = refresh._read_cards_snapshot_generation_id(client, "set-1")

    assert read.row_found is False
    assert read.readable is True  # a missing row is not an unreadable query
    assert read.generation_id is None
    assert read.checks == ["pokemon_set_cards_snapshot_latest.generation_id: no row"]


def test_a_cards_generation_query_failure_is_never_a_matching_generation(monkeypatch):
    """Fail-closed: an unreadable cards snapshot must mark the dashboard stale."""
    _patch_market_dependencies(monkeypatch, _full_marker_market_row())
    monkeypatch.setattr(
        refresh, "_read_cards_snapshot_generation_id",
        lambda _client, _set_id: refresh.CardsGenerationRead(
            None, False, "connection reset",
            ["pokemon_set_cards_snapshot_latest.generation_id: error connection reset"],
        ),
    )

    result = refresh._market_snapshot_staleness(None, "set-1", "365d")

    assert result.stale is True
    assert "cards snapshot generation ID unreadable" in result.reason
    assert "connection reset" in result.reason


def test_cards_market_generation_mismatch_still_marks_the_dashboard_stale(monkeypatch):
    _patch_market_dependencies(monkeypatch, _full_marker_market_row(generation_id="gen-1"))
    client = _RecordingClient(
        {"pokemon_set_cards_snapshot_latest": [{"generation_id": "gen-2"}]}
    )

    result = refresh._market_snapshot_staleness(client, "set-1", "365d")

    assert result.stale is True
    assert result.reason == "cards and market dashboard generation IDs differ"


def test_matching_generation_ids_allow_the_remaining_freshness_checks(monkeypatch):
    _patch_market_dependencies(monkeypatch, _full_marker_market_row(generation_id="gen-1"))
    client = _RecordingClient(
        {"pokemon_set_cards_snapshot_latest": [{"generation_id": "gen-1"}]}
    )

    result = refresh._market_snapshot_staleness(client, "set-1", "365d")

    assert result.stale is False
    assert result.reason == "fresh"


def test_a_slow_planning_query_emits_a_bounded_diagnostic(monkeypatch, caplog):
    clock = iter([0.0, refresh.SLOW_QUERY_SECONDS + 1.0])
    monkeypatch.setattr(refresh.time, "monotonic", lambda: next(clock))
    client = _RecordingClient({"pokemon_set_cards_snapshot_latest": [{"generation_id": "g"}]})

    with caplog.at_level("WARNING", logger=refresh.logger.name):
        refresh._read_cards_snapshot_generation_id(client, "set-1")

    slow = [
        record.getMessage() for record in caplog.records
        if "[refresh-query] slow" in record.getMessage()
    ]
    assert len(slow) == 1
    assert "label=pokemon_set_cards_snapshot_latest.generation_id" in slow[0]
    assert "set_id=set-1" in slow[0]


def test_keyboard_interrupt_during_a_planning_query_propagates():
    """Ctrl+C is a BaseException and must never be classified as a query error."""

    class _Interrupting:
        def execute(self):
            raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        refresh._execute_query("any.label", _Interrupting())


def _stub_per_set_staleness(monkeypatch):
    monkeypatch.setattr(refresh, "_cards_snapshot_staleness", lambda _c, _s: refresh.FreshnessResult("cards", False, "fresh"))
    monkeypatch.setattr(refresh, "_market_snapshot_staleness", lambda _c, _s, _w: refresh.FreshnessResult("market_dashboard", False, "fresh"))
    monkeypatch.setattr(refresh, "_set_page_snapshot_staleness", lambda _c, _s: refresh.FreshnessResult("set_page", False, "fresh"))
    monkeypatch.setattr(refresh, "_global_snapshot_staleness", lambda _c, *, family: refresh.FreshnessResult(family, False, "fresh"))


def test_build_plan_logs_bounded_progress(monkeypatch, caplog):
    _stub_per_set_staleness(monkeypatch)
    set_rows = [{"id": "set-%s" % index, "canonical_key": "key%s" % index} for index in range(1, 26)]

    with caplog.at_level("INFO", logger=refresh.logger.name):
        refresh._build_plan(None, set_rows=set_rows, window="365d")

    messages = [record.getMessage() for record in caplog.records]
    assert any(message.startswith("[refresh-plan] starting sets=25") for message in messages)
    assert any(message.startswith("[refresh-plan] complete sets=25") for message in messages)
    checked = [message for message in messages if message.startswith("[refresh-plan] checked")]
    # Bounded: a heartbeat every PLANNING_PROGRESS_INTERVAL sets plus the last
    # one - never one INFO line per set.
    assert len(checked) == 25 // refresh.PLANNING_PROGRESS_INTERVAL + 1
    assert "key25" in checked[-1]


def test_build_plan_always_logs_a_slow_set(monkeypatch, caplog):
    _stub_per_set_staleness(monkeypatch)
    # set-1 takes longer than the slow threshold; set-2 is instant.
    ticks = iter([0.0, 0.0, refresh.SLOW_PLANNING_SET_SECONDS + 1.0, 1000.0, 1000.0, 1000.0])
    monkeypatch.setattr(refresh.time, "monotonic", lambda: next(ticks))

    with caplog.at_level("INFO", logger=refresh.logger.name):
        refresh._build_plan(
            None,
            set_rows=[
                {"id": "set-1", "canonical_key": "slowKey"},
                {"id": "set-2", "canonical_key": "fastKey"},
            ],
            window="365d",
        )

    checked = [
        message for message in (record.getMessage() for record in caplog.records)
        if message.startswith("[refresh-plan] checked")
    ]
    assert any("key=slowKey" in message for message in checked)


def test_planning_run_id_cache_is_scoped_to_one_invocation(monkeypatch):
    calls = []

    def _uncached(_client, set_id):
        calls.append(set_id)
        return "run-%s" % set_id

    monkeypatch.setattr(refresh, "_latest_run_id_for_set_uncached", _uncached)

    def _cards(_client, set_id):
        # Two lookups inside one planning pass; one uncached read.
        assert refresh._latest_run_id_for_set(None, set_id) == "run-%s" % set_id
        assert refresh._latest_run_id_for_set(None, set_id) == "run-%s" % set_id
        return refresh.FreshnessResult("cards", False, "fresh")

    monkeypatch.setattr(refresh, "_cards_snapshot_staleness", _cards)
    monkeypatch.setattr(refresh, "_market_snapshot_staleness", lambda _c, _s, _w: refresh.FreshnessResult("market_dashboard", False, "fresh"))
    monkeypatch.setattr(refresh, "_set_page_snapshot_staleness", lambda _c, _s: refresh.FreshnessResult("set_page", False, "fresh"))
    monkeypatch.setattr(refresh, "_global_snapshot_staleness", lambda _c, *, family: refresh.FreshnessResult(family, False, "fresh"))

    refresh._build_plan(None, set_rows=[{"id": "set-1"}], window="365d")
    assert calls == ["set-1"]
    # Torn down: the cache never survives the planning pass.
    assert refresh._PLANNING_RUN_ID_CACHE is None
    refresh._latest_run_id_for_set(None, "set-1")
    assert calls == ["set-1", "set-1"]


def test_planning_cache_is_torn_down_even_when_planning_raises(monkeypatch):
    def _boom(_client, _set_id):
        raise RuntimeError("boom")

    monkeypatch.setattr(refresh, "_cards_snapshot_staleness", _boom)
    with pytest.raises(RuntimeError):
        refresh._build_plan(None, set_rows=[{"id": "set-1"}], window="365d")
    assert refresh._PLANNING_RUN_ID_CACHE is None


def _patch_writes_as_recorders(monkeypatch, planning_error):
    """main() with a planner that fails; every write path becomes a recorder."""
    writes = []
    _patch_main_pipeline(monkeypatch)
    monkeypatch.setattr(refresh, "upsert_row", lambda *_a, **_k: writes.append("upsert_row"))
    monkeypatch.setattr(refresh, "upsert_rows", lambda *_a, **_k: writes.append("upsert_rows"))
    monkeypatch.setattr(
        refresh, "publish_explore_rip_rankings_snapshot",
        lambda *_a, **_k: writes.append("publish_explore_rip_rankings_snapshot"),
    )
    monkeypatch.setattr(
        refresh, "_maybe_rebuild_coordinated_market",
        lambda *_a, **_k: writes.append("_maybe_rebuild_coordinated_market"),
    )
    monkeypatch.setattr(
        refresh, "_maybe_rebuild_set_page", lambda *_a, **_k: writes.append("_maybe_rebuild_set_page")
    )
    monkeypatch.setattr(
        refresh, "_maybe_rebuild_rankings", lambda *_a, **_k: writes.append("_maybe_rebuild_rankings")
    )
    monkeypatch.setattr(
        refresh, "_build_validation_snapshot", lambda *_a, **_k: writes.append("_build_validation_snapshot")
    )

    def _planner(*_args, **_kwargs):
        raise planning_error

    monkeypatch.setattr(refresh, "_build_plan", _planner)
    monkeypatch.setattr("sys.argv", ["refresh", "--commit"])
    return writes


def test_no_write_runs_when_planning_is_interrupted(monkeypatch):
    """Ctrl+C during planning leaves production unchanged, and propagates."""
    writes = _patch_writes_as_recorders(monkeypatch, KeyboardInterrupt())

    with pytest.raises(KeyboardInterrupt):
        refresh.main()
    assert writes == []


def test_no_write_runs_when_planning_raises(monkeypatch):
    writes = _patch_writes_as_recorders(monkeypatch, RuntimeError("planning blew up"))

    with pytest.raises(RuntimeError):
        refresh.main()
    assert writes == []


# ---------------------------------------------------------------------------
# Heartbeat cadence.
#
# Planning measures at ~4s per set over 209 sets. At the previous interval of 10
# that is ~40s of INFO silence, which made a healthy run indistinguishable from a
# blocked one and made the "silence beyond ~10s means blocked" runbook line
# false. The interval is 3, for a ~10-20s expected heartbeat.
# ---------------------------------------------------------------------------


def _checked_heartbeats(caplog):
    return [
        message
        for message in (record.getMessage() for record in caplog.records)
        if message.startswith("[refresh-plan] checked")
    ]


def test_the_planning_interval_is_three_sets():
    assert refresh.PLANNING_PROGRESS_INTERVAL == 3


def test_an_info_heartbeat_lands_on_set_three_and_set_six(monkeypatch, caplog):
    _stub_per_set_staleness(monkeypatch)
    set_rows = [{"id": "set-%s" % index, "canonical_key": "key%s" % index} for index in range(1, 8)]

    with caplog.at_level("INFO", logger=refresh.logger.name):
        refresh._build_plan(None, set_rows=set_rows, window="365d")

    heartbeats = _checked_heartbeats(caplog)
    assert any("checked 3/7" in message for message in heartbeats), "no heartbeat at set 3"
    assert any("checked 6/7" in message for message in heartbeats), "no heartbeat at set 6"
    # Sets 1, 2, 4 and 5 stay at DEBUG — the interval must still bound the volume.
    assert not any("checked 1/7" in message for message in heartbeats)
    assert not any("checked 4/7" in message for message in heartbeats)


def test_completion_is_always_logged_even_off_the_interval(monkeypatch, caplog):
    _stub_per_set_staleness(monkeypatch)
    # 7 is not a multiple of 3: the final set must still report.
    set_rows = [{"id": "set-%s" % index, "canonical_key": "key%s" % index} for index in range(1, 8)]

    with caplog.at_level("INFO", logger=refresh.logger.name):
        refresh._build_plan(None, set_rows=set_rows, window="365d")

    messages = [record.getMessage() for record in caplog.records]
    assert any("checked 7/7" in message for message in _checked_heartbeats(caplog))
    assert any(message.startswith("[refresh-plan] complete sets=7") for message in messages)


def test_a_slow_set_logs_immediately_even_off_the_interval(monkeypatch, caplog):
    _stub_per_set_staleness(monkeypatch)
    # Set 1 is slow (never on the interval); set 2 is instant.
    ticks = iter([0.0, 0.0, refresh.SLOW_PLANNING_SET_SECONDS + 1.0, 5.0, 5.0, 5.0])
    monkeypatch.setattr(refresh.time, "monotonic", lambda: next(ticks))

    with caplog.at_level("INFO", logger=refresh.logger.name):
        refresh._build_plan(
            None,
            set_rows=[
                {"id": "set-1", "canonical_key": "slowKey"},
                {"id": "set-2", "canonical_key": "fastKey"},
            ],
            window="365d",
        )

    heartbeats = _checked_heartbeats(caplog)
    assert any("key=slowKey" in message for message in heartbeats), (
        "a set slower than the threshold must report regardless of the interval"
    )


def test_a_timed_out_query_names_the_label_and_the_set_id(caplog):
    """A blocked PostgREST call is bounded by the client's finite timeout.

    The diagnostic must identify WHICH query and WHICH set, and must not print
    the exception message (a PostgREST response body must never reach the log).
    """

    class ReadTimeout(Exception):
        pass

    class _TimingOut:
        def execute(self):
            raise ReadTimeout("secret-bearing response body")

    with caplog.at_level("WARNING", logger=refresh.logger.name):
        rows, error = refresh._execute_query(
            "pokemon_set_cards_snapshot_latest.generation_id", _TimingOut(), set_id="set-1"
        )

    assert rows == []
    assert error is not None, "a timeout is a failure, never an empty-but-fine result"
    timeouts = [
        record.getMessage()
        for record in caplog.records
        if record.levelname == "WARNING" and "[refresh-query] timeout" in record.getMessage()
    ]
    assert len(timeouts) == 1
    assert "label=pokemon_set_cards_snapshot_latest.generation_id" in timeouts[0]
    assert "set_id=set-1" in timeouts[0]
    assert "error_type=ReadTimeout" in timeouts[0]
    assert "secret-bearing response body" not in timeouts[0]


def test_an_ordinary_query_failure_stays_at_debug_and_is_never_called_a_timeout(caplog):
    """`_latest_timestamp` probes columns that may not exist, by design.

    Those handled failures must not be promoted to WARNING — hundreds of them
    per run would bury the one timeout line that matters.
    """

    class _Broken:
        def execute(self):
            raise RuntimeError("connection reset")

    with caplog.at_level("DEBUG", logger=refresh.logger.name):
        rows, error = refresh._execute_query("some.label", _Broken(), set_id="set-9")

    assert (rows, error) == ([], "connection reset")
    assert not any(
        record.levelname == "WARNING" and "[refresh-query]" in record.getMessage()
        for record in caplog.records
    )
    assert any(
        record.levelname == "DEBUG" and "label=some.label" in record.getMessage()
        for record in caplog.records
    ), "the failure must still be diagnosable at DEBUG"


def test_changing_the_heartbeat_interval_changes_no_freshness_decision(monkeypatch):
    """Cadence is observability only: same plan, same verdicts, no writes."""
    writes = []
    monkeypatch.setattr(refresh, "upsert_row", lambda *_a, **_k: writes.append("upsert_row"))
    monkeypatch.setattr(refresh, "upsert_rows", lambda *_a, **_k: writes.append("upsert_rows"))
    monkeypatch.setattr(
        refresh, "publish_explore_rip_rankings_snapshot",
        lambda *_a, **_k: writes.append("publish"),
    )

    def _verdicts(interval):
        monkeypatch.setattr(refresh, "PLANNING_PROGRESS_INTERVAL", interval)
        monkeypatch.setattr(
            refresh, "_cards_snapshot_staleness",
            lambda _c, set_id: refresh.FreshnessResult("cards", set_id.endswith("2"), "reason-%s" % set_id),
        )
        monkeypatch.setattr(
            refresh, "_market_snapshot_staleness",
            lambda _c, set_id, _w: refresh.FreshnessResult("market_dashboard", False, "fresh"),
        )
        monkeypatch.setattr(
            refresh, "_set_page_snapshot_staleness",
            lambda _c, set_id: refresh.FreshnessResult("set_page", set_id.endswith("5"), "page-%s" % set_id),
        )
        monkeypatch.setattr(
            refresh, "_global_snapshot_staleness",
            lambda _c, *, family: refresh.FreshnessResult(family, False, "fresh"),
        )
        set_rows = [{"id": "set-%s" % index, "canonical_key": "key%s" % index} for index in range(1, 8)]
        plans, rankings, validation, checks = refresh._build_plan(
            None, set_rows=set_rows, window="365d"
        )
        return [
            (plan.set_row["id"], plan.cards.stale, plan.cards.reason,
             plan.market_dashboard.stale, plan.set_page.stale, plan.set_page.reason)
            for plan in plans
        ], rankings.stale, validation.stale, checks

    assert _verdicts(3) == _verdicts(10)
    assert writes == [], "planning is read-only at every cadence"


# ---------------------------------------------------------------------------
# Safety invariants that must not regress alongside the cadence change.
# ---------------------------------------------------------------------------


def test_the_refresh_planner_selects_exactly_the_rip_contract_columns():
    """Same three columns as the audit, and never `set_canonical_key`.

    `explore_rip_statistics_latest` exposes `canonical_key`; asking for
    `set_canonical_key` makes PostgREST reject the whole SELECT.
    """
    client = _RecordingClient({"explore_rip_statistics_latest": []})

    refresh._latest_eligible_run_id_by_set(client)

    assert client.selects == [
        ("explore_rip_statistics_latest", "set_id,calculation_run_id,financial_rip_v3_score_version")
    ]
    columns = client.selects[0][1]
    assert "set_canonical_key" not in columns


def test_the_generation_comparison_never_downloads_the_cards_payload():
    """One scalar, projected server-side — not the multi-megabyte document."""
    client = _RecordingClient(
        {"pokemon_set_cards_snapshot_latest": [{"generation_id": "gen-1"}]}
    )

    refresh._read_cards_snapshot_generation_id(client, "set-1")

    columns = client.selects[0][1]
    assert columns == refresh.CARDS_GENERATION_ID_PROJECTION
    assert columns.startswith("generation_id:payload_json->")
    # The bare column would be the whole document.
    assert "payload_json," not in columns
    assert columns != "payload_json"


# ---------------------------------------------------------------------------
# Requirement J regression: the heavy per-set cards_json/payload_json read in
# _cards_snapshot_staleness (the "REQUIRED" heavy read documented at module
# top) is a local read used only to compute small integer counts and marker
# booleans. Its FreshnessResult MUST NOT carry a reference to the big payload
# forward into SetRefreshPlan/RefreshSummary state that lives across the whole
# ~210-set planning loop — otherwise memory grows with catalog size instead of
# staying bounded (requirement D).
# ---------------------------------------------------------------------------


def _huge_cards_payload(sentinel: str, n_cards: int = 500):
    """A cards_json/payload_json pair shaped like the real snapshot row, large
    enough (and tagged with a unique sentinel) that any accidental retention is
    trivially detectable by substring search over the returned object's repr."""
    cards_json = [
        {
            "id": f"card-{i}",
            "marketPrice": 1.23,
            "movement7d": {"pct": 0.1},
            "bigBlob": sentinel * 50,
        }
        for i in range(n_cards)
    ]
    payload_json = {
        "meta": {
            "snapshot": {
                "movementContractVersion": "v1",
                "generationId": "gen-1",
                "windowConvention": "trailing",
                "movementAsOfDate": "2026-06-20",
                "builtAt": "2026-06-21T00:00:00+00:00",
            }
        },
        "cardAppealMarketPriceCorrelation": {"value": 0.5},
        "hugeUnrelatedBlob": sentinel * 200,
    }
    return cards_json, payload_json


def test_cards_snapshot_staleness_does_not_retain_the_cards_payload(monkeypatch):
    sentinel = "SENTINEL-PAYLOAD-MARKER-J-REQUIREMENT"
    cards_json, payload_json = _huge_cards_payload(sentinel)
    row = {
        "set_id": "set-1",
        "cards_json": cards_json,
        "card_count": len(cards_json),
        "payload_json": payload_json,
        "updated_at": "2026-06-21T00:00:00+00:00",
    }
    monkeypatch.setattr(refresh, "_latest_for_set_cards", lambda _client, _set_id: (None, []))
    monkeypatch.setattr(refresh, "_read_snapshot_row", lambda *_args, **_kwargs: row)
    client = _RecordingClient({"pokemon_canonical_card_market_prices_latest": []})

    result = refresh._cards_snapshot_staleness(client, "set-1")

    # The freshness verdict is computed correctly from the (locally-read) payload...
    assert result.stale is False
    # ...but nothing in the returned, long-lived object graph references the
    # sentinel-tagged payload. This is the exact shape SetRefreshPlan retains
    # across the whole planning loop, so proving it here proves the plan can
    # never accumulate per-set payload bytes.
    assert sentinel not in repr(result)
    for field_value in vars(result).values():
        assert field_value is not cards_json
        assert field_value is not payload_json
        assert field_value is not row


def test_set_refresh_plan_across_many_sets_never_references_the_payloads(monkeypatch):
    """End-to-end shape of requirement D: run _build_plan over a catalog-sized
    number of sets, each with a distinct large sentinel-tagged payload, and
    assert none of the returned SetRefreshPlan objects reference ANY of them —
    proving retained state does not grow with catalog size."""
    sentinels = [f"SENTINEL-{i}-J-REQUIREMENT" for i in range(50)]
    rows_by_set_id = {}
    for i, sentinel in enumerate(sentinels):
        cards_json, payload_json = _huge_cards_payload(sentinel, n_cards=20)
        rows_by_set_id[f"set-{i}"] = {
            "set_id": f"set-{i}",
            "cards_json": cards_json,
            "card_count": len(cards_json),
            "payload_json": payload_json,
            "updated_at": "2026-06-21T00:00:00+00:00",
        }

    def _read_snapshot_row(_client, table, _select_fields, filters):
        if table != "pokemon_set_cards_snapshot_latest":
            return None
        set_id = dict(filters).get("set_id")
        return rows_by_set_id.get(set_id)

    monkeypatch.setattr(refresh, "_latest_for_set_cards", lambda _client, _set_id: (None, []))
    monkeypatch.setattr(refresh, "_read_snapshot_row", _read_snapshot_row)
    monkeypatch.setattr(refresh, "_market_snapshot_staleness", lambda _client, set_id, window: refresh.FreshnessResult("market_dashboard", False, "fresh"))
    monkeypatch.setattr(refresh, "_set_page_snapshot_staleness", lambda _client, set_id: refresh.FreshnessResult("set_page", False, "fresh"))
    monkeypatch.setattr(refresh, "_global_snapshot_staleness", lambda _client, *, family: refresh.FreshnessResult(family, False, "fresh"))

    client = _RecordingClient({"pokemon_canonical_card_market_prices_latest": []})
    set_rows = [{"id": f"set-{i}"} for i in range(len(sentinels))]
    plans, _rankings, _validation, _source_checks = refresh._build_plan(client, set_rows=set_rows, window="365d")

    assert len(plans) == len(sentinels)
    combined_repr = "\n".join(repr(plan) for plan in plans)
    for sentinel in sentinels:
        assert sentinel not in combined_repr


# ---------------------------------------------------------------------------
# Requirement E regression: _market_snapshot_staleness's row read used to
# select the FULL payload_json column PLUS all three dedicated heavy history
# columns (set_value_histories_json, top_chase_card_histories_json,
# performance_vs_cost_history_json) in ONE request — even though payload_json
# itself duplicates those same histories inline (confirmed by reading
# pokemon_snapshot_builders.build_market_dashboard_snapshot_rows). The fix:
# a narrow MARKET_DASHBOARD_META_PROJECTION read for payload_json.meta, plus
# LAZY single-column fetches for the two history columns with no scalar
# shortcut, issued only when the check that needs them is actually reached.
# ---------------------------------------------------------------------------


class _MarketDashboardRecordingQuery:
    def __init__(self, client, table):
        self._client = client
        self._table = table
        self._columns = ""

    def select(self, columns):
        self._columns = columns
        self._client.selects.append((self._table, columns))
        return self

    def eq(self, *_args, **_kwargs):
        return self

    def order(self, *_args, **_kwargs):
        return self

    def limit(self, *_args, **_kwargs):
        return self

    def execute(self):
        columns = self._columns or ""
        row = {}
        if self._table != "pokemon_set_market_dashboard_snapshot_latest":
            return type("Result", (), {"data": []})()
        if refresh.MARKET_DASHBOARD_META_PROJECTION in columns:
            row["meta"] = self._client.meta
        if "top_chase_card_histories_json" in columns:
            row["top_chase_card_histories_json"] = self._client.top_chase
        if "performance_vs_cost_history_json" in columns:
            row["performance_vs_cost_history_json"] = self._client.performance
        if "latest_market_date" in columns:
            row["latest_market_date"] = self._client.latest_market_date
        if "updated_at" in columns:
            row["updated_at"] = self._client.updated_at
        return type("Result", (), {"data": [row]})()


class _MarketDashboardRecordingClient:
    """Records every `.select(...)` column string issued against the market
    dashboard table, so a test can assert exactly which columns (narrow vs
    heavy) were actually requested — the direct, evidence-based proof that
    requirement E's narrow projection is what production issues, not just
    what the source code appears to say."""

    def __init__(self, *, meta, top_chase=None, performance=None,
                 latest_market_date="2026-06-20", updated_at="2026-06-21T00:00:00+00:00"):
        self.meta = meta
        self.top_chase = top_chase
        self.performance = performance
        self.latest_market_date = latest_market_date
        self.updated_at = updated_at
        self.selects: list = []

    def table(self, name):
        return _MarketDashboardRecordingQuery(self, name)


def _patch_market_dependencies_for_recording_client(monkeypatch):
    monkeypatch.setattr(refresh, "_latest_for_market_dashboard", lambda _client, _set_id: (None, []))
    monkeypatch.setattr(refresh, "_latest_simulation_history_date", lambda _client, _set_id: (None, []))
    monkeypatch.setattr(refresh, "_latest_set_value_history_by_scope", _no_set_value_history)


_FRESH_META = {
    "snapshot": {
        "type": "pokemon_set_market_dashboard",
        "movementContractVersion": "v1",
        "generationId": "gen-1",
        "windowConvention": "trailing",
        "movementAsOfDate": "2026-06-20",
        "builtAt": "2026-06-21T00:00:00+00:00",
    },
    "setValueHistoryLatestDateByScope": {"standard": "2026-06-20", "hits": "2026-06-20", "top10": "2026-06-20"},
}


def test_market_dashboard_row_read_never_selects_the_full_payload_json_column(monkeypatch):
    """THE requirement-E regression: the row read must use the small `meta`
    JSON-path projection, never the full (duplicate-laden) payload_json column."""
    _patch_market_dependencies_for_recording_client(monkeypatch)
    client = _MarketDashboardRecordingClient(meta=_FRESH_META, top_chase={}, performance=[])
    monkeypatch.setattr(refresh, "_read_cards_snapshot_generation_id", lambda _client, _set_id: refresh.CardsGenerationRead("gen-1", True, None, []))

    refresh._market_snapshot_staleness(client, "set-1", "365d")

    dashboard_selects = [columns for table, columns in client.selects if table == "pokemon_set_market_dashboard_snapshot_latest"]
    assert dashboard_selects, "expected at least one market-dashboard row read"
    initial_row_select = dashboard_selects[0]
    assert refresh.MARKET_DASHBOARD_META_PROJECTION in initial_row_select
    # The bare (giant, duplicate-laden) column must never appear as its own
    # selected field in the initial row read.
    assert "payload_json," not in initial_row_select
    assert not initial_row_select.startswith("payload_json")
    assert ",payload_json" not in initial_row_select.replace(refresh.MARKET_DASHBOARD_META_PROJECTION, "")


def test_market_dashboard_staleness_skips_performance_history_fetch_when_marker_missing(monkeypatch):
    """A set whose completeness marker is missing is ALREADY decided stale by
    the time the check that needs performance_vs_cost_history_json is reached
    — so that heavy column must never be requested for it."""
    _patch_market_dependencies_for_recording_client(monkeypatch)
    incomplete_meta = {}  # no "snapshot" key -> marker_missing True
    client = _MarketDashboardRecordingClient(meta=incomplete_meta, top_chase={}, performance=["SHOULD_NEVER_BE_FETCHED"])

    result = refresh._market_snapshot_staleness(client, "set-1", "365d")

    assert result.stale is True
    assert result.reason == "required completeness marker missing"
    performance_selects = [
        columns for table, columns in client.selects
        if table == "pokemon_set_market_dashboard_snapshot_latest" and "performance_vs_cost_history_json" in columns
    ]
    assert performance_selects == []


def test_market_dashboard_staleness_skips_all_heavy_columns_when_row_missing(monkeypatch):
    """No row at all -> immediate stale, before ANY heavy column is touched."""
    _patch_market_dependencies_for_recording_client(monkeypatch)

    class _EmptyQuery(_MarketDashboardRecordingQuery):
        def execute(self):
            # Row genuinely absent, regardless of which columns were asked for.
            return type("Result", (), {"data": []})()

    class _EmptyClient:
        def __init__(self):
            self.selects = []

        def table(self, name):
            return _EmptyQuery(self, name)

    client = _EmptyClient()
    result = refresh._market_snapshot_staleness(client, "set-1", "365d")

    assert result.stale is True
    assert result.reason == "snapshot row missing"
    heavy_selects = [
        columns for table, columns in client.selects
        if "top_chase_card_histories_json" in columns or "performance_vs_cost_history_json" in columns
    ]
    assert heavy_selects == []


@pytest.mark.parametrize("n_sets", [10, 200])
def test_market_snapshot_staleness_heavy_fetch_count_stays_bounded_per_set_as_catalog_grows(monkeypatch, n_sets):
    """Requirement D/E at scale: run the REAL freshness check over N synthetic
    sets, each with its own large sentinel-tagged history payload, and prove
    two things regardless of whether N is 10 or 200 (i.e. NOT proportional to
    catalog size in a way that compounds): (1) each set issues AT MOST ONE
    request for each heavy column (no duplicate/rereads), and (2) no returned
    FreshnessResult ever references another set's — or its own dropped —
    sentinel payload, matching requirement J's non-retention proof at scale."""
    _patch_market_dependencies_for_recording_client(monkeypatch)
    monkeypatch.setattr(refresh, "_read_cards_snapshot_generation_id", lambda _client, _set_id: refresh.CardsGenerationRead("gen-1", True, None, []))

    results = []
    sentinels = []
    for i in range(n_sets):
        sentinel = f"SENTINEL-MARKET-{i}-E-REQUIREMENT"
        sentinels.append(sentinel)
        client = _MarketDashboardRecordingClient(
            meta=_FRESH_META,
            top_chase={"card-1": [{"date": "2026-06-20", "value": sentinel * 20}]},
            performance=[{"date": "2026-06-20", "meanValueToCostRatio": 0.8, "blob": sentinel * 20}],
        )
        result = refresh._market_snapshot_staleness(client, f"set-{i}", "365d")
        results.append(result)

        # (1) bounded per-set request count for each heavy column: at most one.
        top_chase_selects = [c for t, c in client.selects if "top_chase_card_histories_json" in c]
        performance_selects = [c for t, c in client.selects if "performance_vs_cost_history_json" in c]
        assert len(top_chase_selects) <= 1
        assert len(performance_selects) <= 1

    # (2) no cross-set or self retention of the heavy sentinel-tagged payloads.
    combined_repr = "\n".join(repr(result) for result in results)
    for sentinel in sentinels:
        assert sentinel not in combined_repr
