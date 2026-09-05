"""Terminal Market Explorer planner shared by Cards and Sealed.

Entitlements deliberately do not live here.  The HTTP boundary authenticates,
normalizes, and authorizes before calling this module; keeping the planner
backend-only prevents a cached Premium result from becoming an authorization
decision.
"""

from __future__ import annotations

import copy
import logging
import time
from collections import Counter, OrderedDict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Mapping
from uuid import uuid4

from backend.domain.pokemon.market_explorer_query import (
    MARKET_EXPLORER_INSTRUMENT_METHODOLOGY_VERSIONS,
    MARKET_EXPLORER_QUERY_CONTRACT_VERSION,
    MARKET_EXPLORER_SERVICE_VERSIONS,
    query_fingerprint,
)
from backend.domain.pokemon.market_index import compute_strict_window_movements

logger = logging.getLogger(__name__)

CACHE_TABLE = "pokemon_market_explorer_query_cache"
SUMMARY_READ_RPC = "get_pokemon_market_explorer_query_cache_summary"
CONSTITUENT_PAGE_RPC = "get_pokemon_market_explorer_query_cache_constituent_page"
CLAIM_RPC = "claim_pokemon_market_explorer_query_cache_build"
PUBLISH_RPC = "publish_pokemon_market_explorer_query_cache_build"
FAIL_RPC = "fail_pokemon_market_explorer_query_cache_build"
INVALIDATE_RPC = "invalidate_pokemon_market_explorer_query_cache"

L1_TTL_SECONDS = 300
L1_MAX_ENTRIES = 128
BUILD_LEASE_SECONDS = 30
FOLLOWER_READ_ATTEMPTS = 2
FOLLOWER_WAIT_SECONDS = 0.05
PUBLICATION_WATERMARK_TTL_SECONDS = 2.0


def json_spec(spec: Mapping[str, Any]) -> dict[str, Any]:
    """Convert the already-normalized tuple form to stable JSON values."""
    return {
        key: list(value) if isinstance(value, tuple) else value
        for key, value in spec.items()
    }


@dataclass(frozen=True)
class PlannerResult:
    payload: dict[str, Any]
    execution_source: str
    elapsed_ms: float


class MarketExplorerBuildInProgress(RuntimeError):
    """Another worker owns the bounded build lease and has not published yet."""


class MarketExplorerPublishFailed(RuntimeError):
    """The persistent cache write did not commit; the build must not report success."""


@dataclass(frozen=True)
class PublicationGeneration:
    canonical_through: str
    repair_generation: int | None = 0

    @property
    def trusted(self) -> bool:
        return self.repair_generation is not None

    @property
    def token(self) -> str:
        if not self.trusted:
            raise ValueError("unknown repair generation has no L1 cache identity")
        return f"{str(self.canonical_through)[:10]}:r{int(self.repair_generation)}"


def publication_scope_key(spec: Mapping[str, Any]) -> tuple[Any, ...]:
    """Only fields that can change the owning publication watermark."""
    return (
        str(spec["asset"]), tuple(spec.get("eraIds") or ()), tuple(spec.get("setIds") or ()),
    )


