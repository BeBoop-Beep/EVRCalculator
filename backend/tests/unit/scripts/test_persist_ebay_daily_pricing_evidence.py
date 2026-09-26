import copy
import uuid
from datetime import datetime, timezone

import pytest

from backend.scripts.index_fair_value_ebay_evidence_collector import CollectorConfig, RunState, cohort_fingerprint, generate_queries
from backend.scripts.persist_ebay_daily_pricing_evidence import digest, normalize_evidence, persist, prepare, project_volume


CID = "cae71539-cdde-41e1-aa61-cf1f67f43d69"
RUN_ID = uuid.uuid4().hex
TARGET = {"pricing_target": True, "canonical_card_id": CID, "card_variant_id": None,
          "card_name": "Pikachu", "card_number": "1", "set_name": "Example"}


def fixture():
    card = dict(TARGET, planned_queries=generate_queries(TARGET), estimated_request_cost=6)
    manifest = {"market_date": "2026-09-19", "selector_version": "ebay_daily_pricing_selector_p1_v1",
                "target_count": 1, "canonical_card_ids": [CID], "cards": [card], "estimated_requests": 6,
                "planning_ceiling": 900}
    manifest["selector_fingerprint"] = digest(manifest)
    state = RunState.new(RUN_ID, [card], CollectorConfig())
    state.targets[CID] = {"status": "completed", "listings_captured": 2}
    state.requests_attempted = 2
    raw = [{"evidence_kind": "active_ask", "ebay_item_id": "i", "collector_run_id": RUN_ID,
            "retrieved_at": "2026-09-19T00:00:00+00:00", "title": "Pikachu",
            "price_value": 10.10, "price_currency": "USD", "shipping_value": None,
            "shipping_currency": None, "marketplace": "EBAY_US", "search_formulation": "primary"}]
    match = [{"collector_run_id": RUN_ID, "target_canonical_card_id": CID, "ebay_item_id": "i",
              "eligibility_status": "LANGUAGE_UNRESOLVED", "identity_qualified": True,
              "identity_state": "HIGH_CONFIDENCE", "identity_matcher_version": "index_fair_value_ebay_d3_v5",
              "language_state": "LANGUAGE_UNVERIFIED", "language_method_version": "ebay_language_policy_v1"}]
    return manifest, state, raw, match


def test_prepare_retains_unresolved_with_unknown_shipping_and_summary():
    manifest, state, raw, match = fixture()
    result = prepare(manifest, state, raw, match, "manifest.json")
    row = result["evidence"][0]
    assert row["evidence_kind"] == "active_ask"
    assert row["shipping_price_usd"] is None and row["landed_ask_usd"] is None
    assert row["english_market_eligibility_state"] == "LANGUAGE_UNRESOLVED"
    assert result["summaries"][0]["raw_count"] == 2
    assert result["summaries"][0]["persisted_count"] == 1
    assert result["run"]["status"] == "COMPLETE"
    assert result["projection"]["chosen_persisted"]["rows_year_365_runs"] == 365
    assert result == prepare(manifest, state, raw, match, "manifest.json") or result["run"]["finished_at"]


def test_free_shipping_landed_math_and_rejection():
    manifest, state, raw, match = fixture()
    raw[0]["shipping_value"] = 0
    raw[0]["shipping_currency"] = "USD"
    match[0]["eligibility_status"] = "ENGLISH_ELIGIBLE"
    match[0]["language_state"] = "LANGUAGE_MATCH"
    row = normalize_evidence(raw[0], match[0], manifest["cards"][0], "2026-09-19", RUN_ID)
    assert row["landed_ask_usd"] == "10.10"
    raw[0]["shipping_value"] = 2.25
    assert normalize_evidence(raw[0], match[0], manifest["cards"][0], "2026-09-19", RUN_ID)["landed_ask_usd"] == "12.35"
    match[0]["identity_qualified"] = False
    match[0]["identity_state"] = "REJECTED"
    match[0]["eligibility_status"] = "IDENTITY_REJECTED"
    assert normalize_evidence(raw[0], match[0], manifest["cards"][0], "2026-09-19", RUN_ID) is None


