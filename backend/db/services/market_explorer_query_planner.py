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
CLAIM_RPC = "claim_pokemon_market_explorer_query_cache_build"
PUBLISH_RPC = "publish_pokemon_market_explorer_query_cache_build"
FAIL_RPC = "fail_pokemon_market_explorer_query_cache_build"
INVALIDATE_RPC = "invalidate_pokemon_market_explorer_query_cache"

L1_TTL_SECONDS = 300
L1_MAX_ENTRIES = 128
BUILD_LEASE_SECONDS = 30
FOLLOWER_READ_ATTEMPTS = 2
FOLLOWER_WAIT_SECONDS = 0.05


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
        self._entries: OrderedDict[str, tuple[float, dict[str, Any]]] = OrderedDict()

    def get(self, fingerprint: str) -> dict[str, Any] | None:
        entry = self._entries.get(fingerprint)
        if not entry:
            return None
        if entry[0] <= self.clock():
            self._entries.pop(fingerprint, None)
            return None
        self._entries.move_to_end(fingerprint)
        return copy.deepcopy(entry[1])

    def put(self, fingerprint: str, payload: Mapping[str, Any]) -> None:
        self._entries[fingerprint] = (
            self.clock() + self.ttl_seconds, copy.deepcopy(dict(payload)),
        )
        self._entries.move_to_end(fingerprint)
        while len(self._entries) > self.capacity:
            self._entries.popitem(last=False)

    def clear(self) -> None:
        self._entries.clear()


class PersistentMarketExplorerCache:
    """Thin service-role repository over the deployment-pending L2 schema."""

    def __init__(self, client: Any, *, metrics: PlannerMetrics | None = None) -> None:
        self.client = client
        self.metrics = metrics

    def read(self, fingerprint: str) -> dict[str, Any] | None:
        try:
            rows = list((self.client.table(CACHE_TABLE).select(
                "query_fingerprint,status,computed_from,computed_through,series_payload,"
                "build_token,build_expires_at"
            )
                         .eq("query_fingerprint", fingerprint).limit(1).execute()).data or [])
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
                "p_lease_seconds": BUILD_LEASE_SECONDS,
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
                "p_series_payload": dict(payload),
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


class MarketExplorerQueryPlanner:
    def __init__(self, *, l1: MarketExplorerL1Cache | None = None,
                 metrics: PlannerMetrics | None = None,
                 sleep: Callable[[float], None] = time.sleep) -> None:
        self.l1 = l1 or MarketExplorerL1Cache()
        self.metrics = metrics or PlannerMetrics()
        self.sleep = sleep

    def _done(self, started: float, source: str, payload: Mapping[str, Any]) -> PlannerResult:
        elapsed = (time.perf_counter() - started) * 1000
        self.metrics.record(source, elapsed)
        logger.info("market_explorer_planner source=%s elapsedMs=%.3f", source, elapsed)
        return PlannerResult(copy.deepcopy(dict(payload)), source, elapsed)

    def execute(
        self,
        *,
        spec: Mapping[str, Any],
        prepared: PreparedEquivalenceRegistry,
        persistent: PersistentMarketExplorerCache,
        canonical_through: Callable[[], str],
        novel_builder: Callable[[str | None, str], dict[str, Any]],
    ) -> PlannerResult:
        started = time.perf_counter()
        fingerprint = query_fingerprint(spec)

        prepared_payload = prepared.resolve(spec)
        if prepared_payload is not None:
            return self._done(started, "prepared", prepared_payload)

        hot = self.l1.get(fingerprint)
        if hot is not None:
            return self._done(started, "memory_cache", hot)

        through = str(canonical_through())[:10]
        row = persistent.read(fingerprint)
        if row and row.get("status") == "ready" and str(row.get("computed_through"))[:10] == through:
            payload = dict(row.get("series_payload") or {})
            self.l1.put(fingerprint, payload)
            return self._done(started, "persistent_cache", payload)

        token = str(uuid4())
        won = persistent.claim(fingerprint=fingerprint, spec=spec, token=token)
        if won is False:
            self.metrics.record("build_contention", 0)
            for _ in range(FOLLOWER_READ_ATTEMPTS):
                self.sleep(FOLLOWER_WAIT_SECONDS)
                follower = persistent.read(fingerprint)
                if (follower and follower.get("status") == "ready"
                        and str(follower.get("computed_through"))[:10] == through):
                    payload = dict(follower.get("series_payload") or {})
                    self.l1.put(fingerprint, payload)
                    return self._done(started, "persistent_cache", payload)

            raise MarketExplorerBuildInProgress(
                "an equivalent Market Explorer query is already being built"
            )

        # status=stale is the historical-repair signal and must rebuild from
        # source. A normal forward publication leaves the prior row ready but
        # behind the canonical watermark, which is safe to append.
        previous = (
            str(row.get("computed_through"))[:10]
            if row and row.get("status") == "ready" and row.get("series_payload") else None
        )
        try:
            delta = novel_builder(previous, through)
            if previous and previous < through and row:
                payload = merge_incremental_result(row.get("series_payload") or {}, delta)
                source = "cache_incremental"
            else:
                payload = delta
                source = "novel_interval"
            if won is True and not persistent.publish(fingerprint=fingerprint, token=token, payload=payload):
                self.metrics.record("cache_build_failures", 0)
            self.l1.put(fingerprint, payload)
            return self._done(started, source, payload)
        except Exception:
            if won is True:
                persistent.fail(fingerprint=fingerprint, token=token)
            raise


GLOBAL_MARKET_EXPLORER_PLANNER = MarketExplorerQueryPlanner()
GLOBAL_PREPARED_EQUIVALENCE_REGISTRY = PreparedEquivalenceRegistry()


def resolve_canonical_through(client: Any, spec: Mapping[str, Any]) -> str:
    """Resolve the semantic publication watermark only after prepared/L1 miss."""
    if spec["asset"] == "cards":
        from backend.db.services.pokemon_market_explorer_query_service import (
            resolve_scope_history_bounds,
            resolve_scope_set_ids,
        )
        set_ids = resolve_scope_set_ids(
            client, era_ids=spec["eraIds"], set_ids=spec["setIds"],
        )
        _, through = resolve_scope_history_bounds(client, set_ids)
        if not through:
            raise RuntimeError("card market publication has no usable date")
        return str(through)[:10]

    from backend.db.services.pokemon_global_sealed_market_service import (
        read_global_sealed_source_snapshots,
    )
    from backend.db.services.pokemon_sealed_market_explorer_query_service import (
        resolve_sealed_scope_set_ids,
    )
    set_ids = resolve_sealed_scope_set_ids(
        client, era_ids=spec["eraIds"], set_ids=spec["setIds"],
    )
    snapshots = read_global_sealed_source_snapshots(client, set_ids)
    through = max((str(row.get("market_date") or "")[:10] for row in snapshots), default="")
    if not through:
        raise RuntimeError("sealed market publication has no usable date")
    return through

# Existing prepared Cards parents/segments are canonical-card or set-aggregate
# publications, not the variant/physical-instrument contract.  No production
# loader is registered until a publisher explicitly carries the same semantic
# versions.  Sealed prepared snapshots are inputs to its novel engine, but the
# currently published overview is not the complete query response contract.
