"""Focused, mocked-DB tests for the Market Explorer daily-operationalization
orchestrator (backend/scripts/run_market_explorer_daily_publication.py).

Two layers are tested:
  1. The DB-facing helpers (metadata refresh, maintained-cache discovery/
     prewarm, historical repair) against a small fake Supabase-style client.
  2. The top-level orchestration functions (``run_daily_publication`` /
     ``run_historical_repair``) with the DB-facing helpers monkeypatched --
     this is glue code over already-tested pieces
     (``publish_market_explorer_daily_projection.run_publish`` has its own
     dedicated test suite), so the orchestration tests assert sequencing and
     failure-isolation, not projection arithmetic.
"""
from __future__ import annotations

from datetime import date
from unittest.mock import patch

import backend.scripts.run_market_explorer_daily_publication as orch


# --- Fake client for the DB-facing helpers -----------------------------------

class Response:
    def __init__(self, data):
        self.data = data


class Query:
    def __init__(self, client, kind, name, params=None):
        self.client = client
        self.kind = kind
        self.name = name
        self.params = params or {}
        self.eq_filters: dict = {}
        self.in_filters: dict = {}
        self.start = None
        self.end = None
        self._upsert_rows = None
        self._delete_ids = None

    def select(self, *_a, **_k):
        return self

    def order(self, *_a, **_k):
        return self

    def limit(self, n):
        self.end = (self.start or 0) + n - 1
        return self

    def eq(self, field, value):
        self.eq_filters[field] = value
        return self

    def in_(self, field, values):
        self.in_filters[field] = list(values)
        return self

    def gt(self, field, value):
        self.gt_value = (field, value)
        return self

    def lte(self, field, value):
        self.lte_filters = getattr(self, "lte_filters", {})
        self.lte_filters[field] = value
        return self

    def range(self, start, end):
        self.start, self.end = start, end
        return self

    def upsert(self, rows, on_conflict=None):
        self._upsert_rows = rows
        self.client.writes.append(("upsert", self.name, list(rows)))
        return self

    def delete(self):
        self._deleting = True
        return self

    def execute(self):
        if self._upsert_rows is not None:
            for row in self._upsert_rows:
                self.client.current_metadata[row["card_variant_id"]] = row
            return Response(self._upsert_rows)

        if getattr(self, "_deleting", False):
            ids = self.in_filters.get("card_variant_id", [])
            for vid in ids:
                self.client.current_metadata.pop(vid, None)
            self.client.writes.append(("delete", self.name, list(ids)))
            return Response(ids)

        if self.kind == "rpc":
            if self.name == orch.AUTHORITY_RPC:
                set_ids = self.params["p_set_ids"]
                rows = [row for row in self.client.authority_rows if row["set_id"] in set_ids]
                return Response(self._slice(rows))
            if self.name == orch.INVALIDATE_CACHE_SCOPED_RPC:
                self.client.invalidate_calls.append(sorted(self.params["p_set_ids"]))
                self.client.repair_generation += 1
                return Response(3)
            if self.name == orch.REPROJECT_DAILY_STATES_RPC:
                self.client.reproject_calls.append(dict(self.params))
                return Response(7)
            raise AssertionError(f"unexpected rpc {self.name}")

        if self.name == "pokemon_market_date_quality":
            rows = [{"market_date": d, "status": s} for d, s in self.client.approved_dates.items()]
            if "market_date" in self.eq_filters:
                rows = [r for r in rows if r["market_date"] == self.eq_filters["market_date"]]
            gt_value = getattr(self, "gt_value", None)
            if gt_value:
                _, value = gt_value
                rows = [r for r in rows if r["market_date"] > value]
            lte_filters = getattr(self, "lte_filters", {})
            if "market_date" in lte_filters:
                value = lte_filters["market_date"]
                rows = [r for r in rows if r["market_date"] <= value]
            return Response(self._slice(rows))

        if self.name == "pokemon_set_value_daily_history_coverage":
            rows = [{"set_id": sid, "has_history": True} for sid in self.client.tracked_set_ids]
            return Response(self._slice(rows))

        if self.name == "sets":
            rows = [{"id": sid, "catalog_only": sid in self.client.catalog_only_set_ids}
                    for sid in self.client.all_set_ids]
            return Response(self._slice(rows))

        if self.name == "pokemon_market_explorer_variant_merge_ledger":
            rows = [{"predecessor_variant_id": v} for v in self.client.retired_ids]
            return Response(self._slice(rows))

        if self.name == orch.CURRENT_METADATA_TABLE:
            rows = [dict(v) for v in self.client.current_metadata.values()]
            return Response(self._slice(rows))

        if self.name == orch.CACHE_TABLE:
            rows = [dict(r) for r in self.client.cache_rows
                    if r.get("cache_kind") == self.eq_filters.get("cache_kind", r.get("cache_kind"))]
            return Response(self._slice(rows))

        if self.name == orch.COVERAGE_TABLE:
            set_id = self.eq_filters.get("set_id")
            rows = [dict(r) for r in self.client.coverage_rows if r["set_id"] == set_id]
            return Response(self._slice(rows))

        raise AssertionError(f"unexpected table {self.name}")

    def _slice(self, rows):
        if self.start is None:
            return rows
        return rows[self.start:self.end + 1]


