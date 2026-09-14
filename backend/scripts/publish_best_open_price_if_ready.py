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
import hashlib
import json
import logging
import os
import platform
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence

from backend.calculations.evr.best_open_price import BEST_OPEN_PRICE_METHOD_VERSION
from backend.calculations.evr.budget_normalized_product_ranking import (
    ALLOCATION_METHOD_VERSION,
    BUDGET_NORMALIZED_RANKING_METHOD_VERSION,
)
from backend.db.clients.supabase_client import create_service_role_client
from backend.db.services.best_open_price_authority import (
    EXECUTION_CONTRACT_VERSION, cents, finite_decimal, source_identity,
    source_content_fingerprint, validate_source, timestamp,
)
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
from backend.scripts.research_best_open_price_bucket2 import run as run_exact_engine, _write_checkpoint

logger = logging.getLogger("best-open-price-publication")

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REPORT_PATH = REPO_ROOT / "logs" / "best_open_price_publication.json"
DEFAULT_CHECKPOINT_DIR = REPO_ROOT / "logs" / "best_open_price_checkpoints"
DEFAULT_LOCK_PATH = Path(tempfile.gettempdir()) / "budget_product_best_open_price_daily.lock"
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


class PublicationFileLock:
    """Process-scoped nonblocking singleton lock for the long daily build.

    The production scheduler runs on Windows, so a lock-file-exists fallback is
    not sufficient: an interrupted process can leave that file behind forever.
    This class uses an OS byte lock (``msvcrt.locking`` on Windows,
    ``fcntl.flock`` on POSIX). The file itself may remain in the temp directory,
    but the lock is released automatically by the OS when the process exits or
    crashes.
    """

    def __init__(self, path: Path | str = DEFAULT_LOCK_PATH):
        self.path = Path(path)
        self._fh = None

    def acquire(self) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fh = open(self.path, "a+b")
        try:
            fh.seek(0, os.SEEK_END)
            if fh.tell() < 1:
                fh.write(b"\0")
                fh.flush()
            fh.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl  # type: ignore
                fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            fh.close()
            return False
        self._fh = fh
        return True

    def release(self) -> None:
        fh = self._fh
        if fh is None:
            return
        try:
            fh.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl  # type: ignore
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        except Exception:
            logger.exception("best-open publication lock release failed path=%s", self.path)
        finally:
            try:
                fh.close()
            finally:
                self._fh = None


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


def _checkpoint_path(checkpoint_dir: Path, source: Mapping[str, Any]) -> Path:
    """Checkpoint namespace bound to the full publication identity, not ID alone.

    Budget Ranking can legally replace rows under the same snapshot ID while
    advancing ``published_at``. Including published_at/market-date/cohort in a
    short digest prevents a partially-computed T1 checkpoint from being resumed
    under T2 even when the snapshot UUID is reused.
    """
    snapshot_id = str(source.get("id") or "")
    safe = "".join(ch for ch in snapshot_id if ch.isalnum() or ch in "-_") or "unknown"
    identity = json.dumps({"source": source_identity(source),
                           "execution": EXECUTION_CONTRACT_VERSION,
                           "content": source.get("_source_content_fingerprint")},
                          sort_keys=True, default=str)
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]
    return checkpoint_dir / f"best_open_price_{safe}_{digest}.json"