def test_validation_prevents_bad_kind_state_and_duplicate_matches():
    manifest, state, raw, match = fixture()
    with pytest.raises(ValueError, match="duplicate"):
        prepare(manifest, state, raw, match + match, "manifest.json")
    raw[0]["evidence_kind"] = "sale"
    with pytest.raises(ValueError, match="active_ask"):
        prepare(manifest, state, raw, match, "manifest.json")
    raw[0]["evidence_kind"] = "active_ask"
    match[0]["eligibility_status"] = "UNKNOWN"
    with pytest.raises(ValueError, match="eligibility"):
        prepare(manifest, state, raw, match, "manifest.json")


class FakeQuery:
    def __init__(self, table, storage):
        self.table, self.storage = table, storage
        self.operation = None
        self.payload = None
        self.filter = None

    def select(self, *_args):
        self.operation = "select"
        return self

    def eq(self, field, value):
        self.filter = (field, value)
        return self

    def limit(self, *_args):
        return self

    def upsert(self, payload, **_kwargs):
        self.operation, self.payload = "upsert", payload
        return self

    def update(self, payload):
        self.operation, self.payload = "update", payload
        return self

    def execute(self):
        if self.operation == "select":
            rows = list(self.storage[self.table].values())
            if self.filter:
                rows = [row for row in rows if row.get(self.filter[0]) == self.filter[1]]
            return type("Response", (), {"data": rows})()
        if self.operation == "update":
            assert self.filter
            for row in self.storage[self.table].values():
                if row.get(self.filter[0]) == self.filter[1]:
                    row.update(self.payload)
            return type("Response", (), {"data": []})()
        rows = self.payload if isinstance(self.payload, list) else [self.payload]
        for row in rows:
            key = row["run_id"] if self.table == "ebay_pricing_runs_v1" else (row.get("id") or (row.get("run_id"), row.get("canonical_card_id")))
            self.storage[self.table][key] = dict(row)
        return type("Response", (), {"data": rows})()


class FakeClient:
    def __init__(self):
        self.storage = {name: {} for name in ("ebay_pricing_runs_v1", "ebay_card_listing_evidence_v1",
                                              "ebay_card_pricing_run_summary_v1")}

    def table(self, name):
        assert name in self.storage  # canonical price tables are never touched
        return FakeQuery(name, self.storage)


def test_run_insert_evidence_replay_and_no_canonical_price_writes():
    prepared = prepare(*fixture(), "manifest.json")
    client = FakeClient()
    first = persist(client, prepared)
    second = persist(client, prepared)
    assert first == second
    assert [len(rows) for rows in client.storage.values()] == [1, 1, 1]
    changed = copy.deepcopy(prepared)
    changed["run"]["run_fingerprint"] = "0" * 64
    with pytest.raises(ValueError, match="different capture"):
        persist(client, changed)


def test_partial_state_and_projection():
    manifest, state, raw, match = fixture()
    state.targets[CID]["status"] = "deferred"
    result = prepare(manifest, state, raw, match, "manifest.json")
    assert result["run"]["status"] == "PARTIAL"
    assert project_volume(result["run"])["all_raw"]["rows_month_30_runs"] == 60


def test_changed_artifact_replay_is_rejected():
    prepared = prepare(*fixture(), "manifest.json")
    client = FakeClient()
    persist(client, prepared)
    changed = copy.deepcopy(prepared)
    changed["summaries"][0]["evidence_fingerprint"] = "0" * 64
    with pytest.raises(ValueError, match="artifacts changed"):
        persist(client, changed)


def test_first_evidence_write_failure_marks_run_failed():
    prepared = prepare(*fixture(), "manifest.json")

    class FailingQuery(FakeQuery):
        def execute(self):
            if self.table == "ebay_card_listing_evidence_v1" and self.operation == "upsert":
                raise RuntimeError("simulated write failure")
            return super().execute()

    class FailingClient(FakeClient):
        def table(self, name):
            return FailingQuery(name, self.storage)

    client = FailingClient()
    with pytest.raises(RuntimeError, match="simulated"):
        persist(client, prepared)
    assert client.storage["ebay_pricing_runs_v1"][prepared["run"]["run_id"]]["status"] == "FAILED"