class PublicationWatermarkCache:
    """Tiny bounded cache for publication metadata, never market results."""

    def __init__(self, *, ttl_seconds: float = PUBLICATION_WATERMARK_TTL_SECONDS,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self.ttl_seconds = float(ttl_seconds)
        self.clock = clock
        self._entries: dict[tuple[Any, ...], tuple[float, PublicationGeneration]] = {}

    def resolve(self, scope_key: tuple[Any, ...],
                loader: Callable[[], PublicationGeneration]) -> PublicationGeneration:
        cached = self._entries.get(scope_key)
        now = self.clock()
        if cached and cached[0] > now:
            return cached[1]
        generation = loader()
        # A failed state-table read must be retried on the next request. Treating
        # unknown as generation zero could resurrect a pre-repair L1 entry.
        if generation.trusted:
            self._entries[scope_key] = (now + self.ttl_seconds, generation)
        return generation

    def clear(self) -> None:
        self._entries.clear()


class PlannerMetrics:
    """Process-local counters suitable for logs/metrics export, never clients."""

    def __init__(self) -> None:
        self.counts: Counter[str] = Counter()
        self.wall_ms: Counter[str] = Counter()

    def record(self, source: str, elapsed_ms: float) -> None:
        self.counts[source] += 1
        self.wall_ms[source] += float(elapsed_ms)


class MarketExplorerL1Cache:
    def __init__(self, *, ttl_seconds: int = L1_TTL_SECONDS, capacity: int = L1_MAX_ENTRIES,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self.ttl_seconds = ttl_seconds
        self.capacity = capacity
        self.clock = clock
        self._entries: OrderedDict[tuple[str, str], tuple[float, dict[str, Any]]] = OrderedDict()

    @staticmethod
    def _key(fingerprint: str, generation: PublicationGeneration) -> tuple[str, str]:
        return fingerprint, generation.token

    def get(self, fingerprint: str, generation: PublicationGeneration) -> dict[str, Any] | None:
        key = self._key(fingerprint, generation)
        entry = self._entries.get(key)
        if not entry:
            return None
        if entry[0] <= self.clock():
            self._entries.pop(key, None)
            return None
        self._entries.move_to_end(key)
        # Cache entries are owned snapshots: put() copies once before storing,
        # and planner/API consumers treat result payloads as immutable. A deep
        # copy on every hit traversed multi-megabyte constituent payloads twice
        # (here and in _done), turning an in-process lookup into ~100 ms work.
        return entry[1]

    def put(self, fingerprint: str, generation: PublicationGeneration,
            payload: Mapping[str, Any]) -> None:
        key = self._key(fingerprint, generation)
        self._entries[key] = (
            self.clock() + self.ttl_seconds, copy.deepcopy(dict(payload)),
        )
        self._entries.move_to_end(key)
        while len(self._entries) > self.capacity:
            self._entries.popitem(last=False)

    def clear(self) -> None:
        self._entries.clear()


class PersistentMarketExplorerCache:
    """Thin service-role repository over the deployment-pending L2 schema."""

    def __init__(self, client: Any, *, metrics: PlannerMetrics | None = None,
                 build_lease_seconds: int = BUILD_LEASE_SECONDS) -> None:
        if build_lease_seconds < 1 or build_lease_seconds > 300:
            raise ValueError("build_lease_seconds must be between 1 and 300")
        self.client = client
        self.metrics = metrics
        self.build_lease_seconds = int(build_lease_seconds)

    def read(self, fingerprint: str, *, summary: bool = False) -> dict[str, Any] | None:
        try:
            if summary:
                rows = list(self.client.rpc(SUMMARY_READ_RPC, {
                    "p_query_fingerprint": fingerprint,
                }).execute().data or [])
            else:
                rows = list((self.client.table(CACHE_TABLE).select(
                    "query_fingerprint,status,computed_from,computed_through,series_payload,"
                    "current_constituents,build_token,build_expires_at,"
                    "query_contract_version,service_version,instrument_methodology_version"
                ).eq("query_fingerprint", fingerprint).limit(1).execute()).data or [])
                if rows and rows[0].get("status") == "ready":
                    payload = dict(rows[0].get("series_payload") or {})
                    payload["currentConstituents"] = list(rows[0].get("current_constituents") or [])
                    rows[0]["series_payload"] = payload
            return dict(rows[0]) if rows else None
        except Exception as exc:  # migration is intentionally not deployed yet
            if self.metrics:
                self.metrics.record("cache_read_failures", 0)
            logger.warning("market_explorer_cache_read_failed fingerprint=%s error=%s",
                           fingerprint[:12], type(exc).__name__)
            return None

    def claim(self, *, fingerprint: str, spec: Mapping[str, Any], token: str) -> bool | None:
        asset = str(spec["asset"])
        try:
            response = self.client.rpc(CLAIM_RPC, {
                "p_query_fingerprint": fingerprint,
                "p_query_contract_version": MARKET_EXPLORER_QUERY_CONTRACT_VERSION,
                "p_service_version": MARKET_EXPLORER_SERVICE_VERSIONS[asset],
                "p_instrument_methodology_version":
                    MARKET_EXPLORER_INSTRUMENT_METHODOLOGY_VERSIONS[asset],
                "p_asset": asset,
                "p_normalized_spec": json_spec(spec),
                "p_build_token": token,
                "p_lease_seconds": self.build_lease_seconds,
            }).execute()
            return bool(response.data)
        except Exception as exc:
            if self.metrics:
                self.metrics.record("cache_build_failures", 0)
            logger.warning("market_explorer_cache_claim_failed fingerprint=%s error=%s",
                           fingerprint[:12], type(exc).__name__)
            return None

    def publish(self, *, fingerprint: str, token: str, payload: Mapping[str, Any]) -> bool:
        try:
            response = self.client.rpc(PUBLISH_RPC, {
                "p_query_fingerprint": fingerprint,
                "p_build_token": token,
                "p_computed_from": payload.get("historyStartDate"),
                "p_computed_through": payload.get("asOf"),
                "p_series_payload": {
                    key: value for key, value in payload.items()
                    if key != "currentConstituents"
                },
                "p_current_value": payload.get("indexValue"),
                "p_constituent_count": (payload.get("metadata") or {}).get("constituentCount"),
                "p_eligible_universe_count":
                    (payload.get("reconciliation") or {}).get("eligibleUniverseCount"),
                "p_current_constituents": payload.get("currentConstituents") or [],
            }).execute()
            return bool(response.data)
        except Exception as exc:
            if self.metrics:
                self.metrics.record("cache_build_failures", 0)
            logger.warning("market_explorer_cache_publish_failed fingerprint=%s error=%s",
                           fingerprint[:12], type(exc).__name__)
            return False

    def constituent_page(self, fingerprint: str, *, limit: int = 100,
                         after_rank: int = 0) -> dict[str, Any] | None:
        if limit < 1 or limit > 100:
            raise ValueError("limit must be between 1 and 100")
        rows = list(self.client.rpc(CONSTITUENT_PAGE_RPC, {
            "p_query_fingerprint": fingerprint,
            "p_limit": limit,
            "p_after_rank": max(0, int(after_rank)),
        }).execute().data or [])
        return dict(rows[0]) if rows else None

    def fail(self, *, fingerprint: str, token: str) -> None:
        try:
            self.client.rpc(FAIL_RPC, {
                "p_query_fingerprint": fingerprint, "p_build_token": token,
            }).execute()
        except Exception:
            logger.warning("market_explorer_cache_failure_release_failed fingerprint=%s",
                           fingerprint[:12])

    def invalidate(self, *, changed_market_date: str | None = None) -> int:
        response = self.client.rpc(INVALIDATE_RPC, {
            "p_changed_market_date": changed_market_date,
        }).execute()
        return int(response.data or 0)

    def repair_generation(self, asset: str) -> int | None:
        """Cross-worker generation; unknown fails closed by bypassing process L1."""
        try:
            rows = list((self.client.table("pokemon_market_explorer_cache_state")
                         .select("repair_generation").eq("asset", str(asset))
                         .limit(1).execute()).data or [])
            if not rows or rows[0].get("repair_generation") is None:
                return None
            return int(rows[0]["repair_generation"])
        except Exception as exc:
            if self.metrics:
                self.metrics.record("cache_read_failures", 0)
            logger.warning("market_explorer_repair_generation_read_failed asset=%s error=%s",
                           asset, type(exc).__name__)
            return None


class PreparedEquivalenceRegistry:
    """Exact semantic registry; incompatible legacy publications fail closed."""

    def __init__(self) -> None:
        self._loaders: dict[str, Callable[[], dict[str, Any]]] = {}

    def register(self, spec: Mapping[str, Any], loader: Callable[[], dict[str, Any]]) -> None:
        self._loaders[query_fingerprint(spec)] = loader

    def resolve(self, spec: Mapping[str, Any]) -> dict[str, Any] | None:
        loader = self._loaders.get(query_fingerprint(spec))
        return copy.deepcopy(loader()) if loader else None


def merge_incremental_result(cached: Mapping[str, Any], delta: Mapping[str, Any]) -> dict[str, Any]:
    """Append a [previous-through, newest] result without resetting its index."""
    result = copy.deepcopy(dict(cached))
    old_trend = list(cached.get("trend") or [])
    new_trend = list(delta.get("trend") or [])
    if not old_trend or not new_trend:
        return copy.deepcopy(dict(delta))
    anchor_date = str(cached.get("asOf") or old_trend[-1][0])[:10]
    old_anchor = next((float(row[1]) for row in old_trend if str(row[0])[:10] == anchor_date), None)
    new_anchor = next((float(row[1]) for row in new_trend if str(row[0])[:10] == anchor_date), None)
    if old_anchor is None or new_anchor in (None, 0):
        return copy.deepcopy(dict(delta))
    scale = old_anchor / new_anchor
    appended = [[row[0], float(row[1]) * scale] for row in new_trend
                if str(row[0])[:10] > anchor_date]
    result.update(copy.deepcopy(dict(delta)))
    result["trend"] = old_trend + appended
    result["indexValue"] = float(result["trend"][-1][1])
    result["familyChanges"] = compute_strict_window_movements([
        {"date": row[0], "value": row[1]} for row in result["trend"]
    ])

    old_tracked = list(cached.get("trackedValueHistory") or [])
    result["trackedValueHistory"] = old_tracked + [copy.deepcopy(row) for row in
        (delta.get("trackedValueHistory") or []) if str(row.get("date"))[:10] > anchor_date]
    result["trackedValueChanges"] = compute_strict_window_movements([
        {"date": row.get("date"), "value": row.get("value")}
        for row in result["trackedValueHistory"]
    ])
    result["historyStartDate"] = cached.get("historyStartDate") or result.get("historyStartDate")
    metadata = dict(result.get("metadata") or {})
    metadata["historyPointCount"] = len(result["trend"])
    metadata["observationCount"] = len(result["trend"])
    result["metadata"] = metadata
    scope = dict(result.get("scope") or {})
    scope["startDate"] = result["historyStartDate"]
    scope["endDate"] = result.get("asOf")
    result["scope"] = scope
    return result


def _is_recoverable_failed_base(
    row: Mapping[str, Any] | None,
    spec: Mapping[str, Any],
    generation: PublicationGeneration,
) -> bool:
    """A ``status='failed'`` row usable ONLY as an incremental build base.

    Never makes a failed row servable as a cache hit -- see the ``status ==
    'ready'`` gate in ``execute()``, which this helper does not touch. A
    failed row qualifies as a last-good build base when its persisted
    payload is real, its versions are compatible with the currently
    requested spec, and it is not stale relative to the latest known
    repair generation (an unknown/untrusted generation fails closed, the
    same posture the rest of this module takes for repair freshness).
    """
    if not row or row.get("status") != "failed":
        return False
    if not generation.trusted:
        return False
    if not row.get("computed_through"):
        return False
    series_payload = row.get("series_payload")
    if not series_payload or not series_payload.get("trend"):
        return False
    asset = str(spec["asset"])
    if row.get("query_contract_version") not in (None, MARKET_EXPLORER_QUERY_CONTRACT_VERSION):
        return False
    if row.get("service_version") not in (None, MARKET_EXPLORER_SERVICE_VERSIONS.get(asset)):
        return False
    if row.get("instrument_methodology_version") not in (
            None, MARKET_EXPLORER_INSTRUMENT_METHODOLOGY_VERSIONS.get(asset)):
        return False
    # No active competing build lease: a genuinely failed row always has its
    # lease columns cleared by fail_pokemon_market_explorer_query_cache_build,
    # so any non-null token here means another worker currently owns it.
    if row.get("build_token") or row.get("build_expires_at"):
        return False
    return True


class MarketExplorerQueryPlanner:
    def __init__(self, *, l1: MarketExplorerL1Cache | None = None,
                 metrics: PlannerMetrics | None = None,
                 watermarks: PublicationWatermarkCache | None = None,
                 sleep: Callable[[float], None] = time.sleep) -> None:
        self.l1 = l1 or MarketExplorerL1Cache()
        self.metrics = metrics or PlannerMetrics()
        self.watermarks = watermarks or PublicationWatermarkCache()
        self.sleep = sleep

    def _done(self, started: float, source: str, payload: Mapping[str, Any]) -> PlannerResult:
        elapsed = (time.perf_counter() - started) * 1000
        self.metrics.record(source, elapsed)
        logger.info("market_explorer_planner source=%s elapsedMs=%.3f", source, elapsed)
        # Nested Market Explorer payloads are immutable after construction.
        # Preserve a distinct top-level mapping without recursively copying a
        # 3+ MB cached result on every request.
        return PlannerResult(dict(payload), source, elapsed)

    def execute(
        self,
        *,
        spec: Mapping[str, Any],
        prepared: PreparedEquivalenceRegistry,
        persistent: PersistentMarketExplorerCache,
        canonical_through: Callable[[], str],
        novel_builder: Callable[[str | None, str], dict[str, Any]],
        summary: bool = False,
    ) -> PlannerResult:
        started = time.perf_counter()
        fingerprint = query_fingerprint(spec)
        l1_key = f"{fingerprint}:summary" if summary else fingerprint

        def response(payload: Mapping[str, Any]) -> dict[str, Any]:
            if not summary:
                return dict(payload)
            return {key: value for key, value in payload.items()
                    if key not in ("currentConstituents", "membershipByDate")}

        def read_cache(*, full: bool = False) -> dict[str, Any] | None:
            return (persistent.read(fingerprint, summary=True)
                    if summary and not full else persistent.read(fingerprint))

        prepared_payload = prepared.resolve(spec)
        if prepared_payload is not None:
            return self._done(started, "prepared", prepared_payload)

        generation = self.watermarks.resolve(
            publication_scope_key(spec),
            lambda: PublicationGeneration(
                canonical_through=str(canonical_through())[:10],
                repair_generation=persistent.repair_generation(str(spec["asset"])),
            ),
        )
        through = generation.canonical_through

        if generation.trusted:
            hot = self.l1.get(l1_key, generation)
            if hot is not None:
                return self._done(started, "memory_cache", hot)

        row = read_cache()
        if row and row.get("status") == "ready" and str(row.get("computed_through"))[:10] == through:
            payload = dict(row.get("series_payload") or {})
            if generation.trusted:
                self.l1.put(l1_key, generation, payload)
            return self._done(started, "persistent_cache", payload)

        token = str(uuid4())
        won = persistent.claim(fingerprint=fingerprint, spec=spec, token=token)
        if won is False:
            self.metrics.record("build_contention", 0)
            for _ in range(FOLLOWER_READ_ATTEMPTS):
                self.sleep(FOLLOWER_WAIT_SECONDS)
                follower = read_cache()
                if (follower and follower.get("status") == "ready"
                        and str(follower.get("computed_through"))[:10] == through):
                    payload = dict(follower.get("series_payload") or {})
                    if generation.trusted:
                        self.l1.put(l1_key, generation, payload)
                    return self._done(started, "persistent_cache", payload)

            raise MarketExplorerBuildInProgress(
                "an equivalent Market Explorer query is already being built"
            )

        # status=stale is the historical-repair signal and must rebuild from
        # source. A normal forward publication leaves the prior row ready but
        # behind the canonical watermark, which is safe to append. A
        # status=failed row whose payload/versions/generation are still
        # trustworthy (see _is_recoverable_failed_base) is likewise a safe
        # incremental base -- it is never returned as a cache hit above, only
        # used here to avoid an unnecessary full historical cold rebuild.
        build_row = read_cache(full=True) if summary else row
        recoverable_failed_base = _is_recoverable_failed_base(build_row, spec, generation)
        previous = (
            str(build_row.get("computed_through"))[:10]
            if build_row and build_row.get("series_payload")
            and (build_row.get("status") == "ready" or recoverable_failed_base) else None
        )
        try:
            delta = novel_builder(previous, through)
            engine = (delta.get("diagnostics") or {}).get("executionEngine")
            if previous and previous < through and build_row:
                payload = merge_incremental_result(build_row.get("series_payload") or {}, delta)
                source = f"cache_incremental_{engine}" if engine else "cache_incremental"
            else:
                payload = delta
                source = str(engine or "novel_interval")
            if won is True and not persistent.publish(fingerprint=fingerprint, token=token, payload=payload):
                self.metrics.record("cache_build_failures", 0)
                raise MarketExplorerPublishFailed(
                    f"market_explorer_cache_publish_returned_false fingerprint={fingerprint[:12]}"
                )
            if generation.trusted:
                self.l1.put(l1_key, generation, response(payload))
            return self._done(started, source, response(payload))
        except Exception:
            if won is True:
                persistent.fail(fingerprint=fingerprint, token=token)
            raise


GLOBAL_MARKET_EXPLORER_PLANNER = MarketExplorerQueryPlanner()
GLOBAL_PREPARED_EQUIVALENCE_REGISTRY = PreparedEquivalenceRegistry()


def resolve_cards_canonical_through(
    client: Any, set_ids: set[str], *, through_date: str | None = None,
) -> str:
    """Latest Cards Market Explorer date, guarded by scoped history existence.

    Set Value coverage answers whether the requested scope has any history; it
    does not own Market Explorer publication freshness. The quality authority
    is the same date gate consumed by the cohort engine, preventing an
    in-progress Set Value publication from causing repeated incremental work.
    """
    coverage = (client.table("pokemon_set_value_daily_history_coverage")
                .select("set_id").eq("has_history", True))
    if set_ids:
        coverage = coverage.in_("set_id", sorted(set_ids))
    if not list(coverage.limit(1).execute().data or []):
        raise RuntimeError("cards market publication has no scoped history")

    quality = (client.table("pokemon_market_date_quality").select("market_date")
               .eq("tcg", "pokemon").in_("status", ["READY", "LEGACY_VERIFIED"]))
    if through_date:
        quality = quality.lte("market_date", str(through_date)[:10])
    rows = list(quality.order("market_date", desc=True).limit(1).execute().data or [])
    through = str(rows[0].get("market_date") or "")[:10] if rows else ""
    if not through:
        raise RuntimeError("cards market publication has no usable date")
    return through


def resolve_canonical_through(client: Any, spec: Mapping[str, Any]) -> str:
    """Narrow metadata-only publication watermark (one call for common scopes)."""
    requested_sets = {str(value) for value in (spec.get("setIds") or ())}
    era_ids = list(spec.get("eraIds") or ())
    if era_ids:
        era_rows = list((client.table("sets").select("id").in_("era_id", era_ids)
                         .execute()).data or [])
        era_sets = {str(row.get("id")) for row in era_rows if row.get("id")}
        requested_sets = requested_sets & era_sets if requested_sets else era_sets

    if spec["asset"] == "cards":
        return resolve_cards_canonical_through(client, requested_sets)
    else:
        query = client.table("pokemon_set_sealed_market_snapshot_latest").select("market_date")
        if requested_sets:
            query = query.in_("set_id", sorted(requested_sets))
        rows = list(query.order("market_date", desc=True, nullsfirst=False)
                    .limit(1).execute().data or [])
        through = str(rows[0].get("market_date") or "")[:10] if rows else ""
    if not through:
        raise RuntimeError(f"{spec['asset']} market publication has no usable date")
    return through

# Existing prepared Cards parents/segments are canonical-card or set-aggregate
# publications, not the variant/physical-instrument contract.  No production
# loader is registered until a publisher explicitly carries the same semantic
# versions.  Sealed prepared snapshots are inputs to its novel engine, but the
# currently published overview is not the complete query response contract.