def validate_engine_result(engine: Mapping[str, Any], source: Mapping[str, Any],
                           source_rows: Optional[Sequence[Mapping[str, Any]]] = None) -> list[str]:
    """Validate arithmetic and evidence, not just self-reported success flags."""
    errors: list[str] = []
    try:
        expected = int(source["eligible_cohort_count"])
        budget_cents = cents(source["full_market_budget"])
        rows = engine.get("products") or []
        if not isinstance(rows, list) or any(not isinstance(row, Mapping) for row in rows):
            return ["engine products must be a list of complete row objects"]
        analysis = engine.get("cohortAnalysis") or {}
        identity = engine.get("source") or {}
        if engine.get("status") != "complete":
            errors.append("engine artifact is not complete")
        if engine.get("methodVersion") != BEST_OPEN_PRICE_METHOD_VERSION:
            errors.append("engine method version mismatch")
        if str(identity.get("snapshotId")) != str(source["id"]) or str(identity.get("cohortFingerprint")) != str(source["cohort_fingerprint"]):
            errors.append("engine source authority mismatch")
        if timestamp(identity.get("publishedAt")) != timestamp(source["published_at"]):
            errors.append("engine source publication timestamp mismatch")
        if source.get("_source_content_fingerprint") and identity.get("sourceContentFingerprint") != source["_source_content_fingerprint"]:
            errors.append("engine source content fingerprint mismatch")
        if identity.get("authorityUnchangedAtCompletion") is not True:
            errors.append("engine source drift verification is missing")
        if cents(identity.get("fullMarketBudget")) != budget_cents:
            errors.append("engine Full Market budget mismatch")
        if expected < 2 or len(rows) != expected or any(int(analysis.get(k) or 0) != expected for k in ("attempted", "resolved")) or int(analysis.get("unresolved") or 0) != 0:
            errors.append("engine did not resolve the complete eligible cohort")
        ids = [str(row.get("sealedProductId") or "") for row in rows]
        if not all(ids) or len(ids) != len(set(ids)):
            errors.append("engine rows contain missing or duplicate product identities")
        by_source = {str(row["sealed_product_id"]): row for row in (source_rows or [])}
        if source_rows is not None and set(ids) != set(by_source):
            errors.append("engine product identities do not match the Full Market source")
        ranks = {str(row["sealed_product_id"]): int(row["budget_rank_v12"]) for row in (source_rows or [])}
        for row in rows:
            pid = str(row.get("sealedProductId") or "<missing>")
            try:
                price, current = cents(row.get("bestOpenPrice")), cents(row.get("currentMarketPrice"))
                quantity = finite_decimal(row.get("thresholdQuantity"))
                current_q = finite_decimal(row.get("currentQuantity"))
                rank = int(row["currentBudgetRank"])
                if min(price, current) < 1 or max(price, current) > budget_cents:
                    raise ValueError("price outside the positive-cent budget domain")
                if quantity != budget_cents // price or current_q != budget_cents // current:
                    raise ValueError("quantity does not match exact whole-unit allocation")
                if row.get("bestOpenPriceCents") != price:
                    raise ValueError("threshold cents disagree with price")
                status = row.get("status")
                expected_status = ("current_number_one_with_headroom" if rank == 1 and price > current else
                                   "resolved_at_market" if price == current else "resolved_below_market")
                if status not in _SUPPORTED_RESOLVED_STATUSES or status != expected_status or (rank == 1 and price < current) or (rank != 1 and price > current):
                    raise ValueError("invalid threshold status/direction")
                if cents(row.get("priceGapDollars")) != current - price:
                    raise ValueError("price gap does not reconcile")
                if abs(finite_decimal(row.get("priceGapPercent")) - Decimal(current - price) / Decimal(current)) > Decimal("1e-12"):
                    raise ValueError("price gap percent does not reconcile")
                if finite_decimal(row.get("currentActualCommittedCapital")) != current_q * Decimal(current) / 100:
                    raise ValueError("current committed capital does not reconcile")
                exactness = row.get("exactness") or {}
                if exactness.get("thresholdWins") is not True:
                    raise ValueError("P* does not canonically win")
                next_cent = price + 1 if price < budget_cents else None
                inside = next_cent is not None and (rank == 1 or next_cent <= current)
                if (exactness.get("oneCentMaximal") is not True or exactness.get("nextPriceCents") != next_cent
                    or (inside and exactness.get("nextPriceWins") is not False)
                    or (not inside and exactness.get("nextPriceWins") is not None)):
                    raise ValueError("P*+1 cent maximality failed or was not verified")
                for field in _REQUIRED_EVIDENCE_FIELDS:
                    finite_decimal(row.get(field))
                for field in ("sourceCalculationRunId", "setId", "productFamily", "benchmarkSealedProductId"):
                    if not row.get(field):
                        raise ValueError(f"missing source evidence {field}")
                if row["benchmarkSealedProductId"] == pid:
                    raise ValueError("candidate cannot benchmark against itself")
                if source_rows is not None:
                    actual = by_source[pid]
                    mapping = {"currentMarketPrice": "product_market_price", "currentQuantity": "quantity",
                               "currentBudgetRank": "budget_rank_v12", "currentOverallRipV12Score": "overall_rip_v12_score",
                               "currentFinancialRipV4Score": "financial_rip_v4_score", "currentCollectorAppealScore": "collector_appeal_score",
                               "currentChaseAccessibilityRaw": "chase_accessibility_raw", "currentChanceToRecoverCapital": "chance_to_recover_capital",
                               "currentActualCommittedCapital": "actual_committed_capital"}
                    for output, key in mapping.items():
                        if finite_decimal(row.get(output)) != finite_decimal(actual.get(key)):
                            raise ValueError(f"current source value mismatch: {output}")
                    if str(row["sourceCalculationRunId"]) != str(actual["source_calculation_run_id"]) or str(row["setId"]) != str(actual["set_id"]) or row["productFamily"] != actual["product_family"]:
                        raise ValueError("source product/run identity mismatch")
                    benchmark_id = str(row["benchmarkSealedProductId"])
                    if ranks.get(benchmark_id) != (2 if ranks[pid] == 1 else 1):
                        raise ValueError("wrong canonical benchmark")
                    benchmark = by_source[benchmark_id]
                    for output, key in (("benchmarkOverallRipV12Score", "overall_rip_v12_score"), ("benchmarkFinancialRipV4Score", "financial_rip_v4_score"),
                                        ("benchmarkChanceToRecoverCapital", "chance_to_recover_capital"), ("benchmarkActualCommittedCapital", "actual_committed_capital")):
                        if finite_decimal(row.get(output)) != finite_decimal(benchmark.get(key)):
                            raise ValueError(f"benchmark source value mismatch: {output}")
            except (ValueError, TypeError, KeyError, ArithmeticError) as exc:
                errors.append(f"{pid}: {exc}")
    except (ValueError, TypeError, KeyError, ArithmeticError) as exc:
        errors.append(f"invalid engine publication payload: {exc}")
    return errors


