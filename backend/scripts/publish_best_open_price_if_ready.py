"""Publish Best-Open Price for the current Full Market authority, once, if needed.

This is the production orchestration wrapper for the already-validated exact
Best-Open Price engine. It performs no request-time work and creates no new
scheduler. The existing daily simulation/publication task invokes this wrapper
after the Budget Ranking publication has completed.

Safety contract:
- one long-running process at a time;
- bind the run to one exact V12 Budget Ranking snapshot before computation;
- use the Bucket-2.x bitwise-exact quantity batching path (width 24);
- require every eligible product to resolve with P* winning and P*+1 cent not
  winning;
- re-read the source after the long build and abort on any drift;
- publish through the already-validated atomic RPC;
- verify the newly published prepared authority before reporting success.
"""

from __future__ import annotations

import argparse
import json
import logging
import platform
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence

from backend.calculations.evr.best_open_price import BEST_OPEN_PRICE_METHOD_VERSION
from backend.calculations.evr.budget_normalized_product_ranking import (
    ALLOCATION_METHOD_VERSION,
    BUDGET_NORMALIZED_RANKING_METHOD_VERSION,
)
from backend.db.clients.supabase_client import create_service_role_client
from backend.db.services.budget_product_best_open_price_service import (
    load_best_open_price_ranking,
    publish_snapshot,
)
from backend.scripts.build_budget_product_best_open_price_snapshot import (
    already_published_for_identity,
    build_payload_from_engine_result,
    resolve_source_identity,
    verify_no_drift,
)
from backend.scripts.research_best_open_price_bucket0 import (
    _historical_authority,
    _load_source,
)
from backend.scripts.research_best_open_price_bucket2 import run as run_exact_engine
from backend.scripts.run_market_explorer_maintained_cache_prewarm import FileLock

logger = logging.getLogger("best-open-price-publication")

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REPORT_PATH = REPO_ROOT / "logs" / "best_open_price_publication.json"
DEFAULT_CHECKPOINT_DIR = REPO_ROOT / "logs" / "best_open_price_checkpoints"
DEFAULT_LOCK_PATH = "/tmp/budget_product_best_open_price_daily.lock"
DEFAULT_QUANTITY_BATCH_SIZE = 24

STATUS_EXIT_CODES = {
    "PUBLISHED": 0,
    "ALREADY_CURRENT": 0,
    "READY_DRY_RUN": 0,
    "ALREADY_RUNNING": 3,
    "SOURCE_FAILED": 2,
    "BUILD_FAILED": 1,
    "VALIDATION_FAILED": 1,
    "SOURCE_DRIFT": 1,
    "PUBLICATION_FAILED": 1,
    "POST_PUBLISH_VERIFICATION_FAILED": 1,
}

_SUPPORTED_RESOLVED_STATUSES = frozenset({
    "resolved_below_market",
    "resolved_at_market",
    "current_number_one_with_headroom",
})
_REQUIRED_EVIDENCE_FIELDS = (
    "currentFinancialRipV4Score",
    "currentCollectorAppealScore",
    "currentChaseAccessibilityRaw",
    "currentChanceToRecoverCapital",
    "currentActualCommittedCapital",
    "benchmarkOverallRipV12Score",
    "benchmarkFinancialRipV4Score",
    "benchmarkChanceToRecoverCapital",
    "benchmarkActualCommittedCapital",
)


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _base_report(*, commit: bool, quantity_batch_size: int) -> Dict[str, Any]:
    return {
        "status": None,
        "startedAt": _utcnow(),
        "finishedAt": None,
        "mode": "commit" if commit else "dry_run",
        "host": platform.node(),
        "head": subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=False,
        ).stdout.strip() or None,
        "methodVersion": BEST_OPEN_PRICE_METHOD_VERSION,
        "quantityBatchSize": quantity_batch_size,
        "sourceBudgetSnapshotId": None,
        "sourceBudgetPublishedAt": None,
        "sourceMarketDate": None,
        "sourceCohortFingerprint": None,
        "sourceAuthorityFingerprint": None,
        "eligibleCohortCount": None,
        "resolvedCount": None,
        "unresolvedCount": None,
        "bestOpenSnapshotId": None,
        "checkpointPath": None,
        "engineRuntimeSeconds": None,
        "failureReason": None,
        "diagnostics": {},
    }