class Client:
    def __init__(self):
        self.tracked_set_ids = ["set-a", "set-b"]
        self.all_set_ids = ["set-a", "set-b", "set-catalog"]
        self.catalog_only_set_ids = {"set-catalog"}
        self.authority_rows = [
            {"card_variant_id": "v1", "set_id": "set-a"},
            {"card_variant_id": "v2", "set_id": "set-a"},
            {"card_variant_id": "v3", "set_id": "set-b"},
        ]
        self.retired_ids = set()
        self.current_metadata: dict = {}
        self.approved_dates = {"2026-09-01": "READY", "2026-09-02": "READY"}
        self.cache_rows = []
        self.coverage_rows = [
            {"set_id": "set-a", "first_market_date": "2026-04-07",
             "computed_through": "2026-09-02", "row_count": 100},
            {"set_id": "set-b", "first_market_date": "2026-04-07",
             "computed_through": "2026-09-02", "row_count": 50},
        ]
        self.writes: list = []
        self.invalidate_calls: list = []
        self.reproject_calls: list = []
        self.repair_generation = 0

    def rpc(self, name, params):
        return Query(self, "rpc", name, params)

    def table(self, name):
        return Query(self, "table", name)


# --- Market date resolution ---------------------------------------------------

def test_resolve_latest_approved_market_date_picks_max():
    client = Client()
    assert orch.resolve_latest_approved_market_date(client) == "2026-09-02"


def test_market_date_not_ready_fails_closed():
    client = Client()
    assert orch.market_date_is_approved(client, "2026-09-05") is False


# --- Metadata refresh ----------------------------------------------------------

def test_metadata_refresh_excludes_retired_and_catalog_only():
    client = Client()
    client.retired_ids = {"v2"}
    report = orch.refresh_current_metadata(client, commit=True)
    assert report.expected_row_count == 2  # v1, v3 -- v2 retired, set-catalog never in scope
    ids = set(client.current_metadata)
    assert ids == {"v1", "v3"}
    assert "v2" not in ids


def test_metadata_refresh_is_idempotent_no_spurious_removal():
    client = Client()
    orch.refresh_current_metadata(client, commit=True)
    second = orch.refresh_current_metadata(client, commit=True)
    assert second.rows_removed == 0
    assert len(client.current_metadata) == 3


def test_metadata_refresh_removes_stale_row_no_longer_current():
    client = Client()
    orch.refresh_current_metadata(client, commit=True)
    # Simulate a retirement happening after the first refresh.
    client.retired_ids = {"v3"}
    report = orch.refresh_current_metadata(client, commit=True)
    assert report.rows_removed == 1
    assert "v3" not in client.current_metadata


def test_metadata_refresh_dry_run_performs_no_writes():
    client = Client()
    report = orch.refresh_current_metadata(client, commit=False)
    assert client.current_metadata == {}
    assert report.expected_row_count == 3


# --- Maintained-cache discovery + prewarm --------------------------------------

def test_maintained_caches_discovered_dynamically_not_hardcoded():
    client = Client()
    client.cache_rows = [
        {"query_fingerprint": "fp1", "normalized_spec": {"setIds": ["set-a"]},
         "status": "ready", "cache_kind": "maintained", "computed_through": "2026-09-01",
         "label": "one"},
        {"query_fingerprint": "fp2", "normalized_spec": {"setIds": []},
         "status": "ready", "cache_kind": "novel", "computed_through": "2026-09-01",
         "label": "two"},
    ]
    rows = orch.discover_maintained_caches(client)
    assert [r["query_fingerprint"] for r in rows] == ["fp1"]  # only cache_kind=maintained


