"""Fail-closed Price Storage V2 serving publication for canonical Pokemon Market roots.

This is deliberately NOT a scheduler. The existing post-scrape wrapper owns timing
and the single-publisher lock. This command owns one bounded publication phase:

1. Market Date Quality must accept/persist the explicit date.
2. Resolve the exact shared global-Market root authority for that date.
3. Stage every root in proven <=5-root batches; publish nothing if any root blocks.
4. Respect the operator release gate. This command never enables it.
5. Apply the frozen Sep 8 V2 transition anchor once.
6. Publish isolated V2 member+root history one root at a time.
7. Only after the ENTIRE root cohort is complete, atomically flip the legacy
   compatibility projection and record the cohort receipt.

A failure after some isolated roots have committed is safe: current public readers
have not advanced because compatibility finalization happens only after every root
succeeds. A retry revalidates the same staged evidence and no-ops exact rows.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
from pathlib import Path
from typing import Any, Iterable, Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.db.services.market_publication_gate import (
    MarketForcePublishRejected,
    enforce_market_publication_gate,
)
from backend.db.services.pokemon_market_rollout_cohort import (
    MARKET_ROOT_AUTHORITY_CUTOVER_DATE,
    resolve_market_root_cohort,
)
from backend.scripts.pokemon_snapshot_builders import get_client

LOG = logging.getLogger("price_storage_v2_serving_cutover")

STAGE_RPC = "stage_price_storage_v2_scoped_values_v2"
ATOMIC_PUBLISH_RPC = "publish_price_storage_v2_scoped_run_atomic_v2"
ANCHOR_RPC = "apply_price_storage_v2_transition_anchor_v1"
FINALIZE_RPC = "finalize_price_storage_v2_serving_compatibility_v1"
RELEASE_GATE_TABLE = "price_storage_v2_scoped_release_gate"
ROOT_HISTORY_TABLE = "pokemon_root_set_value_daily_history_v2"
MEMBER_HISTORY_TABLE = "pokemon_member_set_value_daily_history_v2"
RECEIPT_TABLE = "price_storage_v2_serving_publication_receipts"

STAGE_BATCH_SIZE = 5
READ_BATCH_SIZE = 80
EXIT_OK = 0
EXIT_FAILED = 1
EXIT_BLOCKED = 3


def _chunks(values: Sequence[str], size: int) -> Iterable[list[str]]:
    for offset in range(0, len(values), size):
        yield list(values[offset:offset + size])


def _rpc_data(result: Any) -> Any:
    return getattr(result, "data", None)


def _root_fingerprint(root_ids: Sequence[str]) -> str:
    return hashlib.md5(",".join(sorted(root_ids)).encode("utf-8")).hexdigest()


def _read_release_gate(client: Any) -> bool:
    rows = list(
        client.table(RELEASE_GATE_TABLE)
        .select("enabled")
        .eq("singleton", True)
        .limit(1)
        .execute().data or []
    )
    return bool(rows and rows[0].get("enabled") is True)


def _read_history_rows(
    client: Any,
    table: str,
    *,
    market_date: str,
    root_ids: Sequence[str],
    root_key: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for batch in _chunks(list(root_ids), READ_BATCH_SIZE):
        result = (
            client.table(table)
            .select("set_id,root_set_id,snapshot_date,value_scope,run_id,source")
            .eq("snapshot_date", market_date)
            .in_(root_key, batch)
            .execute()
        )
        rows.extend(dict(row) for row in (result.data or []))
    return rows


def _verify_isolated_cohort(
    client: Any,
    *,
    market_date: str,
    root_ids: Sequence[str],
) -> dict[str, Any]:
    roots = _read_history_rows(
        client, ROOT_HISTORY_TABLE, market_date=market_date,
        root_ids=root_ids, root_key="set_id",
    )
    members = _read_history_rows(
        client, MEMBER_HISTORY_TABLE, market_date=market_date,
        root_ids=root_ids, root_key="root_set_id",
    )
    expected_root_rows = len(root_ids) * 3
    root_scope_keys = {
        (str(row.get("set_id")), str(row.get("value_scope"))) for row in roots
    }
    expected_scope_keys = {
        (root_id, scope)
        for root_id in root_ids
        for scope in ("standard", "hits", "top10")
    }
    member_root_ids = {str(row.get("root_set_id")) for row in members}
    errors: list[str] = []
    if len(roots) != expected_root_rows:
        errors.append(f"root rows {len(roots)} != {expected_root_rows}")
    if root_scope_keys != expected_scope_keys:
        errors.append("root Standard/Hits/Top10 scope matrix is incomplete")
    if member_root_ids != set(root_ids):
        errors.append("member history does not cover the exact root cohort")
    if any(str(row.get("source")) != "price_storage_v2_root_scope_v1" for row in roots):
        errors.append("unexpected root V2 source label")
    if any(str(row.get("source")) != "price_storage_v2_member_scope_v1" for row in members):
        errors.append("unexpected member V2 source label")
    return {
        "ok": not errors,
        "errors": errors,
        "rootRows": len(roots),
        "expectedRootRows": expected_root_rows,
        "memberRows": len(members),
        "memberRoots": len(member_root_ids),
    }


def _read_receipt(client: Any, market_date: str) -> dict[str, Any] | None:
    rows = list(
        client.table(RECEIPT_TABLE)
        .select("market_date,root_count,root_fingerprint,compatibility_row_count,finalized_at")
        .eq("market_date", market_date)
        .limit(1)
        .execute().data or []
    )
    return dict(rows[0]) if rows else None


def run(
    client: Any,
    *,
    market_date: str,
    commit: bool,
) -> tuple[int, dict[str, Any]]:
    day = str(market_date)[:10]
    report: dict[str, Any] = {
        "marketDate": day,
        "cutoverDate": MARKET_ROOT_AUTHORITY_CUTOVER_DATE,
        "mode": "commit" if commit else "dry-run",
        "stageBatchSize": STAGE_BATCH_SIZE,
        "releaseGateMutated": False,
        "schedulerAttached": False,
        "publicCompatibilityFinalized": False,
    }

    if day < MARKET_ROOT_AUTHORITY_CUTOVER_DATE:
        report.update(status="pre_cutover_noop", reason="historical authority remains frozen")
        return EXIT_OK, report

    try:
        gate = enforce_market_publication_gate(
            client,
            commit=commit,
            market_date=day,
            entry_point="Price Storage V2 serving publication",
        )
    except MarketForcePublishRejected as exc:  # defensive; this command has no force flag
        report.update(status="blocked", reason=str(exc))
        return EXIT_BLOCKED, report
    if not gate.proceed:
        report.update(
            status="market_quality_blocked",
            reason=gate.decision.reason,
            marketQualityStatus=gate.decision.status,
        )
        return int(gate.exit_code or EXIT_BLOCKED), report

    roots = resolve_market_root_cohort(client, market_date=day)
    root_ids = sorted({str(row.get("id")) for row in roots if row.get("id")})
    if not root_ids:
        report.update(status="failed", reason="canonical Market root authority is empty")
        return EXIT_FAILED, report
    report.update(
        rootCount=len(root_ids),
        rootFingerprint=_root_fingerprint(root_ids),
        marketQualityStatus=gate.decision.status,
    )

    if not commit:
        report.update(
            status="dry_run_ready",
            releaseGateEnabled=_read_release_gate(client),
            reason="quality and root authority resolved; no staging/publication writes performed",
        )
        return EXIT_OK, report

    staged: dict[str, int] = {}
    stage_results: list[dict[str, Any]] = []
    for batch_number, batch in enumerate(_chunks(root_ids, STAGE_BATCH_SIZE), start=1):
        response = client.rpc(
            STAGE_RPC,
            {"p_root_set_ids": batch, "p_market_date": day},
        ).execute()
        payload = _rpc_data(response) or {}
        results = list(payload.get("results") or []) if isinstance(payload, dict) else []
        stage_results.extend(dict(item) for item in results)
        LOG.info(
            "[price-storage-v2-serving] staged batch=%s roots=%s/%s",
            batch_number,
            min(batch_number * STAGE_BATCH_SIZE, len(root_ids)),
            len(root_ids),
        )

    for item in stage_results:
        root_id = str(item.get("root_set_id") or "")
        run_id = item.get("run_id")
        if item.get("status") == "parity_passed" and root_id and run_id is not None:
            staged[root_id] = int(run_id)
    blocked = [
        item for item in stage_results
        if item.get("status") != "parity_passed" or item.get("run_id") is None
    ]
    if blocked or set(staged) != set(root_ids):
        report.update(
            status="staging_blocked",
            stagedRoots=len(staged),
            blockedRoots=blocked[:20],
            reason="every canonical root must parity-pass before isolated publication begins",
        )
        return EXIT_BLOCKED, report

    report["stagedRoots"] = len(staged)
    release_enabled = _read_release_gate(client)
    report["releaseGateEnabled"] = release_enabled
    if not release_enabled:
        report.update(
            status="release_gate_closed",
            reason="operator kill switch is closed; staged evidence retained, no V2 publication performed",
        )
        return EXIT_BLOCKED, report

    anchor_response = client.rpc(ANCHOR_RPC, {"p_anchor_date": "2026-09-08"}).execute()
    anchor = _rpc_data(anchor_response) or {}
    report["transitionAnchor"] = anchor
    if not isinstance(anchor, dict) or anchor.get("status") not in ("complete", "noop"):
        report.update(status="anchor_failed", reason="Sep 8 transition anchor did not complete")
        return EXIT_FAILED, report

    published: list[dict[str, Any]] = []
    for idx, root_id in enumerate(root_ids, start=1):
        try:
            response = client.rpc(
                ATOMIC_PUBLISH_RPC,
                {
                    "p_run_id": staged[root_id],
                    "p_root_set_id": root_id,
                    "p_market_date": day,
                },
            ).execute()
            payload = _rpc_data(response) or {}
        except Exception as exc:
            report.update(
                status="isolated_publication_failed",
                publishedRoots=len(published),
                failedRootId=root_id,
                reason=f"{type(exc).__name__}: {exc}",
            )
            return EXIT_FAILED, report
        if not isinstance(payload, dict) or payload.get("status") not in ("complete", "noop"):
            report.update(
                status="isolated_publication_failed",
                publishedRoots=len(published),
                failedRootId=root_id,
                reason=f"unexpected atomic publisher result: {payload!r}",
            )
            return EXIT_FAILED, report
        published.append(dict(payload))
        if idx == 1 or idx % 10 == 0 or idx == len(root_ids):
            LOG.info(
                "[price-storage-v2-serving] isolated roots complete=%s/%s",
                idx, len(root_ids),
            )

    isolated = _verify_isolated_cohort(
        client, market_date=day, root_ids=root_ids,
    )
    report["isolatedVerification"] = isolated
    if not isolated["ok"]:
        report.update(
            status="isolated_reconciliation_failed",
            publishedRoots=len(published),
            reason="; ".join(isolated["errors"]),
        )
        return EXIT_FAILED, report

    finalize_response = client.rpc(
        FINALIZE_RPC,
        {"p_market_date": day, "p_root_set_ids": root_ids},
    ).execute()
    finalized = _rpc_data(finalize_response) or {}
    report["compatibilityFinalization"] = finalized
    if not isinstance(finalized, dict) or finalized.get("status") not in ("complete", "noop"):
        report.update(status="compatibility_finalize_failed", reason=f"unexpected result: {finalized!r}")
        return EXIT_FAILED, report

    receipt = _read_receipt(client, day)
    expected_fp = _root_fingerprint(root_ids)
    if (
        not receipt
        or int(receipt.get("root_count") or 0) != len(root_ids)
        or str(receipt.get("root_fingerprint") or "") != expected_fp
    ):
        report.update(
            status="receipt_reconciliation_failed",
            receipt=receipt,
            reason="finalized compatibility receipt does not match canonical root authority",
        )
        return EXIT_FAILED, report

    report.update(
        status="complete",
        publishedRoots=len(published),
        receipt=receipt,
        publicCompatibilityFinalized=True,
        reason="full isolated V2 cohort completed before one atomic compatibility flip",
    )
    return EXIT_OK, report


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Publish Price Storage V2 serving authority")
    result.add_argument("--market-date", required=True, help="Explicit America/Phoenix market date")
    mode = result.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--commit", action="store_true")
    return result


def main() -> int:
    args = parser().parse_args()
    exit_code, report = run(
        get_client(),
        market_date=args.market_date,
        commit=bool(args.commit),
    )
    print(json.dumps(report, indent=2, sort_keys=True, default=str))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
