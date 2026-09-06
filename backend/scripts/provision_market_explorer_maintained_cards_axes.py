"""Provision maintained Cards caches for the finite broad single-axis markets
exposed as normal Plus/prepared intelligence -- Screens, and any equivalent
Builder-composed market share the same identity with these once provisioned.

WHY THIS EXISTS. Prompt 8's live audit found production had 21 maintained
Cards caches -- Global All Raw, Global Top 10, and per-era/prepared
combinations -- but ZERO covering a bare rarity segment, price segment, or
release-age cohort. Every one of those is a finite, product-exposed Plus
market (a Screen or a one-click Builder selection), not a user-invented
custom query, so it belongs in the same maintained tier the era markets
already occupy. Without it, "Established" or "SIR alone" cold-builds on
every single request -- exactly the class of query Prompt 7/8 found timing
out at broad scope.

WHAT THIS DOES NOT PROVISION, ON PURPOSE. Every Pokemon (thousands of
narrow, low-traffic combinations), any compound/Premium axis combination,
and any other arbitrary user-composed query remain ordinary custom/L1/L2
cache territory -- precomputing those would be exactly the unbounded
"cache everything" mistake this script exists to avoid.

SOURCE OF TRUTH FOR "WHAT IS FINITE AND BROAD". Never a hardcoded list:
eras, rarity segments, price segments and release-age cohorts are all read
from `build_market_explorer_filter_options`, the same canonical registry
the frontend's options endpoint and the Builder/Screens UI already consume.
A future taxonomy addition or removal is picked up automatically the next
time this script runs.

IDENTITY, NOT DUPLICATION. Each candidate spec is normalized through the
exact same `normalize_query_spec`/`query_fingerprint` the Builder and every
Screen already use. If a spec's fingerprint already has ANY cache row
(built earlier by a user's own query, a Screen click, or a prior run of
this script), this script reuses and simply promotes that row to
`cache_kind='maintained'` rather than building a duplicate -- a Screen and
an equivalent hand-built Builder market were already guaranteed to
fingerprint identically (see `marketExplorerScreens.mjs`/
`normalizeQuerySpec`); this script does not change or need to change that.

Dry-run is the default-safe mode; writes require `--commit` and use only
the service-role client, matching every sibling script in this family.
"""
from __future__ import annotations

import argparse
import json
import logging
from dataclasses import asdict, dataclass, field
from typing import Any

from backend.db.clients.supabase_client import create_service_role_client
from backend.db.services.market_explorer_query_planner import (
    MarketExplorerL1Cache,
    MarketExplorerQueryPlanner,
    PersistentMarketExplorerCache,
    PreparedEquivalenceRegistry,
    resolve_canonical_through,
)
from backend.db.services.pokemon_market_explorer_query_service import (
    ASSET_CARDS,
    build_market_explorer_filter_options,
    run_market_explorer_query,
)
from backend.domain.pokemon.market_explorer_query import (
    MODE_ALL,
    normalize_query_spec,
    query_fingerprint,
)

LOG = logging.getLogger("market_explorer_maintained_axes_provision")

CACHE_TABLE = "pokemon_market_explorer_query_cache"
BUILD_START = "1999-01-01"


@dataclass
class AxisReport:
    label: str
    spec_kind: str  # "era" | "rarity_segment" | "price_segment" | "release_age"
    fingerprint: str
    already_maintained: bool = False
    built: bool = False
    promoted: bool = False
    execution_source: str | None = None
    error: str | None = None


@dataclass
class ProvisionSummary:
    dry_run: bool
    candidates_considered: int = 0
    already_maintained: int = 0
    built: int = 0
    promoted: int = 0
    failures: int = 0
    reports: list[dict[str, Any]] = field(default_factory=list)


