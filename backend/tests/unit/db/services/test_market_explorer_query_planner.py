from __future__ import annotations

import copy

import pytest

from backend.db.services.market_explorer_query_planner import (
    MarketExplorerBuildInProgress,
    MarketExplorerL1Cache,
    MarketExplorerQueryPlanner,
    PreparedEquivalenceRegistry,
    merge_incremental_result,
)
from backend.domain.pokemon.market_explorer_query import (
    MODE_ALL,
    MODE_CHASE,
    normalize_query_spec,
    query_fingerprint,
)


def payload(through="2026-08-28", *, start="2026-08-27", value=101.0):
    return {
        "asOf": through,
        "historyStartDate": start,
        "indexValue": value,
        "trend": [[start, 100.0], [through, value]],
        "trackedValueHistory": [
            {"date": start, "value": 10.0}, {"date": through, "value": 11.0},
        ],
        "currentConstituents": [{"cardVariantId": "variant-1"}],
        "metadata": {"constituentCount": 1, "historyPointCount": 2},
        "reconciliation": {"eligibleUniverseCount": 1},
        "scope": {"startDate": start, "endDate": through},
    }


class FakePersistent:
    def __init__(self, row=None, *, claim=True, publish=True):
        self.row = copy.deepcopy(row)
        self.claim_result = claim
        self.publish_result = publish
        self.calls = []

    def read(self, fingerprint):
        self.calls.append("read")
        return copy.deepcopy(self.row)

    def claim(self, **kwargs):
        self.calls.append("claim")
        return self.claim_result

    def publish(self, **kwargs):
        self.calls.append("publish")
        if self.publish_result:
            self.row = {"status": "ready", "computed_through": kwargs["payload"]["asOf"],
                        "series_payload": copy.deepcopy(kwargs["payload"])}
        return self.publish_result

    def fail(self, **kwargs):
        self.calls.append("fail")


def planner():
    return MarketExplorerQueryPlanner(
        l1=MarketExplorerL1Cache(ttl_seconds=300, capacity=4), sleep=lambda _: None,
    )


def test_prepared_equivalence_precedes_both_caches_and_novel_engine():
    spec = normalize_query_spec(mode=MODE_ALL)
    registry = PreparedEquivalenceRegistry()
    registry.register(spec, lambda: payload())
    persistent = FakePersistent()
    built = []
    result = planner().execute(spec=spec, prepared=registry, persistent=persistent,
        canonical_through=lambda: pytest.fail("watermark read"),
        novel_builder=lambda *_: built.append(True))
    assert result.execution_source == "prepared"
    assert persistent.calls == [] and built == []


def test_near_equivalent_does_not_use_prepared_and_cards_sealed_never_collide():
    prepared_spec = normalize_query_spec(mode=MODE_ALL, set_ids=["a"])
    requested = normalize_query_spec(mode=MODE_ALL, set_ids=["b"])
    sealed = normalize_query_spec(mode=MODE_ALL, asset="sealed", set_ids=["a"])
    registry = PreparedEquivalenceRegistry()
    registry.register(prepared_spec, lambda: payload())
    assert registry.resolve(requested) is None
    assert query_fingerprint(prepared_spec) != query_fingerprint(sealed)


def test_l1_hit_avoids_l2_watermark_and_novel():
    spec = normalize_query_spec(mode=MODE_ALL)
    hot = MarketExplorerL1Cache()
    hot.put(query_fingerprint(spec), payload())
    instance = MarketExplorerQueryPlanner(l1=hot)
    result = instance.execute(spec=spec, prepared=PreparedEquivalenceRegistry(),
        persistent=FakePersistent(), canonical_through=lambda: pytest.fail("watermark"),
        novel_builder=lambda *_: pytest.fail("novel"))
    assert result.execution_source == "memory_cache"