def test_one_failed_cache_does_not_block_others():
    client = Client()
    client.cache_rows = [
        {"query_fingerprint": "fp1", "normalized_spec": {"mode": "all", "setIds": ["set-a"]},
         "status": "ready", "cache_kind": "maintained", "computed_through": "2026-09-01", "label": "one"},
        {"query_fingerprint": "fp2", "normalized_spec": {"mode": "all", "setIds": ["set-b"]},
         "status": "ready", "cache_kind": "maintained", "computed_through": "2026-09-01", "label": "two"},
    ]

    def fake_advance(client_, row, *, market_date, commit):
        if row["label"] == "one":
            raise RuntimeError("boom")
        return orch.CacheAdvanceReport(fingerprint=row["query_fingerprint"], label=row["label"],
                                       status="advanced", computed_through=market_date)

    with patch.object(orch, "advance_one_maintained_cache", side_effect=fake_advance):
        result = orch.prewarm_maintained_caches(client, market_date="2026-09-02", commit=True)

    assert result["failed"] == 1
    assert result["advanced"] == 1
    assert result["attempted"] == 2


def test_already_current_cache_is_skipped_not_rebuilt():
    client = Client()
    client.cache_rows = [
        {"query_fingerprint": "fp1", "normalized_spec": {"mode": "all", "setIds": ["set-a"]},
         "status": "ready", "cache_kind": "maintained", "computed_through": "2026-09-02", "label": "one"},
    ]
    result = orch.prewarm_maintained_caches(client, market_date="2026-09-02", commit=True)
    assert result["already_current"] == 1
    assert result["advanced"] == 0


def test_scoped_prewarm_only_touches_overlapping_caches():
    client = Client()
    client.cache_rows = [
        {"query_fingerprint": "fp1", "normalized_spec": {"mode": "all", "setIds": ["set-a"]},
         "status": "ready", "cache_kind": "maintained", "computed_through": "2026-09-01", "label": "affected"},
        {"query_fingerprint": "fp2", "normalized_spec": {"mode": "all", "setIds": ["set-b"]},
         "status": "ready", "cache_kind": "maintained", "computed_through": "2026-09-01", "label": "healthy"},
    ]
    with patch.object(orch, "advance_one_maintained_cache",
                      side_effect=lambda c, row, **kw: orch.CacheAdvanceReport(
                          fingerprint=row["query_fingerprint"], label=row["label"], status="advanced")):
        result = orch.prewarm_maintained_caches(
            client, market_date="2026-09-02", commit=True, only_set_ids=["set-a"])
    assert result["attempted"] == 1
    assert result["reports"][0]["label"] == "affected"


# --- Normal-day orchestration (monkeypatched DB-facing helpers) ---------------

def test_normal_day_not_ready_is_a_noop_case_d():
    with patch.object(orch, "resolve_latest_approved_market_date", return_value=None), \
         patch.object(orch, "run_publish") as mock_publish, \
         patch.object(orch, "prewarm_maintained_caches") as mock_prewarm:
        result = orch.run_daily_publication(object(), commit=True)
    assert result["status"] == "not_ready"
    mock_publish.assert_not_called()
    mock_prewarm.assert_not_called()


def test_normal_day_full_success_case_a():
    with patch.object(orch, "resolve_latest_approved_market_date", return_value="2026-09-02"), \
         patch.object(orch, "market_date_is_approved", return_value=True), \
         patch.object(orch, "refresh_current_metadata",
                      return_value=orch.MetadataRefreshReport(expected_row_count=3)), \
         patch.object(orch, "resolve_tracked_set_ids", return_value=["set-a", "set-b"]), \
         patch.object(orch, "run_publish",
                      return_value={"failures": 0, "sets_reconciliation_failed": 0, "sets_new": 2}), \
         patch.object(orch, "prewarm_maintained_caches",
                      return_value={"attempted": 2, "advanced": 2, "already_current": 0, "failed": 0}):
        result = orch.run_daily_publication(object(), commit=True)
    assert result["status"] == "ok"
    assert result["market_date"] == "2026-09-02"
    assert result["caches"]["advanced"] == 2