def _finish(report: Dict[str, Any], status: str, *, reason: Optional[str] = None) -> tuple[int, Dict[str, Any]]:
    report["status"] = status
    report["finishedAt"] = _utcnow()
    if reason:
        report["failureReason"] = reason
    return STATUS_EXIT_CODES[status], report


def _checkpoint_path(checkpoint_dir: Path, snapshot_id: str) -> Path:
    safe = "".join(ch for ch in str(snapshot_id) if ch.isalnum() or ch in "-_")
    return checkpoint_dir / f"best_open_price_{safe}.json"


def validate_engine_result(engine: Mapping[str, Any], source: Mapping[str, Any]) -> list[str]:
    """Fail-closed publication gates over the completed exact-engine artifact."""
    errors: list[str] = []
    expected = int(source.get("eligible_cohort_count") or 0)
    rows = [row for row in (engine.get("products") or []) if isinstance(row, Mapping)]
    analysis = engine.get("cohortAnalysis") or {}

    if engine.get("status") != "complete":
        errors.append("engine artifact is not complete")
    if str((engine.get("source") or {}).get("snapshotId")) != str(source.get("id")):
        errors.append("engine source snapshot does not match captured Budget Ranking authority")
    if str((engine.get("source") or {}).get("cohortFingerprint")) != str(source.get("cohort_fingerprint")):
        errors.append("engine cohort fingerprint does not match captured Budget Ranking authority")
    if expected < 1 or len(rows) != expected:
        errors.append(f"engine resolved row population {len(rows)} does not equal eligible cohort {expected}")
    if int(analysis.get("attempted") or 0) != expected:
        errors.append("engine attempted count does not equal eligible cohort")
    if int(analysis.get("resolved") or 0) != expected or int(analysis.get("unresolved") or 0) != 0:
        errors.append("engine did not resolve the complete eligible cohort")

    identities = [str(row.get("sealedProductId") or "") for row in rows]
    if not all(identities) or len(identities) != len(set(identities)):
        errors.append("engine rows contain missing or duplicate product identities")

    for row in rows:
        pid = str(row.get("sealedProductId") or "<missing>")
        if row.get("status") not in _SUPPORTED_RESOLVED_STATUSES:
            errors.append(f"{pid}: unsupported or unresolved status {row.get('status')!r}")
        if row.get("bestOpenPrice") is None or row.get("thresholdQuantity") is None:
            errors.append(f"{pid}: missing exact threshold price/quantity")
        exactness = row.get("exactness") or {}
        if exactness.get("thresholdWins") is not True:
            errors.append(f"{pid}: P* does not canonically win")
        if exactness.get("oneCentMaximal") is not True or exactness.get("nextPriceWins") is True:
            errors.append(f"{pid}: P*+1 cent maximality failed")
        for field in _REQUIRED_EVIDENCE_FIELDS:
            if row.get(field) is None:
                errors.append(f"{pid}: missing persisted source evidence {field}")
        if row.get("sourceCalculationRunId") in (None, ""):
            errors.append(f"{pid}: missing source calculation run")

    return errors


def _compact_diagnostics(engine: Mapping[str, Any]) -> Dict[str, Any]:
    timings = engine.get("timings") or {}
    lru = engine.get("lru") or {}
    analysis = engine.get("cohortAnalysis") or {}
    return {
        "constructionMode": engine.get("constructionMode"),
        "quantityBatchSize": engine.get("quantityBatchSize"),
        "statusCounts": analysis.get("statusCounts") or {},
        "discountPercentiles": analysis.get("discountPercentiles") or {},
        "totalWallSeconds": timings.get("totalWallSeconds"),
        "quantityDistributionConstructionSeconds": timings.get("quantityDistributionConstructionSeconds"),
        "preparedScorerConstructionSeconds": timings.get("preparedScorerConstructionSeconds"),
        "quantityCacheHits": lru.get("hits"),
        "quantityCacheMisses": lru.get("misses"),
        "quantityCacheEvictions": lru.get("evictions"),
        "determinismReplaySkippedForRecurringPublication": True,
    }