def _compact_diagnostics(engine: Mapping[str, Any]) -> Dict[str, Any]:
    timings = engine.get("timings") or {}
    lru = engine.get("lru") or {}
    analysis = engine.get("cohortAnalysis") or {}
    return {
        "executionContractVersion": EXECUTION_CONTRACT_VERSION,
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
        and timestamp(prepared.get("sourceBudgetPublishedAt")) == timestamp(source.get("published_at"))
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

    lock = lock or PublicationFileLock(DEFAULT_LOCK_PATH)
    try:
        if not lock.acquire():
            return _finish(report, "ALREADY_RUNNING")
    except OSError as exc:
        return _finish(report, "SOURCE_FAILED", reason=f"publication lock unavailable: {exc}")

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
            validate_source(source)

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
                source_identity(source_snapshot) != source_identity(source)
            ):
                return _finish(report, "SOURCE_FAILED", reason="captured source identity changed before engine start")
            source_authority = _historical_authority(source_snapshot, source_rows)
            report["sourceAuthorityFingerprint"] = source_authority["fingerprint"]
            source = dict(source)
            source["_source_content_fingerprint"] = source_content_fingerprint(source_snapshot, source_rows)
        except Exception as exc:
            return _finish(report, "SOURCE_FAILED", reason=str(exc))

        checkpoint = _checkpoint_path(checkpoint_dir, source)
        report["checkpointPath"] = str(checkpoint)
        try:
            engine = engine_runner(
                checkpoint,
                quantity_batch_size=quantity_batch_size,
                run_determinism=False,
                source_snapshot_id=str(source["id"]),
                expected_source_authority_fingerprint=source_authority["fingerprint"],
                expected_source_content_fingerprint=source["_source_content_fingerprint"],
                client=client,
                reuse_complete=True,
            )
        except Exception as exc:
            return _finish(report, "BUILD_FAILED", reason=str(exc))

        report["engineRuntimeSeconds"] = (engine.get("timings") or {}).get("totalWallSeconds")
        analysis = engine.get("cohortAnalysis") or {}
        report["resolvedCount"] = analysis.get("resolved")
        report["unresolvedCount"] = analysis.get("unresolved")
        report["diagnostics"] = _compact_diagnostics(engine)

        validation_errors = validate_engine_result(engine, source, source_rows)
        if validation_errors:
            report["diagnostics"]["validationErrors"] = validation_errors[:25]
            return _finish(report, "VALIDATION_FAILED", reason="; ".join(validation_errors[:5]))

        try:
            verify_no_drift(
                client, source,
                ranking_method_version=BUDGET_NORMALIZED_RANKING_METHOD_VERSION,
                allocation_method_version=ALLOCATION_METHOD_VERSION,
            )
            end_snapshot, end_rows, _ = _load_source(client, str(source["id"]))
            if source_content_fingerprint(end_snapshot, end_rows) != source["_source_content_fingerprint"]:
                raise RuntimeError("Full Market source values changed during computation")
        except Exception as exc:
            return _finish(report, "SOURCE_DRIFT", reason=str(exc))

        try:
            payload = build_payload_from_engine_result(
                dict(source),
                list(engine.get("products") or []),
                unresolved_count=0,
                runtime_seconds=float(report["engineRuntimeSeconds"] or (time.perf_counter() - started)),
                diagnostics_json=report["diagnostics"],
            )
        except Exception as exc:
            return _finish(report, "VALIDATION_FAILED", reason=f"publication payload construction failed: {exc}")

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
                and timestamp(verified.get("sourceBudgetPublishedAt")) == timestamp(source["published_at"])
                and str(verified.get("sourceCohortFingerprint")) == str(source["cohort_fingerprint"])
                and int(verified.get("resolvedCount") or 0) == int(source["eligible_cohort_count"])
                and int(verified.get("unresolvedCount") or 0) == 0
            ):
                raise RuntimeError(f"published Best-Open authority failed read-back verification: {verified.get('reason')}")
            persisted = {str(row.get("sealed_product_id")): row for row in verified.get("rows", [])}
            if set(persisted) != {str(row["sealed_product_id"]) for row in payload["rows"]}:
                raise RuntimeError("published product identity set differs from submitted rows")
            for row in payload["rows"]:
                actual = persisted[str(row["sealed_product_id"])]
                for key, expected in row.items():
                    value = actual.get(key)
                    if isinstance(expected, (int, float, Decimal)) and not isinstance(expected, bool):
                        equal = finite_decimal(value) == finite_decimal(expected)
                    else:
                        equal = value == expected
                    if not equal:
                        raise RuntimeError(f"published row field mismatch: {row['sealed_product_id']} {key}")
        except Exception as exc:
            return _finish(report, "POST_PUBLISH_VERIFICATION_FAILED", reason=str(exc))

        return _finish(report, "PUBLISHED")
    except Exception as exc:
        logger.exception("unhandled Best-Open publication failure")
        return _finish(report, "BUILD_FAILED", reason=str(exc))
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
    _write_checkpoint(args.json_report, report)
    print("[best-open-price] " + json.dumps({
        key: report.get(key) for key in (
            "status", "sourceMarketDate", "sourceBudgetSnapshotId", "bestOpenSnapshotId",
            "resolvedCount", "unresolvedCount", "engineRuntimeSeconds", "failureReason",
        )
    }, default=str), flush=True)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