def test_cache_failure_does_not_roll_back_projection_case_b():
    with patch.object(orch, "resolve_latest_approved_market_date", return_value="2026-09-02"), \
         patch.object(orch, "market_date_is_approved", return_value=True), \
         patch.object(orch, "refresh_current_metadata",
                      return_value=orch.MetadataRefreshReport(expected_row_count=3)), \
         patch.object(orch, "resolve_tracked_set_ids", return_value=["set-a", "set-b"]), \
         patch.object(orch, "run_publish",
                      return_value={"failures": 0, "sets_reconciliation_failed": 0, "sets_new": 2}), \
         patch.object(orch, "prewarm_maintained_caches",
                      return_value={"attempted": 2, "advanced": 1, "already_current": 0, "failed": 1}):
        result = orch.run_daily_publication(object(), commit=True)
    # Projection status still "ok" -- a stale/failed cache never rolls back
    # an already-committed valid projection.
    assert result["status"] == "ok"
    assert result["caches"]["failed"] == 1


def test_projection_failure_prevents_cache_prewarm_case_c():
    with patch.object(orch, "resolve_latest_approved_market_date", return_value="2026-09-02"), \
         patch.object(orch, "market_date_is_approved", return_value=True), \
         patch.object(orch, "refresh_current_metadata",
                      return_value=orch.MetadataRefreshReport(expected_row_count=3)), \
         patch.object(orch, "resolve_tracked_set_ids", return_value=["set-a", "set-b"]), \
         patch.object(orch, "run_publish",
                      return_value={"failures": 0, "sets_reconciliation_failed": 1, "sets_new": 1}), \
         patch.object(orch, "prewarm_maintained_caches") as mock_prewarm:
        result = orch.run_daily_publication(object(), commit=True)
    assert result["status"] == "projection_failed"
    mock_prewarm.assert_not_called()
    assert result["caches"] is None


def test_dry_run_same_date_rerun_is_idempotent_report_shape():
    with patch.object(orch, "resolve_latest_approved_market_date", return_value="2026-09-02"), \
         patch.object(orch, "market_date_is_approved", return_value=True), \
         patch.object(orch, "refresh_current_metadata",
                      return_value=orch.MetadataRefreshReport(expected_row_count=3)), \
         patch.object(orch, "resolve_tracked_set_ids", return_value=["set-a", "set-b"]), \
         patch.object(orch, "run_publish",
                      return_value={"failures": 0, "sets_reconciliation_failed": 0, "sets_up_to_date": 2}), \
         patch.object(orch, "prewarm_maintained_caches",
                      return_value={"attempted": 2, "advanced": 0, "already_current": 2, "failed": 0}):
        first = orch.run_daily_publication(object(), commit=False)
        second = orch.run_daily_publication(object(), commit=False)
    assert first["status"] == second["status"] == "ok"
    assert second["caches"]["already_current"] == 2


# --- Historical repair -----------------------------------------------------

def test_historical_repair_reprojects_from_earliest_affected_date():
    client = Client()
    client.approved_dates = {"2026-04-07": "READY", "2026-04-08": "READY"}
    client.authority_rows = [{"card_variant_id": "v1", "set_id": "set-a"}]
    client.coverage_rows = [{"set_id": "set-a", "first_market_date": "2026-04-07",
                             "computed_through": "2026-04-08", "row_count": 0}]

    with patch("backend.scripts.publish_market_explorer_daily_projection.load_variant_ids_for_set",
              return_value=["v1"]), \
         patch("backend.scripts.publish_market_explorer_daily_projection.load_retired_predecessor_ids",
              return_value=set()), \
         patch("backend.scripts.publish_market_explorer_daily_projection.load_interval_join",
              return_value=[{"card_variant_id": "v1"}]), \
         patch("backend.scripts.publish_market_explorer_daily_projection.count_actual_rows",
              return_value=2), \
         patch("backend.scripts.publish_market_explorer_daily_projection.activate_or_repair_coverage",
              side_effect=lambda c, *, commit, set_id, report: report.__setattr__(
                  "coverage_after", {"set_id": set_id, "computed_through": "2026-04-08", "row_count": 2})), \
         patch.object(orch, "prewarm_maintained_caches", return_value={"attempted": 0}):
        result = orch.run_historical_repair(
            client, commit=True, set_ids=["set-a"], repair_start=date(2026, 4, 7),
            repair_through=date(2026, 4, 8),
        )

    assert client.reproject_calls[0]["p_start_date"] == "2026-04-07"
    assert result["status"] == "ok"
    assert result["reconciled"] is True