def _already_current(client: Any, source: Mapping[str, Any]) -> bool:
    prepared = load_best_open_price_ranking(client)
    return bool(
        prepared.get("available")
        and str(prepared.get("sourceBudgetSnapshotId")) == str(source.get("id"))
        and str(prepared.get("sourceBudgetPublishedAt")) == str(source.get("published_at"))
        and str(prepared.get("sourceCohortFingerprint")) == str(source.get("cohort_fingerprint"))
        and int(prepared.get("unresolvedCount") or 0) == 0
        and int(prepared.get("resolvedCount") or 0) == int(source.get("eligible_cohort_count") or 0)
    )


def run(
    *,
    commit: bool,
    client: Any = None,
    quantity_batch_size: int = DEFAULT_QUANTITY_BATCH_SIZE,
    checkpoint_dir: Path = DEFAULT_CHECKPOINT_DIR,
    lock: Any = None,
    engine_runner=run_exact_engine,
) -> tuple[int, Dict[str, Any]]:
    started = time.perf_counter()
    report = _base_report(commit=commit, quantity_batch_size=quantity_batch_size)
    if quantity_batch_size < 1:
        return _finish(report, "SOURCE_FAILED", reason="quantity batch size must be positive")

    lock = lock or FileLock(DEFAULT_LOCK_PATH)
    if not lock.acquire():
        return _finish(report, "ALREADY_RUNNING")

    try:
        client = client or create_service_role_client()
        try:
            source = resolve_source_identity(
                client,
                ranking_method_version=BUDGET_NORMALIZED_RANKING_METHOD_VERSION,
                allocation_method_version=ALLOCATION_METHOD_VERSION,
            )
            report.update({
                "sourceBudgetSnapshotId": str(source["id"]),
                "sourceBudgetPublishedAt": str(source["published_at"]),
                "sourceMarketDate": str(source["market_date"]),
                "sourceCohortFingerprint": str(source["cohort_fingerprint"]),
                "eligibleCohortCount": int(source["eligible_cohort_count"]),
            })
            if not source.get("ranked_under_v12_authority"):
                return _finish(report, "SOURCE_FAILED", reason="current Budget Ranking is not V12-authoritative")

            if _already_current(client, source):
                return _finish(report, "ALREADY_CURRENT")
            if already_published_for_identity(client, source, method_version=BEST_OPEN_PRICE_METHOD_VERSION):
                # This means an exact-source publication exists but is not the
                # current readable pointer. Recomputing would create different
                # timing diagnostics under the same authority identity and the
                # atomic RPC correctly refuses such nondeterministic content.
                return _finish(
                    report, "SOURCE_FAILED",
                    reason="an exact-source Best-Open snapshot exists but is not the readable latest authority",
                )

            source_snapshot, source_rows, _ = _load_source(client, str(source["id"]))
            if (
                str(source_snapshot.get("published_at")) != str(source.get("published_at"))
                or str(source_snapshot.get("cohort_fingerprint")) != str(source.get("cohort_fingerprint"))
            ):
                return _finish(report, "SOURCE_FAILED", reason="captured source identity changed before engine start")
            source_authority = _historical_authority(source_snapshot, source_rows)
            report["sourceAuthorityFingerprint"] = source_authority["fingerprint"]
        except Exception as exc:
            return _finish(report, "SOURCE_FAILED", reason=str(exc))

        checkpoint = _checkpoint_path(checkpoint_dir, str(source["id"]))
        report["checkpointPath"] = str(checkpoint)
        try:
            engine = engine_runner(
                checkpoint,
                quantity_batch_size=quantity_batch_size,
                run_determinism=False,
                source_snapshot_id=str(source["id"]),
                expected_source_authority_fingerprint=source_authority["fingerprint"],
            )
        except Exception as exc:
            return _finish(report, "BUILD_FAILED", reason=str(exc))

        report["engineRuntimeSeconds"] = (engine.get("timings") or {}).get("totalWallSeconds")
        analysis = engine.get("cohortAnalysis") or {}
        report["resolvedCount"] = analysis.get("resolved")
        report["unresolvedCount"] = analysis.get("unresolved")
        report["diagnostics"] = _compact_diagnostics(engine)

        validation_errors = validate_engine_result(engine, source)
        if validation_errors:
            report["diagnostics"]["validationErrors"] = validation_errors[:25]
            return _finish(report, "VALIDATION_FAILED", reason="; ".join(validation_errors[:5]))

        try:
            verify_no_drift(
                client, source,
                ranking_method_version=BUDGET_NORMALIZED_RANKING_METHOD_VERSION,
                allocation_method_version=ALLOCATION_METHOD_VERSION,
            )
        except Exception as exc:
            return _finish(report, "SOURCE_DRIFT", reason=str(exc))

        payload = build_payload_from_engine_result(
            dict(source),
            list(engine.get("products") or []),
            unresolved_count=0,
            runtime_seconds=float(report["engineRuntimeSeconds"] or (time.perf_counter() - started)),
            diagnostics_json=report["diagnostics"],
        )

        if not commit:
            report["diagnostics"]["contentFingerprint"] = payload["contentFingerprint"]
            return _finish(report, "READY_DRY_RUN")

        try:
            # The atomic RPC performs the final in-transaction live-source and
            # row-by-row evidence revalidation. A source change in the tiny gap
            # after verify_no_drift therefore rolls back instead of publishing
            # a stale threshold snapshot.
            snapshot_id = publish_snapshot(client, payload["snapshot"], payload["rows"])
            report["bestOpenSnapshotId"] = snapshot_id
        except Exception as exc:
            return _finish(report, "PUBLICATION_FAILED", reason=str(exc))

        try:
            verified = load_best_open_price_ranking(client)
            if not (
                verified.get("available")
                and str(verified.get("snapshotId")) == str(snapshot_id)
                and str(verified.get("sourceBudgetSnapshotId")) == str(source["id"])
                and int(verified.get("resolvedCount") or 0) == int(source["eligible_cohort_count"])
                and int(verified.get("unresolvedCount") or 0) == 0
            ):
                raise RuntimeError(f"published Best-Open authority failed read-back verification: {verified.get('reason')}")
        except Exception as exc:
            return _finish(report, "POST_PUBLISH_VERIFICATION_FAILED", reason=str(exc))

        return _finish(report, "PUBLISHED")
    finally:
        lock.release()


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--commit", action="store_true")
    parser.add_argument("--json-report", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--checkpoint-dir", type=Path, default=DEFAULT_CHECKPOINT_DIR)
    parser.add_argument("--quantity-batch-size", type=int, default=DEFAULT_QUANTITY_BATCH_SIZE)
    args = parser.parse_args(argv)

    logger.info(
        "best-open publication start head=%s host=%s mode=%s",
        subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=False).stdout.strip(),
        platform.node(),
        "commit" if args.commit else "dry-run",
    )
    code, report = run(
        commit=args.commit,
        quantity_batch_size=args.quantity_batch_size,
        checkpoint_dir=args.checkpoint_dir,
    )
    args.json_report.parent.mkdir(parents=True, exist_ok=True)
    args.json_report.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    print("[best-open-price] " + json.dumps({
        key: report.get(key) for key in (
            "status", "sourceMarketDate", "sourceBudgetSnapshotId", "bestOpenSnapshotId",
            "resolvedCount", "unresolvedCount", "engineRuntimeSeconds", "failureReason",
        )
    }, default=str), flush=True)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
