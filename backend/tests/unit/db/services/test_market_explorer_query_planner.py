from __future__ import annotations

import copy

import pytest

from backend.db.services.market_explorer_query_planner import (
    MarketExplorerBuildInProgress,
    MarketExplorerL1Cache,
    MarketExplorerQueryPlanner,
    PersistentMarketExplorerCache,
    PreparedEquivalenceRegistry,
    PublicationGeneration,
    PublicationWatermarkCache,
    merge_incremental_result,
    publication_scope_key,
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
    def __init__(self, row=None, *, claim=True, publish=True, repair_generation=0,
                 generation_error=False, read_error=False):
        self.row = copy.deepcopy(row)
        self.claim_result = claim
        self.publish_result = publish
        self.generation = repair_generation
        self.generation_error = generation_error
        self.read_error = read_error
        self.calls = []

    def read(self, fingerprint):
        self.calls.append("read")
        if self.read_error:
            return None
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

    def repair_generation(self, _asset):
        self.calls.append("generation")
        if self.generation_error:
            return None
        return self.generation


def planner():
    return MarketExplorerQueryPlanner(
        l1=MarketExplorerL1Cache(ttl_seconds=300, capacity=4), sleep=lambda _: None,
    )


class GenerationClient:
    def __init__(self, data=None, error=None):
        self.data = data
        self.error = error

    def table(self, _name):
        return self

    def select(self, _columns):
        return self

    def eq(self, _column, _value):
        return self

    def limit(self, _count):
        return self

    def execute(self):
        if self.error:
            raise self.error
        return type("Response", (), {"data": self.data})()


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


@pytest.mark.parametrize("value", [0, 1])
def test_persistent_repair_generation_preserves_legitimate_values(value):
    cache = PersistentMarketExplorerCache(GenerationClient([{"repair_generation": value}]))
    assert cache.repair_generation("cards") == value


def test_persistent_repair_generation_read_failure_and_missing_row_are_unknown():
    assert PersistentMarketExplorerCache(
        GenerationClient(error=RuntimeError("transient"))
    ).repair_generation("cards") is None
    assert PersistentMarketExplorerCache(GenerationClient([])).repair_generation("cards") is None


def test_near_equivalent_does_not_use_prepared_and_cards_sealed_never_collide():
    prepared_spec = normalize_query_spec(mode=MODE_ALL, set_ids=["a"])
    requested = normalize_query_spec(mode=MODE_ALL, set_ids=["b"])
    sealed = normalize_query_spec(mode=MODE_ALL, asset="sealed", set_ids=["a"])
    registry = PreparedEquivalenceRegistry()
    registry.register(prepared_spec, lambda: payload())
    assert registry.resolve(requested) is None
    assert query_fingerprint(prepared_spec) != query_fingerprint(sealed)


def test_prepared_loader_is_reinvoked_and_never_hidden_by_process_l1():
    spec = normalize_query_spec(mode=MODE_ALL)
    published = [payload("2026-08-27")]
    registry = PreparedEquivalenceRegistry()
    registry.register(spec, lambda: published[0])
    instance = planner()
    first = instance.execute(spec=spec, prepared=registry, persistent=FakePersistent(),
        canonical_through=lambda: pytest.fail("prepared owns freshness"),
        novel_builder=lambda *_: pytest.fail("novel"))
    published[0] = payload("2026-08-28")
    second = instance.execute(spec=spec, prepared=registry, persistent=FakePersistent(),
        canonical_through=lambda: pytest.fail("prepared owns freshness"),
        novel_builder=lambda *_: pytest.fail("novel"))
    assert first.payload["asOf"] == "2026-08-27"
    assert second.payload["asOf"] == "2026-08-28"


def test_l1_hit_avoids_l2_watermark_and_novel():
    spec = normalize_query_spec(mode=MODE_ALL)
    generation = PublicationGeneration("2026-08-28", 0)
    hot = MarketExplorerL1Cache()
    hot.put(query_fingerprint(spec), generation, payload())
    watermarks = PublicationWatermarkCache()
    watermarks.resolve(publication_scope_key(spec), lambda: generation)
    instance = MarketExplorerQueryPlanner(l1=hot, watermarks=watermarks)
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
    assert instance.l1.get(query_fingerprint(spec), PublicationGeneration("2026-08-28"))["asOf"] == "2026-08-28"


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
    assert persistent.calls == ["generation", "read", "claim", "publish"]


def test_follower_never_launches_duplicate_build_while_lease_is_active():
    spec = normalize_query_spec(mode=MODE_ALL)
    persistent = FakePersistent({"status": "building", "computed_through": None}, claim=False)
    with pytest.raises(MarketExplorerBuildInProgress):
        planner().execute(spec=spec, prepared=PreparedEquivalenceRegistry(),
            persistent=persistent, canonical_through=lambda: "2026-08-28",
            novel_builder=lambda *_: pytest.fail("duplicate build"))
    assert persistent.calls == ["generation", "read", "claim", "read", "read"]


def test_null_claim_means_migration_unavailable_and_novel_result_still_returns():
    spec = normalize_query_spec(mode=MODE_ALL)
    result = planner().execute(spec=spec, prepared=PreparedEquivalenceRegistry(),
        persistent=FakePersistent(claim=None), canonical_through=lambda: "2026-08-28",
        novel_builder=lambda *_: payload())
    assert result.execution_source == "novel_interval"


def test_l1_identity_requires_same_fingerprint_and_publication_generation():
    spec = normalize_query_spec(mode=MODE_ALL)
    fingerprint = query_fingerprint(spec)
    cache = MarketExplorerL1Cache()
    d1 = PublicationGeneration("2026-08-27", 4)
    cache.put(fingerprint, d1, payload("2026-08-27"))
    assert cache.get(fingerprint, d1)["asOf"] == "2026-08-27"
    assert cache.get(fingerprint, PublicationGeneration("2026-08-28", 4)) is None
    assert cache.get(fingerprint, PublicationGeneration("2026-08-27", 5)) is None


def test_d1_l1_cannot_hide_d2_and_forward_refresh_remains_incremental():
    now = [0.0]
    spec = normalize_query_spec(mode=MODE_ALL)
    watermarks = PublicationWatermarkCache(ttl_seconds=2, clock=lambda: now[0])
    instance = MarketExplorerQueryPlanner(
        l1=MarketExplorerL1Cache(clock=lambda: now[0]), watermarks=watermarks,
    )
    old = payload("2026-08-27", start="2026-08-26", value=110.0)
    persistent = FakePersistent({"status": "ready", "computed_through": "2026-08-27",
                                 "series_payload": old})
    current = ["2026-08-27"]
    first = instance.execute(spec=spec, prepared=PreparedEquivalenceRegistry(),
        persistent=persistent, canonical_through=lambda: current[0],
        novel_builder=lambda *_: pytest.fail("fresh D1 must use L2"))
    assert first.payload["asOf"] == "2026-08-27"

    current[0] = "2026-08-28"
    now[0] = 2.001
    ranges = []
    delta = payload("2026-08-28", start="2026-08-27", value=102.0)
    second = instance.execute(spec=spec, prepared=PreparedEquivalenceRegistry(),
        persistent=persistent, canonical_through=lambda: current[0],
        novel_builder=lambda start, end: ranges.append((start, end)) or delta)
    assert second.payload["asOf"] == "2026-08-28"
    assert second.execution_source == "cache_incremental"
    assert ranges == [("2026-08-27", "2026-08-28")]


def test_shared_repair_generation_invalidates_independent_worker_l1s():
    spec = normalize_query_spec(mode=MODE_ALL)
    fingerprint = query_fingerprint(spec)
    workers = [MarketExplorerL1Cache(), MarketExplorerL1Cache()]
    old = PublicationGeneration("2026-08-28", 7)
    repaired = PublicationGeneration("2026-08-28", 8)
    for cache in workers:
        cache.put(fingerprint, old, payload())
        assert cache.get(fingerprint, old) is not None
        assert cache.get(fingerprint, repaired) is None


def test_repair_generation_plus_stale_l2_forces_full_rebuild_not_append():
    spec = normalize_query_spec(mode=MODE_ALL)
    old_generation = PublicationGeneration("2026-08-28", 2)
    cache = MarketExplorerL1Cache()
    cache.put(query_fingerprint(spec), old_generation, payload())
    persistent = FakePersistent(
        {"status": "stale", "computed_through": "2026-08-28", "series_payload": payload()},
        repair_generation=3,
    )
    ranges = []
    result = MarketExplorerQueryPlanner(l1=cache).execute(
        spec=spec, prepared=PreparedEquivalenceRegistry(), persistent=persistent,
        canonical_through=lambda: "2026-08-28",
        novel_builder=lambda start, end: ranges.append((start, end)) or payload(),
    )
    assert ranges == [(None, "2026-08-28")]
    assert result.execution_source == "novel_interval"


def test_sealed_uses_the_same_publication_and_repair_generation_identity():
    spec = normalize_query_spec(mode=MODE_ALL, asset="sealed")
    fingerprint = query_fingerprint(spec)
    cache = MarketExplorerL1Cache()
    cache.put(fingerprint, PublicationGeneration("2026-08-28", 1), payload())
    assert cache.get(fingerprint, PublicationGeneration("2026-08-28", 1)) is not None
    assert cache.get(fingerprint, PublicationGeneration("2026-08-29", 1)) is None
    assert cache.get(fingerprint, PublicationGeneration("2026-08-28", 2)) is None


def test_true_same_generation_l1_hit_avoids_l2_and_novel_after_tiny_watermark_hit():
    spec = normalize_query_spec(mode=MODE_ALL)
    generation = PublicationGeneration("2026-08-28", 9)
    watermarks = PublicationWatermarkCache(ttl_seconds=2)
    watermarks.resolve(publication_scope_key(spec), lambda: generation)
    cache = MarketExplorerL1Cache()
    cache.put(query_fingerprint(spec), generation, payload())
    persistent = FakePersistent(repair_generation=pytest.fail)
    result = MarketExplorerQueryPlanner(l1=cache, watermarks=watermarks).execute(
        spec=spec, prepared=PreparedEquivalenceRegistry(), persistent=persistent,
        canonical_through=lambda: pytest.fail("database watermark lookup"),
        novel_builder=lambda *_: pytest.fail("novel"),
    )
    assert result.execution_source == "memory_cache"
    assert persistent.calls == []


def test_unknown_generation_has_no_l1_identity_and_is_not_watermark_cached():
    generation = PublicationGeneration("2026-08-28", None)
    assert generation.trusted is False
    with pytest.raises(ValueError, match="unknown repair generation"):
        _ = generation.token

    loads = iter([generation, PublicationGeneration("2026-08-28", 1)])
    watermarks = PublicationWatermarkCache(ttl_seconds=300)
    scope = ("cards", (), ())
    assert watermarks.resolve(scope, lambda: next(loads)).trusted is False
    assert watermarks.resolve(scope, lambda: next(loads)).repair_generation == 1


@pytest.mark.parametrize("asset", ["cards", "sealed"])
def test_generation_failure_bypasses_old_l1_and_uses_ready_current_l2_without_put(asset):
    spec = normalize_query_spec(mode=MODE_ALL, asset=asset)
    fingerprint = query_fingerprint(spec)
    old = PublicationGeneration("2026-08-28", 0)
    cache = MarketExplorerL1Cache()
    stale_l1_payload = payload(value=999.0)
    cache.put(fingerprint, old, stale_l1_payload)
    current_l2_payload = payload(value=111.0)
    persistent = FakePersistent(
        {"status": "ready", "computed_through": "2026-08-28",
         "series_payload": current_l2_payload}, generation_error=True,
    )

    result = MarketExplorerQueryPlanner(l1=cache).execute(
        spec=spec, prepared=PreparedEquivalenceRegistry(), persistent=persistent,
        canonical_through=lambda: "2026-08-28",
        novel_builder=lambda *_: pytest.fail("ready/current L2 is authoritative"),
    )
    assert result.execution_source == "persistent_cache"
    assert result.payload["indexValue"] == 111.0
    assert cache.get(fingerprint, old)["indexValue"] == 999.0
    assert persistent.calls == ["generation", "read"]


@pytest.mark.parametrize("asset", ["cards", "sealed"])
def test_generation_failure_with_stale_l2_forces_full_rebuild(asset):
    spec = normalize_query_spec(mode=MODE_ALL, asset=asset)
    persistent = FakePersistent(
        {"status": "stale", "computed_through": "2026-08-28", "series_payload": payload()},
        generation_error=True,
    )
    ranges = []
    result = planner().execute(
        spec=spec, prepared=PreparedEquivalenceRegistry(), persistent=persistent,
        canonical_through=lambda: "2026-08-28",
        novel_builder=lambda start, end: ranges.append((start, end)) or payload(),
    )
    assert result.execution_source == "novel_interval"
    assert ranges == [(None, "2026-08-28")]


def test_generation_failure_with_missing_or_failed_l2_remains_available():
    spec = normalize_query_spec(mode=MODE_ALL)
    persistent = FakePersistent(claim=None, generation_error=True, read_error=True)
    result = planner().execute(
        spec=spec, prepared=PreparedEquivalenceRegistry(), persistent=persistent,
        canonical_through=lambda: "2026-08-28",
        novel_builder=lambda start, end: payload(),
    )
    assert result.execution_source == "novel_interval"
    assert persistent.calls == ["generation", "read", "claim"]


def test_generation_failure_preserves_active_lease_follower_semantics():
    spec = normalize_query_spec(mode=MODE_ALL)
    persistent = FakePersistent(
        {"status": "building", "computed_through": None}, claim=False,
        generation_error=True,
    )
    with pytest.raises(MarketExplorerBuildInProgress):
        planner().execute(
            spec=spec, prepared=PreparedEquivalenceRegistry(), persistent=persistent,
            canonical_through=lambda: "2026-08-28",
            novel_builder=lambda *_: pytest.fail("must not duplicate active build"),
        )
    assert persistent.calls == ["generation", "read", "claim", "read", "read"]


def test_failed_generation_is_retried_and_next_trusted_generation_can_use_l1():
    spec = normalize_query_spec(mode=MODE_ALL)
    fingerprint = query_fingerprint(spec)
    cache = MarketExplorerL1Cache()
    repaired = PublicationGeneration("2026-08-28", 1)
    cache.put(fingerprint, repaired, payload(value=123.0))
    watermarks = PublicationWatermarkCache(ttl_seconds=300)
    persistent = FakePersistent(
        {"status": "ready", "computed_through": "2026-08-28", "series_payload": payload()},
        generation_error=True,
    )
    instance = MarketExplorerQueryPlanner(l1=cache, watermarks=watermarks)
    first = instance.execute(
        spec=spec, prepared=PreparedEquivalenceRegistry(), persistent=persistent,
        canonical_through=lambda: "2026-08-28",
        novel_builder=lambda *_: pytest.fail("L2 ready"),
    )
    persistent.generation_error = False
    persistent.generation = 1
    second = instance.execute(
        spec=spec, prepared=PreparedEquivalenceRegistry(), persistent=persistent,
        canonical_through=lambda: "2026-08-28",
        novel_builder=lambda *_: pytest.fail("trusted L1"),
    )
    assert first.execution_source == "persistent_cache"
    assert second.execution_source == "memory_cache"
    assert second.payload["indexValue"] == 123.0
    assert persistent.calls.count("generation") == 2


def test_two_workers_cannot_serve_old_l1_when_one_generation_read_fails():
    spec = normalize_query_spec(mode=MODE_ALL)
    fingerprint = query_fingerprint(spec)
    caches = [MarketExplorerL1Cache(), MarketExplorerL1Cache()]
    for cache in caches:
        cache.put(fingerprint, PublicationGeneration("2026-08-28", 0), payload(value=999.0))

    known = MarketExplorerQueryPlanner(l1=caches[0]).execute(
        spec=spec, prepared=PreparedEquivalenceRegistry(),
        persistent=FakePersistent(
            {"status": "stale", "computed_through": "2026-08-28", "series_payload": payload()},
            repair_generation=1,
        ),
        canonical_through=lambda: "2026-08-28", novel_builder=lambda *_: payload(value=111.0),
    )
    unknown = MarketExplorerQueryPlanner(l1=caches[1]).execute(
        spec=spec, prepared=PreparedEquivalenceRegistry(),
        persistent=FakePersistent(
            {"status": "stale", "computed_through": "2026-08-28", "series_payload": payload()},
            generation_error=True,
        ),
        canonical_through=lambda: "2026-08-28", novel_builder=lambda *_: payload(value=112.0),
    )
    assert known.payload["indexValue"] == 111.0
    assert unknown.payload["indexValue"] == 112.0
