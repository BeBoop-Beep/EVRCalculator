"""Bucket 3A production builder/wrapper for Best-Open Price persistence.

Dry-run by default; ``--commit`` is required to actually publish. This
script does NOT hold a database transaction open for the ~65-minute
computation -- the singleton lock below only prevents a second concurrent
invocation (reporting ``already_running``), and the final atomic publish
(the RPC in migration 20260913220000) is a separate, short concern.

Flow:
  1. Resolve the latest V12 Full Market ranking source -> capture source
     identity (snapshot id, published_at, market_date, cohort_fingerprint,
     full_market_budget, eligible_cohort_count, model versions).
  2. Skip if a Best-Open Price snapshot is already published for that exact
     identity + method version (idempotent no-op).
  3. Run the validated cohort engine
     (``backend/scripts/research_best_open_price_bucket2.py``'s ``run``).
  4. Require every eligible product resolved, or explicitly-approved
     unavailable statuses accounted for in ``unresolved_count``.
  5. Re-read the source identity and ABORT on any drift before publishing.
  6. Build the payload (`build_snapshot_payload` / `build_row_payload`).
  7. Dry-run (default): write a local JSON report only, no DB write.
     ``--commit``: call the publication RPC.

No cron/recurring orchestration is wired by this script -- it is invoked
manually per the Bucket 3B canary plan (see
docs/research/BEST_OPEN_PRICE_BUCKET3A_PRIVATE_PERSISTENCE.md).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.calculations.evr.best_open_price import BEST_OPEN_PRICE_METHOD_VERSION
from backend.db.services.budget_product_best_open_price_service import (
    build_row_payload,
    build_snapshot_payload,
    content_fingerprint,
    load_best_open_price_ranking,
    publish_snapshot,
)
from backend.scripts.run_market_explorer_maintained_cache_prewarm import FileLock

DEFAULT_LOCK_PATH = "/tmp/budget_product_best_open_price_builder.lock"
DEFAULT_REPORT_PATH = REPO_ROOT / "docs" / "research" / "best_open_price_bucket3a_dry_run_report.json"

# Chase-accessibility / transform version identifiers are pinned here rather
# than imported, matching the pattern of BEST_OPEN_PRICE_METHOD_VERSION --
# see backend/desirability/weighted_rip.py::compute_overall_rip_v12 for the
# live authority these must track if it is ever versioned independently.
CHASE_ACCESSIBILITY_VERSION = "chase_accessibility_v1"
CHASE_ACCESSIBILITY_TRANSFORM_VERSION = "chase_accessibility_transform_v1"


def resolve_source_identity(client: Any, *, ranking_method_version: str, allocation_method_version: str) -> Dict[str, Any]:
    latest = client.table("budget_product_ranking_latest").select("*") \
        .eq("ranking_method_version", ranking_method_version) \
        .eq("allocation_method_version", allocation_method_version).limit(1).execute()
    rows = list(latest.data or [])
    if not rows:
        raise RuntimeError("no live budget ranking source published for the requested method/allocation versions")
    snapshot = client.table("budget_product_ranking_snapshots").select("*") \
        .eq("id", str(rows[0]["snapshot_id"])).limit(1).execute()
    srows = list(snapshot.data or [])
    if not srows:
        raise RuntimeError("budget ranking latest pointer references a missing snapshot")
    return srows[0]


def already_published_for_identity(client: Any, source: Dict[str, Any], *, method_version: str) -> bool:
    """Idempotent-skip check: a snapshot already exists whose source binding
    exactly matches this source identity and method version."""
    existing = client.table("budget_product_best_open_price_snapshots").select("id") \
        .eq("source_budget_snapshot_id", str(source["id"])) \
        .eq("source_budget_published_at", str(source["published_at"])) \
        .eq("best_open_price_method_version", method_version).limit(1).execute()
    return bool(existing.data)


def verify_no_drift(client: Any, source: Dict[str, Any], *, ranking_method_version: str, allocation_method_version: str) -> None:
    """Re-read the source identity immediately before publish and ABORT on
    any drift -- the ~65-minute computation window is exactly the exposure
    this guards against."""
    fresh = resolve_source_identity(
        client, ranking_method_version=ranking_method_version, allocation_method_version=allocation_method_version,
    )
    if (
        str(fresh["id"]) != str(source["id"])
        or str(fresh["published_at"]) != str(source["published_at"])
        or str(fresh["cohort_fingerprint"]) != str(source["cohort_fingerprint"])
    ):
        raise RuntimeError(
            "source budget ranking authority drifted during computation "
            f"(was snapshot={source['id']} published_at={source['published_at']}, "
            f"now snapshot={fresh['id']} published_at={fresh['published_at']}); aborting publish"
        )


def build_payload_from_engine_result(
    source: Dict[str, Any],
    engine_rows: Sequence[Dict[str, Any]],
    *,
    unresolved_count: int,
    runtime_seconds: float,
    diagnostics_json: Dict[str, Any],
) -> Dict[str, Any]:
    rows = [build_row_payload(row) for row in engine_rows]
    snapshot = build_snapshot_payload(
        built_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        source_budget_snapshot_id=str(source["id"]),
        source_budget_published_at=str(source["published_at"]),
        source_market_date=str(source["market_date"]),
        source_cohort_fingerprint=str(source["cohort_fingerprint"]),
        source_full_market_row_fingerprint=str(source.get("cohort_fingerprint")),
        source_full_market_budget=float(source["full_market_budget"]),
        source_eligible_cohort_count=int(source["eligible_cohort_count"]),
        ranking_method_version=str(source["ranking_method_version"]),
        allocation_method_version=str(source["allocation_method_version"]),
        comparison_scope_version=str(source["comparison_scope_version"]),
        financial_rip_version=str(source["financial_rip_version"]),
        overall_rip_v12_version=str(source["overall_rip_version"]),
        collector_appeal_version=str(source["collector_appeal_version"]),
        chase_accessibility_version=CHASE_ACCESSIBILITY_VERSION,
        chase_accessibility_transform_version=CHASE_ACCESSIBILITY_TRANSFORM_VERSION,
        resolved_count=len(rows),
        unresolved_count=unresolved_count,
        runtime_seconds=runtime_seconds,
        diagnostics_json=diagnostics_json,
    )
    return {"snapshot": snapshot, "rows": rows, "contentFingerprint": content_fingerprint(rows)}


def run(
    *,
    client: Any,
    engine_rows: Sequence[Dict[str, Any]],
    unresolved_count: int,
    runtime_seconds: float,
    diagnostics_json: Dict[str, Any],
    ranking_method_version: str,
    allocation_method_version: str,
    commit: bool,
    report_path: Path = DEFAULT_REPORT_PATH,
    lock: Any = None,
) -> Dict[str, Any]:
    lock = lock or FileLock(DEFAULT_LOCK_PATH)
    if not lock.acquire():
        return {"status": "already_running"}
    try:
        source = resolve_source_identity(
            client, ranking_method_version=ranking_method_version, allocation_method_version=allocation_method_version,
        )
        if already_published_for_identity(client, source, method_version=BEST_OPEN_PRICE_METHOD_VERSION):
            return {"status": "already_published", "sourceBudgetSnapshotId": str(source["id"])}

        expected = int(source["eligible_cohort_count"])
        if len(engine_rows) + unresolved_count != expected:
            raise RuntimeError(
                f"engine produced {len(engine_rows)} resolved + {unresolved_count} unresolved, "
                f"expected total {expected}"
            )

        verify_no_drift(
            client, source, ranking_method_version=ranking_method_version, allocation_method_version=allocation_method_version,
        )

        payload = build_payload_from_engine_result(
            source, engine_rows, unresolved_count=unresolved_count,
            runtime_seconds=runtime_seconds, diagnostics_json=diagnostics_json,
        )

        if not commit:
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(json.dumps({
                "status": "dry_run", "source": {"id": str(source["id"]), "publishedAt": str(source["published_at"])},
                "resolvedCount": len(payload["rows"]), "unresolvedCount": unresolved_count,
                "contentFingerprint": payload["contentFingerprint"],
            }, indent=2), encoding="utf-8")
            return {"status": "dry_run", "reportPath": str(report_path), **payload}

        snapshot_id = publish_snapshot(client, payload["snapshot"], payload["rows"])
        return {"status": "published", "snapshotId": snapshot_id, **payload}
    finally:
        lock.release()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit", action="store_true", help="Actually publish (default: dry-run report only)")
    parser.add_argument("--ranking-method-version", default="budget_constrained_whole_unit_cross_format_v1")
    parser.add_argument("--allocation-method-version", default="floor_to_budget_v1")
    args = parser.parse_args(argv)

    print(
        "This entrypoint requires the validated ~65-minute cohort engine run "
        "(backend/scripts/research_best_open_price_bucket2.py) to be wired in as "
        "`engine_rows` -- invoke `run()` programmatically from a driver that has "
        "already produced that validated result. Refusing to run a placeholder "
        "computation against production.", file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