def test_fresh_l2_hit_avoids_novel_and_populates_l1():
    spec = normalize_query_spec(mode=MODE_ALL)
    persistent = FakePersistent({"status": "ready", "computed_through": "2026-08-28",
                                 "series_payload": payload()})
    instance = planner()
    result = instance.execute(spec=spec, prepared=PreparedEquivalenceRegistry(),
        persistent=persistent, canonical_through=lambda: "2026-08-28",
        novel_builder=lambda *_: pytest.fail("novel"))
    assert result.execution_source == "persistent_cache"
    assert instance.l1.get(query_fingerprint(spec))["asOf"] == "2026-08-28"


def test_one_date_stale_cache_queries_anchor_and_appends_without_index_reset():
    spec = normalize_query_spec(mode=MODE_ALL)
    old = payload("2026-08-27", start="2026-08-26", value=110.0)
    persistent = FakePersistent({"status": "ready", "computed_through": "2026-08-27",
                                 "series_payload": old})
    ranges = []
    delta = payload("2026-08-28", start="2026-08-27", value=102.0)
    result = planner().execute(spec=spec, prepared=PreparedEquivalenceRegistry(),
        persistent=persistent, canonical_through=lambda: "2026-08-28",
        novel_builder=lambda start, end: ranges.append((start, end)) or delta)
    assert ranges == [("2026-08-27", "2026-08-28")]
    assert result.execution_source == "cache_incremental"
    assert result.payload["trend"] == [
        ["2026-08-26", 100.0], ["2026-08-27", 110.0], ["2026-08-28", 112.2],
    ]


def test_multi_date_incremental_sequence_appends_every_new_point():
    old = payload("2026-08-26", start="2026-08-25", value=105.0)
    delta = payload("2026-08-28", start="2026-08-26", value=120.0)
    delta["trend"] = [["2026-08-26", 100.0], ["2026-08-27", 110.0], ["2026-08-28", 120.0]]
    merged = merge_incremental_result(old, delta)
    assert [row[0] for row in merged["trend"]] == [
        "2026-08-25", "2026-08-26", "2026-08-27", "2026-08-28",
    ]
    assert merged["indexValue"] == pytest.approx(126.0)


def test_historical_repair_stale_status_forces_full_rebuild():
    spec = normalize_query_spec(mode=MODE_ALL)
    persistent = FakePersistent({"status": "stale", "computed_through": "2026-08-28",
                                 "series_payload": payload()})
    ranges = []
    result = planner().execute(spec=spec, prepared=PreparedEquivalenceRegistry(),
        persistent=persistent, canonical_through=lambda: "2026-08-28",
        novel_builder=lambda start, end: ranges.append((start, end)) or payload())
    assert ranges == [(None, "2026-08-28")]
    assert result.execution_source == "novel_interval"


def test_miss_builds_once_and_cache_write_failure_does_not_fail_response():
    spec = normalize_query_spec(mode=MODE_CHASE)
    persistent = FakePersistent(publish=False)
    builds = []
    result = planner().execute(spec=spec, prepared=PreparedEquivalenceRegistry(),
        persistent=persistent, canonical_through=lambda: "2026-08-28",
        novel_builder=lambda *_: builds.append(True) or payload())
    assert result.payload["asOf"] == "2026-08-28"
    assert builds == [True]
    assert persistent.calls == ["read", "claim", "publish"]


def test_follower_never_launches_duplicate_build_while_lease_is_active():
    spec = normalize_query_spec(mode=MODE_ALL)
    persistent = FakePersistent({"status": "building", "computed_through": None}, claim=False)
    with pytest.raises(MarketExplorerBuildInProgress):
        planner().execute(spec=spec, prepared=PreparedEquivalenceRegistry(),
            persistent=persistent, canonical_through=lambda: "2026-08-28",
            novel_builder=lambda *_: pytest.fail("duplicate build"))
    assert persistent.calls == ["read", "claim", "read", "read"]


def test_null_claim_means_migration_unavailable_and_novel_result_still_returns():
    spec = normalize_query_spec(mode=MODE_ALL)
    result = planner().execute(spec=spec, prepared=PreparedEquivalenceRegistry(),
        persistent=FakePersistent(claim=None), canonical_through=lambda: "2026-08-28",
        novel_builder=lambda *_: payload())
    assert result.execution_source == "novel_interval"