def discover_candidate_specs(client: Any) -> list[tuple[str, str, dict[str, Any]]]:
    """(label, spec_kind, normalized_spec) for every finite broad single-axis
    Cards market -- read entirely from the canonical options registry, never
    a hardcoded list. Global All Raw / Global Top 10 are intentionally NOT
    re-listed here; they are already provisioned and this script's job is
    additive coverage, not re-deriving what already exists.
    """
    options = build_market_explorer_filter_options(client)
    candidates: list[tuple[str, str, dict[str, Any]]] = []

    for era in options.get("eras") or []:
        era_id = str(era.get("id") or "")
        if not era_id:
            continue
        spec = normalize_query_spec(asset=ASSET_CARDS, mode=MODE_ALL, era_ids=[era_id])
        candidates.append((f"era:{era.get('label')}", "era", spec))

    segments = ((options.get("cardSegments") or options.get("segments") or {}).get("segments") or [])
    for segment in segments:
        key = str(segment.get("key") or "")
        if not key:
            continue
        spec = normalize_query_spec(asset=ASSET_CARDS, mode=MODE_ALL, segment_ids=[key])
        candidates.append((f"rarity:{segment.get('label')}", "rarity_segment", spec))

    for price_segment in (options.get("priceSegments") or {}).get(ASSET_CARDS) or []:
        segment_id = str(price_segment.get("id") or "")
        if not segment_id:
            continue
        spec = normalize_query_spec(asset=ASSET_CARDS, mode=MODE_ALL, price_segment_ids=[segment_id])
        candidates.append((f"price:{price_segment.get('label')}", "price_segment", spec))

    for cohort in options.get("releaseAgeCohorts") or []:
        cohort_id = str(cohort.get("id") or "")
        if not cohort_id:
            continue
        spec = normalize_query_spec(asset=ASSET_CARDS, mode=MODE_ALL, release_age_cohort_ids=[cohort_id])
        candidates.append((f"releaseAge:{cohort.get('label')}", "release_age", spec))

    return candidates


def load_existing_cache_row(client: Any, fingerprint: str) -> dict[str, Any] | None:
    rows = list((client.table(CACHE_TABLE)
                 .select("query_fingerprint,status,cache_kind,computed_through")
                 .eq("query_fingerprint", fingerprint).limit(1).execute()).data or [])
    return dict(rows[0]) if rows else None


def promote_to_maintained(client: Any, fingerprint: str) -> None:
    (client.table(CACHE_TABLE).update({"cache_kind": "maintained"})
     .eq("query_fingerprint", fingerprint).eq("status", "ready").execute())


def build_market(client: Any, spec: dict[str, Any]):
    def build(previous_through: str | None, canonical_date: str) -> dict[str, Any]:
        return run_market_explorer_query(
            client, mode=spec["mode"], era_ids=spec["eraIds"], set_ids=spec["setIds"],
            segment_ids=spec["segmentIds"], pokemon_ids=spec["pokemonIds"],
            price_segment_ids=spec["priceSegmentIds"],
            release_age_cohort_ids=spec["releaseAgeCohortIds"], top_n=spec["topN"],
            start_date=previous_through or BUILD_START, end_date=canonical_date,
        )
    return build


def provision_one(client: Any, *, commit: bool, label: str, spec_kind: str,
                   spec: dict[str, Any]) -> AxisReport:
    fingerprint = query_fingerprint(spec)
    report = AxisReport(label=label, spec_kind=spec_kind, fingerprint=fingerprint)
    existing = load_existing_cache_row(client, fingerprint)
    if existing and existing.get("cache_kind") == "maintained":
        report.already_maintained = True
        return report

    if not commit:
        return report

    planner = MarketExplorerQueryPlanner(l1=MarketExplorerL1Cache())
    persistent = PersistentMarketExplorerCache(client)
    try:
        result = planner.execute(
            spec=spec, prepared=PreparedEquivalenceRegistry(), persistent=persistent,
            canonical_through=lambda: resolve_canonical_through(client, spec),
            novel_builder=build_market(client, spec),
        )
        report.execution_source = result.execution_source
        report.built = True
    except Exception as exc:  # noqa: BLE001 - isolated per candidate, never fatal to the run
        report.error = str(exc)
        LOG.error(json.dumps({
            "event": "axis_provision_build_failed", "label": label, "fingerprint": fingerprint[:12],
            "error": type(exc).__name__,
        }, sort_keys=True))
        return report

    promote_to_maintained(client, fingerprint)
    report.promoted = True
    return report


def run_provision(client: Any, *, commit: bool) -> dict[str, Any]:
    summary = ProvisionSummary(dry_run=not commit)
    candidates = discover_candidate_specs(client)
    summary.candidates_considered = len(candidates)
    for label, spec_kind, spec in candidates:
        report = provision_one(client, commit=commit, label=label, spec_kind=spec_kind, spec=spec)
        if report.already_maintained:
            summary.already_maintained += 1
        if report.built:
            summary.built += 1
        if report.promoted:
            summary.promoted += 1
        if report.error:
            summary.failures += 1
        summary.reports.append(asdict(report))
        LOG.info(json.dumps({
            "event": "axis_complete", "label": label, "alreadyMaintained": report.already_maintained,
            "promoted": report.promoted, "error": report.error,
        }, sort_keys=True))
    return asdict(summary)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="List candidates; perform no writes.")
    mode.add_argument("--commit", action="store_true", help="Build and promote via the service-role client.")
    return parser


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = build_parser().parse_args()
    report = run_provision(create_service_role_client(), commit=bool(args.commit))
    print(json.dumps(report, indent=2, sort_keys=True, default=str))
    return 1 if report["failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