def test_historical_repair_bumps_repair_generation_via_scoped_rpc():
    client = Client()
    client.approved_dates = {"2026-04-07": "READY"}
    with patch("backend.scripts.publish_market_explorer_daily_projection.load_variant_ids_for_set",
              return_value=[]), \
         patch("backend.scripts.publish_market_explorer_daily_projection.load_retired_predecessor_ids",
              return_value=set()), \
         patch("backend.scripts.publish_market_explorer_daily_projection.load_interval_join",
              return_value=[]), \
         patch("backend.scripts.publish_market_explorer_daily_projection.count_actual_rows",
              return_value=0), \
         patch("backend.scripts.publish_market_explorer_daily_projection.activate_or_repair_coverage",
              side_effect=lambda c, *, commit, set_id, report: report.__setattr__(
                  "coverage_after", {"set_id": set_id, "computed_through": "2026-04-07", "row_count": 0})), \
         patch.object(orch, "prewarm_maintained_caches", return_value={"attempted": 0}):
        result = orch.run_historical_repair(
            client, commit=True, set_ids=["set-a"], repair_start=date(2026, 4, 7),
            repair_through=date(2026, 4, 7),
        )
    assert client.invalidate_calls == [["set-a"]]
    assert client.repair_generation == 1
    assert result["repair_generation_bumped"] is True


def test_historical_repair_reconciliation_failure_blocks_coverage_and_caches():
    client = Client()
    client.approved_dates = {"2026-04-07": "READY"}
    with patch("backend.scripts.publish_market_explorer_daily_projection.load_variant_ids_for_set",
              return_value=["v1"]), \
         patch("backend.scripts.publish_market_explorer_daily_projection.load_retired_predecessor_ids",
              return_value=set()), \
         patch("backend.scripts.publish_market_explorer_daily_projection.load_interval_join",
              return_value=[{"card_variant_id": "v1"}]), \
         patch("backend.scripts.publish_market_explorer_daily_projection.count_actual_rows",
              return_value=999), \
         patch.object(orch, "prewarm_maintained_caches") as mock_prewarm:
        result = orch.run_historical_repair(
            client, commit=True, set_ids=["set-a"], repair_start=date(2026, 4, 7),
            repair_through=date(2026, 4, 7),
        )
    assert result["status"] == "reconciliation_failed"
    assert result["reconciled"] is False
    assert client.invalidate_calls == []  # never bumps generation / invalidates on failed reconcile
    mock_prewarm.assert_not_called()


def test_historical_repair_no_sets_is_a_noop():
    client = Client()
    result = orch.run_historical_repair(
        client, commit=True, set_ids=[], repair_start=date(2026, 4, 7),
    )
    assert result["status"] == "no_sets"
    assert client.reproject_calls == []


# --- Security / write boundary --------------------------------------------

def test_main_uses_service_role_client_only(monkeypatch):
    sentinel_client = object()
    monkeypatch.setattr(orch, "create_service_role_client", lambda: sentinel_client)

    captured = {}

    def fake_run_daily_publication(client, **kwargs):
        captured["client"] = client
        return {"status": "ok"}

    monkeypatch.setattr(orch, "run_daily_publication", fake_run_daily_publication)
    monkeypatch.setattr("sys.argv", ["run_market_explorer_daily_publication.py", "--dry-run"])

    exit_code = orch.main()

    assert captured["client"] is sentinel_client  # never an anon/authenticated client
    assert exit_code == 0


def test_summary_is_json_serializable():
    import json
    with patch.object(orch, "resolve_latest_approved_market_date", return_value="2026-09-02"), \
         patch.object(orch, "market_date_is_approved", return_value=True), \
         patch.object(orch, "refresh_current_metadata",
                      return_value=orch.MetadataRefreshReport(expected_row_count=3)), \
         patch.object(orch, "resolve_tracked_set_ids", return_value=["set-a"]), \
         patch.object(orch, "run_publish",
                      return_value={"failures": 0, "sets_reconciliation_failed": 0}), \
         patch.object(orch, "prewarm_maintained_caches",
                      return_value={"attempted": 0, "advanced": 0, "already_current": 0, "failed": 0}):
        result = orch.run_daily_publication(object(), commit=True)
    json.dumps(result, default=str)  # must not raise
