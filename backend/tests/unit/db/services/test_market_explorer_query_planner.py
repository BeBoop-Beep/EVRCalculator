from __future__ import annotations

import copy

import pytest

from backend.db.services.market_explorer_query_planner import (
    MarketExplorerBuildInProgress,
    MarketExplorerL1Cache,
    MarketExplorerPublishFailed,
    MarketExplorerQueryPlanner,
    PersistentMarketExplorerCache,
    PreparedEquivalenceRegistry,
    PublicationGeneration,
    PublicationWatermarkCache,
    merge_incremental_result,
    publication_scope_key,
    resolve_cards_canonical_through,
    resolve_canonical_through,
)
from backend.domain.pokemon.market_explorer_query import (
    MARKET_EXPLORER_INSTRUMENT_METHODOLOGY_VERSIONS,
    MARKET_EXPLORER_QUERY_CONTRACT_VERSION,
    MARKET_EXPLORER_SERVICE_VERSIONS,
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

    def read(self, fingerprint, summary=False):
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


class WatermarkQuery:
    def __init__(self, rows, filters=(), order=None, limit_count=None):
        self.rows = rows
        self.filters = filters
        self.ordering = order
        self.limit_count = limit_count

    def select(self, _columns):
        return self

    def eq(self, column, value):
        return WatermarkQuery(self.rows, self.filters + ((column, "eq", value),),
                              self.ordering, self.limit_count)

    def in_(self, column, values):
        return WatermarkQuery(self.rows, self.filters + ((column, "in", set(values)),),
                              self.ordering, self.limit_count)

    def lte(self, column, value):
        return WatermarkQuery(self.rows, self.filters + ((column, "lte", value),),
                              self.ordering, self.limit_count)

    def order(self, column, desc=False, **_kwargs):
        return WatermarkQuery(self.rows, self.filters, (column, desc), self.limit_count)

    def limit(self, count):
        return WatermarkQuery(self.rows, self.filters, self.ordering, count)

    def execute(self):
        rows = list(self.rows)
        for column, operator, value in self.filters:
            if operator == "eq":
                rows = [row for row in rows if row.get(column) == value]
            elif operator == "lte":
                rows = [row for row in rows if str(row.get(column) or "") <= str(value)]
            else:
                rows = [row for row in rows if row.get(column) in value]
        if self.ordering:
            column, desc = self.ordering
            rows.sort(key=lambda row: str(row.get(column) or ""), reverse=desc)
        if self.limit_count is not None:
            rows = rows[:self.limit_count]
        return type("Response", (), {"data": rows})()


class WatermarkClient:
    def __init__(self, *, coverage_latest="2026-08-29", quality=None, has_history=True):
        self.coverage_latest = coverage_latest
        self.quality = quality or [
            {"market_date": "2026-08-27", "tcg": "pokemon", "status": "READY"},
            {"market_date": "2026-08-28", "tcg": "pokemon", "status": "READY"},
        ]
        self.has_history = has_history

    def table(self, name):
        if name == "pokemon_set_value_daily_history_coverage":
            rows = ([{"set_id": "set-a", "has_history": True,
                      "latest_snapshot_date": self.coverage_latest}]
                    if self.has_history else [])
            return WatermarkQuery(rows)
        if name == "pokemon_market_date_quality":
            return WatermarkQuery(self.quality)
        if name == "sets":
            return WatermarkQuery([])
        raise AssertionError(name)


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


def test_cards_watermark_uses_quality_when_set_value_coverage_is_ahead():
    spec = normalize_query_spec(mode=MODE_ALL, set_ids=["set-a"])
    assert resolve_canonical_through(
        WatermarkClient(coverage_latest="2026-08-29"), spec
    ) == "2026-08-28"


def test_cards_historical_horizon_ignores_later_in_progress_dates():
    quality = [
        {"market_date": date, "tcg": "pokemon", "status": "READY"}
        for date in ("2026-08-28", "2026-08-29", "2026-08-30")
    ]
    assert resolve_cards_canonical_through(
        WatermarkClient(quality=quality), {"set-a"}, through_date="2026-08-28"
    ) == "2026-08-28"


def test_cards_watermark_skips_degraded_dates_but_accepts_later_ready_date():
    quality = [
        {"market_date": "2026-08-27", "tcg": "pokemon", "status": "READY"},
        {"market_date": "2026-08-28", "tcg": "pokemon", "status": "DEGRADED"},
        {"market_date": "2026-08-29", "tcg": "pokemon", "status": "READY"},
    ]
    spec = normalize_query_spec(mode=MODE_ALL, set_ids=["set-a"])
    assert resolve_canonical_through(WatermarkClient(quality=quality), spec) == "2026-08-29"


def test_open_interval_ahead_does_not_advance_beyond_quality_authority():
    spec = normalize_query_spec(mode=MODE_ALL, set_ids=["set-a"])
    client = WatermarkClient(coverage_latest="2026-08-30")
    assert resolve_canonical_through(client, spec) == "2026-08-28"


def test_cards_watermark_no_history_scope_does_not_invent_a_date():
    spec = normalize_query_spec(mode=MODE_ALL, set_ids=["set-a"])
    with pytest.raises(RuntimeError, match="no scoped history"):
        resolve_canonical_through(WatermarkClient(has_history=False), spec)


def test_set_value_ahead_keeps_ready_d2_l2_as_true_hit():
    spec = normalize_query_spec(mode=MODE_ALL, set_ids=["set-a"])
    client = WatermarkClient(coverage_latest="2026-08-29")
    persistent = FakePersistent({"status": "ready", "computed_through": "2026-08-28",
                                 "series_payload": payload("2026-08-28")})
    result = planner().execute(
        spec=spec, prepared=PreparedEquivalenceRegistry(), persistent=persistent,
        canonical_through=lambda: resolve_canonical_through(client, spec),
        novel_builder=lambda *_: pytest.fail("D2 L2 is current"),
    )
    assert result.execution_source == "persistent_cache"


def test_quality_forward_publication_moves_generation_and_appends_d1_d2():
    now = [0.0]
    quality = [{"market_date": "2026-08-27", "tcg": "pokemon", "status": "READY"}]
    client = WatermarkClient(quality=quality)
    spec = normalize_query_spec(mode=MODE_ALL, set_ids=["set-a"])
    persistent = FakePersistent({"status": "ready", "computed_through": "2026-08-27",
                                 "series_payload": payload("2026-08-27", start="2026-08-26")})
    instance = MarketExplorerQueryPlanner(
        l1=MarketExplorerL1Cache(clock=lambda: now[0]),
        watermarks=PublicationWatermarkCache(ttl_seconds=2, clock=lambda: now[0]),
    )
    first = instance.execute(spec=spec, prepared=PreparedEquivalenceRegistry(),
        persistent=persistent, canonical_through=lambda: resolve_canonical_through(client, spec),
        novel_builder=lambda *_: pytest.fail("D1 L2 is current"))
    quality.append({"market_date": "2026-08-28", "tcg": "pokemon", "status": "READY"})
    now[0] = 2.001
    calls = []
    second = instance.execute(spec=spec, prepared=PreparedEquivalenceRegistry(),
        persistent=persistent, canonical_through=lambda: resolve_canonical_through(client, spec),
        novel_builder=lambda start, end: calls.append((start, end)) or payload("2026-08-28", start="2026-08-27"))
    assert first.execution_source == "persistent_cache"
    assert second.execution_source == "cache_incremental"
    assert calls == [("2026-08-27", "2026-08-28")]


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


def test_miss_builds_once_and_cache_write_failure_propagates_as_publish_failed():
    # Intentionally changed behavior: a publish() that returns False used to
    # be swallowed as a "best effort" cache write and still reported success.
    # It is now a real, propagated failure -- the caller must be able to tell
    # the cache did not durably persist, and the build lease must be released.
    spec = normalize_query_spec(mode=MODE_CHASE)
    persistent = FakePersistent(publish=False)
    builds = []
    with pytest.raises(MarketExplorerPublishFailed):
        planner().execute(spec=spec, prepared=PreparedEquivalenceRegistry(),
            persistent=persistent, canonical_through=lambda: "2026-08-28",
            novel_builder=lambda *_: builds.append(True) or payload())
    assert builds == [True]
    assert persistent.calls == ["generation", "read", "claim", "publish", "fail"]


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


# --- Recoverable failed-base lifecycle (Global All Raw stuck-failed recovery) ---

_UNSET = object()


def _failed_global_row(asset="cards", *, through="2026-09-02",
                        series_payload=_UNSET, query_contract_version=None,
                        service_version=None, instrument_methodology_version=None,
                        build_token=None, build_expires_at=None):
    return {
        "status": "failed",
        "computed_from": "2026-04-07",
        "computed_through": through,
        "series_payload": (
            payload(through, start="2026-04-07") if series_payload is _UNSET else series_payload
        ),
        "query_contract_version": (
            MARKET_EXPLORER_QUERY_CONTRACT_VERSION if query_contract_version is None
            else query_contract_version
        ),
        "service_version": (
            MARKET_EXPLORER_SERVICE_VERSIONS[asset] if service_version is None else service_version
        ),
        "instrument_methodology_version": (
            MARKET_EXPLORER_INSTRUMENT_METHODOLOGY_VERSIONS[asset]
            if instrument_methodology_version is None else instrument_methodology_version
        ),
        "build_token": build_token,
        "build_expires_at": build_expires_at,
    }


def test_failed_row_with_valid_last_good_artifact_is_recoverable_build_base():
    """1. A failed row with a valid, version-compatible payload is a usable base."""
    spec = normalize_query_spec(mode=MODE_ALL)
    persistent = FakePersistent(_failed_global_row(through="2026-09-02"))
    ranges = []
    result = planner().execute(spec=spec, prepared=PreparedEquivalenceRegistry(),
        persistent=persistent, canonical_through=lambda: "2026-09-03",
        novel_builder=lambda start, end: ranges.append((start, end)) or
            payload("2026-09-03", start="2026-09-02"))
    assert ranges == [("2026-09-02", "2026-09-03")]
    assert result.execution_source.startswith("cache_incremental")


def test_failed_row_is_never_returned_as_a_persistent_cache_hit():
    """2. status='failed' must never short-circuit as a servable cache hit."""
    spec = normalize_query_spec(mode=MODE_ALL)
    persistent = FakePersistent(_failed_global_row(through="2026-09-03"))
    result = planner().execute(spec=spec, prepared=PreparedEquivalenceRegistry(),
        persistent=persistent, canonical_through=lambda: "2026-09-03",
        novel_builder=lambda start, end: payload("2026-09-03", start="2026-09-02"))
    assert result.execution_source != "persistent_cache"


def test_builder_receives_recoverable_failed_previous_not_none():
    """3. The builder receives previous='2026-09-02', not a cold-rebuild None."""
    spec = normalize_query_spec(mode=MODE_ALL)
    persistent = FakePersistent(_failed_global_row(through="2026-09-02"))
    seen = []
    planner().execute(spec=spec, prepared=PreparedEquivalenceRegistry(),
        persistent=persistent, canonical_through=lambda: "2026-09-03",
        novel_builder=lambda start, end: seen.append(start) or
            payload("2026-09-03", start="2026-09-02"))
    assert seen == ["2026-09-02"]


def test_successful_recovery_publishes_ready_through_new_watermark():
    """4. A successful recovery build publishes status='ready' through D."""
    spec = normalize_query_spec(mode=MODE_ALL)
    persistent = FakePersistent(_failed_global_row(through="2026-09-02"))
    planner().execute(spec=spec, prepared=PreparedEquivalenceRegistry(),
        persistent=persistent, canonical_through=lambda: "2026-09-03",
        novel_builder=lambda start, end: payload("2026-09-03", start="2026-09-02"))
    assert persistent.row["status"] == "ready"
    assert str(persistent.row["computed_through"])[:10] == "2026-09-03"


def test_failed_row_with_no_payload_is_not_recoverable():
    """5. A failed row with no persisted payload cannot seed an incremental build."""
    spec = normalize_query_spec(mode=MODE_ALL)
    row = _failed_global_row(series_payload=None)
    persistent = FakePersistent(row)
    ranges = []
    planner().execute(spec=spec, prepared=PreparedEquivalenceRegistry(),
        persistent=persistent, canonical_through=lambda: "2026-09-03",
        novel_builder=lambda start, end: ranges.append(start) or payload("2026-09-03"))
    assert ranges == [None]


def test_failed_row_with_no_computed_through_is_not_recoverable():
    """6. A failed row missing computed_through cannot seed an incremental build."""
    spec = normalize_query_spec(mode=MODE_ALL)
    row = _failed_global_row()
    row["computed_through"] = None
    persistent = FakePersistent(row)
    ranges = []
    planner().execute(spec=spec, prepared=PreparedEquivalenceRegistry(),
        persistent=persistent, canonical_through=lambda: "2026-09-03",
        novel_builder=lambda start, end: ranges.append(start) or payload("2026-09-03"))
    assert ranges == [None]


def test_incompatible_service_version_is_not_recoverable():
    """7. A version-incompatible failed row must fail closed to a cold rebuild."""
    spec = normalize_query_spec(mode=MODE_ALL)
    row = _failed_global_row(service_version="pokemon-market-explorer-cards-v0-ancient")
    persistent = FakePersistent(row)
    ranges = []
    planner().execute(spec=spec, prepared=PreparedEquivalenceRegistry(),
        persistent=persistent, canonical_through=lambda: "2026-09-03",
        novel_builder=lambda start, end: ranges.append(start) or payload("2026-09-03"))
    assert ranges == [None]


def test_untrusted_repair_generation_makes_failed_row_unrecoverable():
    """8. An unknown/invalidated repair generation must not recover a failed row."""
    spec = normalize_query_spec(mode=MODE_ALL)
    persistent = FakePersistent(_failed_global_row(), generation_error=True)
    ranges = []
    planner().execute(spec=spec, prepared=PreparedEquivalenceRegistry(),
        persistent=persistent, canonical_through=lambda: "2026-09-03",
        novel_builder=lambda start, end: ranges.append(start) or payload("2026-09-03"))
    assert ranges == [None]


class LifecyclePersistent:
    """Mirrors the real RPC contract: claim/fail never clear series_payload."""

    def __init__(self, row):
        self.row = copy.deepcopy(row)
        self.calls = []
        self.publish_result = True

    def read(self, fingerprint, summary=False):
        self.calls.append("read")
        return copy.deepcopy(self.row)

    def claim(self, **kwargs):
        self.calls.append("claim")
        # claim_pokemon_market_explorer_query_cache_build only ever touches
        # status/build_* columns -- computed_through/series_payload survive.
        if self.row is None:
            self.row = {"status": "building"}
        else:
            self.row["status"] = "building"
        return True

    def publish(self, **kwargs):
        self.calls.append("publish")
        if not self.publish_result:
            return False
        self.row.update({
            "status": "ready",
            "computed_through": kwargs["payload"]["asOf"],
            "series_payload": copy.deepcopy(kwargs["payload"]),
        })
        return True

    def fail(self, **kwargs):
        self.calls.append("fail")
        # fail_pokemon_market_explorer_query_cache_build only clears
        # status/build_* columns -- the prior ready payload is untouched.
        if self.row is None:
            self.row = {"status": "failed"}
        else:
            self.row["status"] = "failed"

    def repair_generation(self, _asset):
        self.calls.append("generation")
        return 0


def test_ready_cache_refresh_failure_retains_last_good_ready_artifact():
    """9. A ready cache whose refresh fails keeps its last-good payload intact."""
    spec = normalize_query_spec(mode=MODE_ALL)
    good_payload = payload("2026-09-02", start="2026-04-07")
    persistent = LifecyclePersistent({
        "status": "ready", "computed_from": "2026-04-07", "computed_through": "2026-09-02",
        "series_payload": good_payload,
        "query_contract_version": MARKET_EXPLORER_QUERY_CONTRACT_VERSION,
        "service_version": MARKET_EXPLORER_SERVICE_VERSIONS["cards"],
        "instrument_methodology_version": MARKET_EXPLORER_INSTRUMENT_METHODOLOGY_VERSIONS["cards"],
        "build_token": None, "build_expires_at": None,
    })
    persistent.publish_result = False

    def failing_builder(start, end):
        raise RuntimeError("57014 statement timeout")

    with pytest.raises(RuntimeError, match="57014"):
        planner().execute(spec=spec, prepared=PreparedEquivalenceRegistry(),
            persistent=persistent, canonical_through=lambda: "2026-09-03",
            novel_builder=failing_builder)

    assert persistent.row["status"] == "failed"
    assert persistent.row["computed_through"] == "2026-09-02"
    assert persistent.row["series_payload"] == good_payload


def test_never_successful_cache_may_remain_failed_without_fabricated_ready():
    """10. A cache with no prior ready publish stays failed; no ready state is invented."""
    spec = normalize_query_spec(mode=MODE_ALL)
    persistent = LifecyclePersistent(None)

    def failing_builder(start, end):
        raise RuntimeError("cold build failed")

    with pytest.raises(RuntimeError, match="cold build failed"):
        planner().execute(spec=spec, prepared=PreparedEquivalenceRegistry(),
            persistent=persistent, canonical_through=lambda: "2026-09-03",
            novel_builder=failing_builder)

    # No row was ever published ready -- fail() marks the attempt failed, it
    # never fabricates a ready artifact from nothing.
    assert persistent.row["status"] == "failed"
    assert "series_payload" not in persistent.row


def test_publish_false_raises_and_releases_the_build_lease():
    """11 & 13. publish()->False raises, and fail() releases the lease so a
    later attempt is free to claim again."""
    spec = normalize_query_spec(mode=MODE_CHASE)
    persistent = FakePersistent(publish=False)
    with pytest.raises(MarketExplorerPublishFailed):
        planner().execute(spec=spec, prepared=PreparedEquivalenceRegistry(),
            persistent=persistent, canonical_through=lambda: "2026-08-28",
            novel_builder=lambda *_: payload())
    assert persistent.calls[-1] == "fail"

    # Lease released -> a subsequent build attempt can claim and succeed.
    persistent.publish_result = True
    persistent.calls = []
    result = planner().execute(spec=spec, prepared=PreparedEquivalenceRegistry(),
        persistent=persistent, canonical_through=lambda: "2026-08-28",
        novel_builder=lambda *_: payload())
    assert result.execution_source == "novel_interval"
    assert "claim" in persistent.calls


def test_publish_false_never_produces_a_successful_planner_result():
    """12. No PlannerResult / execution_source can be observed from a False publish."""
    spec = normalize_query_spec(mode=MODE_ALL)
    persistent = FakePersistent(publish=False)
    result_holder = {}
    try:
        result_holder["value"] = planner().execute(
            spec=spec, prepared=PreparedEquivalenceRegistry(), persistent=persistent,
            canonical_through=lambda: "2026-08-28", novel_builder=lambda *_: payload(),
        )
    except MarketExplorerPublishFailed:
        pass
    assert "value" not in result_holder


def test_recovered_build_republishes_normalized_constituent_detail():
    """14. A recovered build's payload still carries currentConstituents intact."""
    spec = normalize_query_spec(mode=MODE_ALL)
    persistent = FakePersistent(_failed_global_row(through="2026-09-02"))
    result = planner().execute(spec=spec, prepared=PreparedEquivalenceRegistry(),
        persistent=persistent, canonical_through=lambda: "2026-09-03",
        novel_builder=lambda start, end: payload("2026-09-03", start="2026-09-02"))
    assert result.payload["currentConstituents"] == [{"cardVariantId": "variant-1"}]
    assert persistent.row["series_payload"]["currentConstituents"] == [
        {"cardVariantId": "variant-1"},
    ]


def test_existing_l1_l2_cache_hit_semantics_unchanged_regression():
    """15. Fresh ready L2 still short-circuits to persistent_cache and warms L1."""
    spec = normalize_query_spec(mode=MODE_ALL)
    persistent = FakePersistent({"status": "ready", "computed_through": "2026-08-28",
                                 "series_payload": payload()})
    instance = planner()
    result = instance.execute(spec=spec, prepared=PreparedEquivalenceRegistry(),
        persistent=persistent, canonical_through=lambda: "2026-08-28",
        novel_builder=lambda *_: pytest.fail("novel"))
    assert result.execution_source == "persistent_cache"
    assert instance.l1.get(
        query_fingerprint(spec), PublicationGeneration("2026-08-28")
    )["asOf"] == "2026-08-28"


def test_existing_stale_status_still_forces_full_rebuild_not_recovery():
    """16. status='stale' (historical-repair signal) is unaffected by the new
    failed-row recovery path and still forces a full rebuild."""
    spec = normalize_query_spec(mode=MODE_ALL)
    persistent = FakePersistent({"status": "stale", "computed_through": "2026-08-28",
                                 "series_payload": payload()})
    ranges = []
    result = planner().execute(spec=spec, prepared=PreparedEquivalenceRegistry(),
        persistent=persistent, canonical_through=lambda: "2026-08-28",
        novel_builder=lambda start, end: ranges.append((start, end)) or payload())
    assert ranges == [(None, "2026-08-28")]
    assert result.execution_source == "novel_interval"
