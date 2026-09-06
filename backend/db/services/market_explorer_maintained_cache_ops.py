"""Shared maintained-cache discovery/build helpers for Market Explorer.

Extracted out of ``backend/scripts/run_market_explorer_daily_publication.py``
so the authoritative daily-publication path never has to import the heavy
planner/cache machinery at all (see the P0 incident writeup referenced from
that script's module docstring: an in-process prewarm of all 21 stale
``cache_kind='maintained'`` caches drove the Oracle scraper VM to memory
saturation). This module is imported by:

  * ``backend/scripts/run_market_explorer_maintained_cache_prewarm.py`` --
    the new lean, serial, resource-guarded, lockable operational worker that
    is the ONLY thing allowed to actually build a maintained cache.
  * ``backend/scripts/run_market_explorer_daily_publication.py`` -- ONLY for
    read-only discovery (identifying which maintained caches are affected by
    a historical repair, so they can be reported as deferred / invalidated),
    never for building one.

Nothing in this module is new math: it is the same
``MarketExplorerQueryPlanner`` / ``PersistentMarketExplorerCache`` /
``run_market_explorer_query`` build path ``build_market_explorer_maintained_cache.py``
already uses, reused rather than duplicated.
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from typing import Any, Sequence

from backend.db.services.market_explorer_query_planner import (
    MarketExplorerL1Cache,
    MarketExplorerQueryPlanner,
    PersistentMarketExplorerCache,
    PreparedEquivalenceRegistry,
)
from backend.db.services.pokemon_market_explorer_query_service import (
    run_market_explorer_query,
)
from backend.domain.pokemon.market_explorer_query import query_fingerprint

LOG = logging.getLogger("market_explorer_maintained_cache_ops")

CACHE_TABLE = "pokemon_market_explorer_query_cache"
CACHE_BUILD_START = "1999-01-01"


def discover_maintained_caches(client: Any) -> list[dict[str, Any]]:
    """Every ``cache_kind='maintained'`` row, spec-driven -- never a
    hardcoded fingerprint list. A future maintained cache is picked up
    automatically the day it is promoted.
    """
    from backend.scripts.publish_market_explorer_daily_projection import _paged

    return _paged(lambda: client.table(CACHE_TABLE).select(
        "query_fingerprint,normalized_spec,status,cache_kind,computed_through,label"
    ).eq("cache_kind", "maintained"))


def caches_overlapping_set_ids(client: Any, set_ids: Sequence[str]) -> list[dict[str, Any]]:
    """Read-only: maintained caches whose ``normalized_spec.setIds`` overlaps
    ``set_ids``. Used by historical repair to report which maintained caches
    are affected (and therefore deferred to the separate operational
    worker) -- never to build anything.
    """
    scope = {str(v) for v in set_ids}
    if not scope:
        return []
    rows = discover_maintained_caches(client)
    return [
        row for row in rows
        if {str(v) for v in ((row.get("normalized_spec") or {}).get("setIds") or [])} & scope
    ]


def _spec_from_normalized(normalized_spec: dict[str, Any]) -> dict[str, Any]:
    """Rehydrate the spec dict exactly as ``normalize_query_spec`` produced it
    (this IS that dict, persisted verbatim as ``normalized_spec`` at build
    time -- see ``domain/pokemon/market_explorer_query.py``), converting list
    fields back to tuples. Must pass every field through, including
    ``contractVersion``/``asset``/etc -- selectively reconstructing a subset
    of keys silently drops fields ``query_fingerprint``/planner code expects.
    """
    return {
        **normalized_spec,
        "eraIds": tuple(normalized_spec.get("eraIds") or ()),
        "setIds": tuple(normalized_spec.get("setIds") or ()),
        "segmentIds": tuple(normalized_spec.get("segmentIds") or ()),
        "pokemonIds": tuple(normalized_spec.get("pokemonIds") or ()),
        "priceSegmentIds": tuple(normalized_spec.get("priceSegmentIds") or ()),
        "releaseAgeCohortIds": tuple(normalized_spec.get("releaseAgeCohortIds") or ()),
    }


def _builder(client: Any, spec: dict[str, Any]):
    def build(previous: str | None, through: str) -> dict[str, Any]:
        return run_market_explorer_query(
            client, mode=spec["mode"], era_ids=spec["eraIds"], set_ids=spec["setIds"],
            segment_ids=spec["segmentIds"], pokemon_ids=spec["pokemonIds"],
            price_segment_ids=spec["priceSegmentIds"],
            release_age_cohort_ids=spec["releaseAgeCohortIds"], top_n=spec["topN"],
            start_date=previous or CACHE_BUILD_START, end_date=through)
    return build


@dataclass
class CacheAdvanceReport:
    fingerprint: str
    label: str
    status: str  # "advanced" | "already_current" | "failed"
    execution_source: str | None = None
    computed_through: str | None = None
    error: str | None = None


def advance_one_maintained_cache(client: Any, row: dict[str, Any], *,
                                  market_date: str, commit: bool) -> CacheAdvanceReport:
    """Build/advance exactly ONE maintained cache row to ``market_date``
    through the real planner/persistent-cache path. Callers (the operational
    worker) are responsible for serial execution, resource guards, and the
    per-invocation build limit -- this function performs one build and
    returns.
    """
    label = str(row.get("label") or row.get("query_fingerprint") or "?")
    fingerprint = str(row.get("query_fingerprint") or "")
    # A row can have computed_through already at/beyond market_date while
    # still status='failed' -- e.g. a prior attempt updated the watermark
    # but never completed a successful publish. Only a genuinely ready row
    # at/beyond the target date is truly "already current"; a failed row
    # must still go through planner.execute() so it can attempt recovery
    # (or correctly remain failed if not recoverable), never silently
    # treated as done.
    if (row.get("status") == "ready"
            and str(row.get("computed_through") or "")[:10] >= market_date):
        return CacheAdvanceReport(fingerprint=fingerprint, label=label,
                                  status="already_current",
                                  computed_through=str(row.get("computed_through"))[:10])
    if not commit:
        return CacheAdvanceReport(fingerprint=fingerprint, label=label,
                                  status="advanced", computed_through=market_date)

    spec = _spec_from_normalized(row.get("normalized_spec") or {})
    planner = MarketExplorerQueryPlanner(l1=MarketExplorerL1Cache())
    persistent = PersistentMarketExplorerCache(client, build_lease_seconds=300)
    result = planner.execute(
        spec=spec, prepared=PreparedEquivalenceRegistry(), persistent=persistent,
        canonical_through=lambda: market_date, novel_builder=_builder(client, spec),
    )
    computed_fingerprint = query_fingerprint(spec)
    return CacheAdvanceReport(fingerprint=computed_fingerprint, label=label,
                              status="advanced", execution_source=result.execution_source,
                              computed_through=market_date)


def prewarm_maintained_caches(client: Any, *, market_date: str, commit: bool,
                               only_set_ids: Sequence[str] = ()) -> dict[str, Any]:
    """Advance EVERY discovered maintained cache to ``market_date`` in one
    process, unbounded.

    NOT used by the daily-publication path any more (that is the root cause
    of the P0 memory incident this module's extraction fixes) and NOT used
    by historical repair's automatic path either. Retained for the rare
    operator scenario of an explicit, deliberate bulk rebuild (e.g. from a
    REPL or a one-off script), and for existing lower-level tests -- one
    failed cache never blocks another; each build is isolated in its own
    try/except and reported individually.
    """
    rows = discover_maintained_caches(client)
    scope_filter = set(str(v) for v in only_set_ids)
    attempted: list[dict[str, Any]] = []
    advanced = 0
    already_current = 0
    failed = 0
    for row in rows:
        spec_set_ids = {str(v) for v in ((row.get("normalized_spec") or {}).get("setIds") or [])}
        if scope_filter and not (spec_set_ids & scope_filter):
            continue
        try:
            report = advance_one_maintained_cache(client, row, market_date=market_date, commit=commit)
        except Exception as exc:  # noqa: BLE001 - isolated per cache, never fatal to the run
            failed += 1
            attempted.append(asdict(CacheAdvanceReport(
                fingerprint=str(row.get("query_fingerprint") or ""),
                label=str(row.get("label") or row.get("query_fingerprint") or "?"),
                status="failed", error=str(exc),
            )))
            LOG.error(json.dumps({
                "event": "maintained_cache_failed",
                "fingerprint": row.get("query_fingerprint"), "error": str(exc),
            }, sort_keys=True))
            continue
        if report.status == "advanced":
            advanced += 1
        elif report.status == "already_current":
            already_current += 1
        attempted.append(asdict(report))

    return {
        "attempted": len(attempted), "advanced": advanced,
        "already_current": already_current, "failed": failed, "reports": attempted,
    }
