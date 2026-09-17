"""Resilient runtime wrapper for the canonical Pokemon market publication audit.

The canonical audit owns all business rules and verdict semantics. This module
only hardens its I/O path for scheduled/offline execution:

* every PostgREST execute is retried only when the shared data-service classifier
  says the failure is transient, with a fresh service-role client per attempt;
* the very large Cards snapshot is read metadata-first, and ``cards_json`` is
  fetched only for the exceptional rows whose compact metadata cannot establish
  their own market date.

No verdict is weakened. If a surface is stale, malformed, or missing, the
canonical audit still fails closed exactly as before.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, Sequence, Tuple

from backend.db.clients.supabase_client import create_service_role_client
from backend.scripts import audit_pokemon_market_publication as core
from backend.scripts.snapshot_query_retry import run_snapshot_operation_with_retry


logger = logging.getLogger(__name__)
_ORIGINAL_LOAD_ROWS = core._load_rows
_CARDS_TABLE = "pokemon_set_cards_snapshot_latest"
_CARDS_HEAVY_COLUMNS = "set_id,payload_json,cards_json,card_count,updated_at"
_CARDS_META_COLUMNS = "set_id,payload_meta:payload_json->meta,card_count,updated_at"


class _RetryingQuery:
    """Replay a Supabase query against a fresh client for each retry attempt."""

    def __init__(self, table: str):
        self.table_name = table
        self._operations: List[Tuple[str, Tuple[Any, ...], Dict[str, Any]]] = []
        self._not_next = False

    @property
    def not_(self) -> "_RetryingQuery":
        self._not_next = True
        return self

    def _record(self, name: str, *args: Any, **kwargs: Any) -> "_RetryingQuery":
        if self._not_next:
            name = f"not_.{name}"
            self._not_next = False
        self._operations.append((name, args, kwargs))
        return self

    def select(self, *args: Any, **kwargs: Any) -> "_RetryingQuery":
        return self._record("select", *args, **kwargs)

    def eq(self, *args: Any, **kwargs: Any) -> "_RetryingQuery":
        return self._record("eq", *args, **kwargs)

    def in_(self, *args: Any, **kwargs: Any) -> "_RetryingQuery":
        return self._record("in_", *args, **kwargs)

    def gte(self, *args: Any, **kwargs: Any) -> "_RetryingQuery":
        return self._record("gte", *args, **kwargs)

    def order(self, *args: Any, **kwargs: Any) -> "_RetryingQuery":
        return self._record("order", *args, **kwargs)

    def limit(self, *args: Any, **kwargs: Any) -> "_RetryingQuery":
        return self._record("limit", *args, **kwargs)

    def is_(self, *args: Any, **kwargs: Any) -> "_RetryingQuery":
        return self._record("is_", *args, **kwargs)

    def _execute_once(self, client: Any) -> Any:
        query = client.table(self.table_name)
        for name, args, kwargs in self._operations:
            target = query
            method_name = name
            if name.startswith("not_."):
                target = query.not_
                method_name = name.split(".", 1)[1]
            query = getattr(target, method_name)(*args, **kwargs)
        return query.execute()

    def execute(self) -> Any:
        return run_snapshot_operation_with_retry(
            self._execute_once,
            operation_name=f"market-publication-audit:{self.table_name}",
            client_factory=create_service_role_client,
        )


class RetryingServiceRoleClient:
    """Small Supabase client facade used by the read-only publication audit."""

    def table(self, name: str) -> _RetryingQuery:
        return _RetryingQuery(name)


def _meta_market_date(row: Dict[str, Any]) -> Optional[str]:
    meta = row.get("payload_meta")
    if not isinstance(meta, dict):
        return None
    synthetic = {"payload_json": {"meta": meta}}
    return core.cards_snapshot_market_date(synthetic)


def _runtime_load_rows(
    client: Any,
    table: str,
    columns: str,
    set_ids: Sequence[str],
    *,
    chunk_size: int = 200,
    **filters: Any,
) -> Dict[str, Dict[str, Any]]:
    """Keep canonical chunk semantics, but slim the Cards snapshot read."""

    if table != _CARDS_TABLE or "cards_json" not in columns:
        return _ORIGINAL_LOAD_ROWS(
            client,
            table,
            columns,
            set_ids,
            chunk_size=chunk_size,
            **filters,
        )

    compact = _ORIGINAL_LOAD_ROWS(
        client,
        table,
        _CARDS_META_COLUMNS,
        set_ids,
        chunk_size=max(1, min(chunk_size, 100)),
        **filters,
    )

    rows: Dict[str, Dict[str, Any]] = {}
    fallback_ids: List[str] = []
    for set_id, row in compact.items():
        meta = row.get("payload_meta") if isinstance(row.get("payload_meta"), dict) else {}
        synthetic = dict(row)
        synthetic["payload_json"] = {"meta": meta}
        rows[set_id] = synthetic
        if _meta_market_date(row) is None:
            fallback_ids.append(set_id)

    if fallback_ids:
        # Preserve the canonical last-resort per-card price-date behavior, but
        # isolate the heavy JSON to one exceptional set per response.
        heavy = _ORIGINAL_LOAD_ROWS(
            client,
            table,
            _CARDS_HEAVY_COLUMNS,
            fallback_ids,
            chunk_size=1,
            **filters,
        )
        rows.update(heavy)

    return rows


def run_market_publication_audit(
    *,
    market_date: Optional[str] = None,
    canonical_keys: Optional[Sequence[str]] = None,
    phase: str = core.PHASE_FULL,
) -> core.MarketAuditReport:
    """Run the canonical audit with resilient reads and identical verdict rules."""

    client = RetryingServiceRoleClient()
    previous_loader = core._load_rows
    core._load_rows = _runtime_load_rows
    try:
        return core.run_market_publication_audit(
            client,
            market_date=market_date,
            canonical_keys=canonical_keys,
            phase=phase,
        )
    finally:
        core._load_rows = previous_loader


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = core.build_parser().parse_args(argv)
    report = run_market_publication_audit(
        market_date=args.market_date,
        canonical_keys=args.sets,
        phase=args.phase,
    )

    # Preserve the canonical alerting contract. Targeted --set diagnostics remain
    # operator probes and never claim the whole daily pipeline passed or failed.
    if not args.sets and report.market_date:
        try:
            from backend.alerts.pipeline_alerts import (
                alert_market_audit,
                alert_market_pipeline_complete_if_ready,
                alert_simulation_stage,
            )

            failing = [row.canonical_key or row.set_id or "unknown" for row in report.failed_rows]
            alert_market_audit(
                market_date=report.market_date,
                passed=report.passed,
                failing_surfaces=failing,
                expected_date=report.market_date,
                error=report.error,
            )
            if args.phase == core.PHASE_FULL:
                alert_simulation_stage(
                    market_date=report.market_date,
                    state="complete" if report.passed else "publication_failed",
                    set_count=len(report.rows),
                    final_audit_status="PASS" if report.passed else "FAIL",
                )
            elif args.phase == core.PHASE_POST_SCRAPE:
                # Alert helper only needs the regular service-role client for its
                # own lightweight read/write bookkeeping.
                alert_market_pipeline_complete_if_ready(
                    create_service_role_client(),
                    market_date=report.market_date,
                    audit_passed=report.passed,
                )
        except Exception:  # pragma: no cover - verdict never depends on alerting
            logger.exception("%s failed to queue publication audit alert", core.AUDIT_TAG)

    if args.as_json:
        print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    else:
        for line in core.format_report_lines(report):
            logger.info("%s", line)

    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
