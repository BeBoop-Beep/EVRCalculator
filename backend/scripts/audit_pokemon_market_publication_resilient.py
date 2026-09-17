"""Resilient runtime wrapper for the canonical Pokemon market publication audit.

The canonical audit owns the per-surface truth checks. This runtime layer keeps
those checks production-safe and adapts post-cutover authority contracts that
must match the publishers themselves:

* every PostgREST execute is retried only when the shared data-service classifier
  says the failure is transient, with a fresh service-role client per attempt;
* the very large Cards snapshot is read metadata-first, and ``cards_json`` is
  fetched only for exceptional rows whose compact metadata cannot establish
  their own market date;
* the Set Page snapshot is projected down to only the metadata/summary fields the
  audit actually consumes, instead of fetching the full page payload for the
  entire daily cohort;
* global Market Set Value membership is resolved from the same frozen Market-root
  authority as its publisher, never from opening-simulation eligibility;
* a set-page row's generic ``as_of`` timestamp is never treated as an advertised
  market date. Only explicit market-date fields can participate in the header
  market-freshness check;
* a newly admitted Market root with exactly one current Set Value observation is
  allowed to publish no movement windows yet, matching the Set Value publisher's
  own insufficient-history contract;
* Sealed Market is required to advance to the promoted date only when an
  overview-eligible sealed source observation actually reaches that date. A
  truthfully dated older sealed snapshot does not become a publication failure
  merely because the card-market batch advanced further.

No stale/missing market value is relabelled or waived. The adapters remove audit
contract drift while preserving fail-closed behavior for actual public surfaces.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, Sequence, Tuple

from backend.db.clients.supabase_client import create_service_role_client
from backend.db.services.pokemon_market_rollout_cohort import resolve_market_root_ids
from backend.scripts import audit_pokemon_market_publication as core
from backend.scripts.snapshot_query_retry import run_snapshot_operation_with_retry


logger = logging.getLogger(__name__)
_ORIGINAL_LOAD_ROWS = core._load_rows
_ORIGINAL_AUDIT_GLOBAL_SET_VALUE = core._audit_global_set_value
_ORIGINAL_AUDIT_SEALED = core._audit_sealed

_CARDS_TABLE = "pokemon_set_cards_snapshot_latest"
_CARDS_HEAVY_COLUMNS = "set_id,payload_json,cards_json,card_count,updated_at"
_CARDS_META_COLUMNS = "set_id,payload_meta:payload_json->meta,card_count,updated_at"

_PAGES_TABLE = "pokemon_set_page_snapshot_latest"
_PAGES_COMPACT_COLUMNS = (
    "set_id,"
    "payload_meta:payload_json->meta,"
    "payload_summary:payload_json->summary,"
    "payload_set_value:payload_json->setValue,"
    "title_card_json,market_summary_json,as_of,updated_at"
)
_PAGES_COMPACT_CHUNK_SIZE = 50


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

    def lte(self, *args: Any, **kwargs: Any) -> "_RetryingQuery":
        return self._record("lte", *args, **kwargs)

    def lt(self, *args: Any, **kwargs: Any) -> "_RetryingQuery":
        return self._record("lt", *args, **kwargs)

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


def _compact_page_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """Rehydrate only the payload paths the canonical page audit reads."""

    payload: Dict[str, Any] = {}
    meta = row.get("payload_meta")
    if isinstance(meta, dict):
        payload["meta"] = meta
    summary = row.get("payload_summary")
    if isinstance(summary, dict):
        payload["summary"] = summary
    if row.get("payload_set_value") is not None:
        payload["setValue"] = row.get("payload_set_value")

    synthetic = dict(row)
    synthetic["payload_json"] = payload
    return synthetic


def _runtime_load_rows(
    client: Any,
    table: str,
    columns: str,
    set_ids: Sequence[str],
    *,
    chunk_size: int = 200,
    **filters: Any,
) -> Dict[str, Dict[str, Any]]:
    """Keep canonical semantics while reducing known oversized JSON reads."""

    if table == _PAGES_TABLE and "payload_json" in columns:
        compact = _ORIGINAL_LOAD_ROWS(
            client,
            table,
            _PAGES_COMPACT_COLUMNS,
            set_ids,
            chunk_size=max(1, min(chunk_size, _PAGES_COMPACT_CHUNK_SIZE)),
            **filters,
        )
        return {set_id: _compact_page_row(row) for set_id, row in compact.items()}

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


def _explicit_page_market_date(page_row: Optional[Dict[str, Any]]) -> Optional[str]:
    """Only a market date the page explicitly publishes can vouch for freshness."""

    if not page_row:
        return None
    return core._first_date_at(
        {
            "meta": core._dig(page_row.get("payload_json"), "meta") or {},
            "marketSummary": core._as_obj(page_row.get("market_summary_json")),
            "titleCard": core._as_obj(page_row.get("title_card_json")),
        },
        core.PAGE_SNAPSHOT_DATE_PATHS,
    )


def _runtime_audit_header_summary(
    market_date: str,
    page_row: Optional[Dict[str, Any]],
    sections: Sequence[core.SectionVerdict],
) -> core.SectionVerdict:
    """Audit only an EXPLICIT market date advertised by the Set Page header."""

    verdict = core.SectionVerdict(section=core.SECTION_HEADER_SUMMARY)
    if not page_row:
        verdict.passed = False
        verdict.detail = "no published set page snapshot row"
        return verdict

    header_date = _explicit_page_market_date(page_row)
    verdict.observed_date = header_date
    if header_date is None:
        verdict.applicable = False
        verdict.detail = (
            "set page publishes no explicit market date; row as_of is build/simulation "
            "metadata and is not used as market-date authority"
        )
        return verdict

    if header_date > market_date:
        verdict.passed = False
        verdict.detail = (
            f"header advertises {header_date}, ahead of the promoted market date {market_date}"
        )
        return verdict

    behind = [
        f"{v.section}@{v.observed_date}"
        for v in sections
        if v.applicable and v.observed_date and v.observed_date < header_date
    ]
    if behind:
        verdict.passed = False
        verdict.detail = (
            f"header advertises {header_date} but these sections are older: {', '.join(behind)}"
        )
    return verdict


def _runtime_global_set_value_cohort_ids(client: Any, market_date: str) -> List[str]:
    """Use the same root-membership authority as the global Set Value publisher."""

    return list(resolve_market_root_ids(client, market_date=market_date))


def _runtime_audit_global_set_value(
    market_date: str,
    *,
    target: Optional[Dict[str, Any]],
    canonical_set_value: Optional[float],
    in_cohort: bool,
    snapshot_problem: Optional[str] = None,
) -> core.SectionVerdict:
    """Preserve strict checks while recognizing the publisher's one-point state."""

    verdict = _ORIGINAL_AUDIT_GLOBAL_SET_VALUE(
        market_date,
        target=target,
        canonical_set_value=canonical_set_value,
        in_cohort=in_cohort,
        snapshot_problem=snapshot_problem,
    )
    if verdict.passed or not verdict.applicable or not isinstance(target, dict):
        return verdict
    if not verdict.detail or "missing window metadata" not in verdict.detail:
        return verdict

    try:
        history_point_count = int(target.get("historyPointCount"))
    except (TypeError, ValueError):
        return verdict
    windows = target.get("windows")
    start_date = core._date_key(target.get("historyStartDate"))
    end_date = core._date_key(target.get("historyEndDate"))
    if not (
        history_point_count == 1
        and isinstance(windows, dict)
        and not windows
        and start_date == market_date
        and end_date == market_date
    ):
        return verdict

    # The canonical implementation checks value parity *after* window metadata.
    # Because the one-point adapter is deliberately overriding only that window
    # failure, perform the downstream canonical checks here before allowing the
    # insufficient-history state to pass. Otherwise a mismatched one-point value
    # could be accidentally waived along with its legitimately-empty windows.
    value = core._finite(target.get("currentSetValue") or target.get("current_set_value"))
    if canonical_set_value is None:
        verdict.detail = (
            f"global Set Value advertises a value for {market_date} but no canonical "
            f"standard set-value row exists for that date"
        )
        return verdict
    if value is None or round(value, 2) != round(canonical_set_value, 2):
        verdict.detail = (
            f"global Set Value {round(value, 2) if value is not None else value!r} disagrees with "
            f"the canonical standard set value {round(canonical_set_value, 2)} for {market_date}"
        )
        return verdict

    verdict.passed = True
    verdict.detail = (
        "single-point current Set Value history; movement windows are "
        "legitimately unavailable until a second observation exists"
    )
    return verdict


def _runtime_audit_sealed(
    market_date: str,
    sealed_row: Optional[Dict[str, Any]],
    has_sealed_product: bool,
    *,
    sealed_source_latest_date: Optional[str] = None,
) -> core.SectionVerdict:
    """Do not require a target-day sealed snapshot when the source never reached it."""

    verdict = _ORIGINAL_AUDIT_SEALED(
        market_date,
        sealed_row,
        has_sealed_product,
        sealed_source_latest_date=sealed_source_latest_date,
    )
    if verdict.passed or not verdict.applicable or not has_sealed_product or not sealed_row:
        return verdict

    observed = core._date_key(sealed_row.get("market_date"))
    source_day = core._date_key(sealed_source_latest_date)
    if observed and observed < market_date and (source_day is None or source_day < market_date):
        verdict.passed = True
        verdict.detail = (
            f"overview-eligible sealed source has no observation on/after {market_date}; "
            f"published snapshot remains truthfully dated {observed}"
        )
    return verdict


def run_market_publication_audit(
    *,
    market_date: Optional[str] = None,
    canonical_keys: Optional[Sequence[str]] = None,
    phase: str = core.PHASE_FULL,
) -> core.MarketAuditReport:
    """Run the canonical audit with resilient reads and current authority contracts."""

    client = RetryingServiceRoleClient()
    resolved_market_date = market_date
    if resolved_market_date is None:
        resolved_market_date, _ = core.resolve_promoted_market_date(client)

    previous_loader = core._load_rows
    previous_global_cohort = core.global_set_value_cohort_ids
    previous_header_audit = core._audit_header_summary
    previous_global_audit = core._audit_global_set_value
    previous_sealed_audit = core._audit_sealed
    core._load_rows = _runtime_load_rows
    if resolved_market_date:
        core.global_set_value_cohort_ids = lambda _sets: _runtime_global_set_value_cohort_ids(
            client, resolved_market_date
        )
    core._audit_header_summary = _runtime_audit_header_summary
    core._audit_global_set_value = _runtime_audit_global_set_value
    core._audit_sealed = _runtime_audit_sealed
    try:
        return core.run_market_publication_audit(
            client,
            market_date=market_date,
            canonical_keys=canonical_keys,
            phase=phase,
        )
    finally:
        core._load_rows = previous_loader
        core.global_set_value_cohort_ids = previous_global_cohort
        core._audit_header_summary = previous_header_audit
        core._audit_global_set_value = previous_global_audit
        core._audit_sealed = previous_sealed_audit


def _queue_alerts(report: core.MarketAuditReport, args: Any) -> None:
    """Preserve the canonical audit's alert side effects without affecting verdicts."""

    if args.sets or not report.market_date:
        return
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
            alert_market_pipeline_complete_if_ready(
                create_service_role_client(),
                market_date=report.market_date,
                audit_passed=report.passed,
            )
    except Exception:  # pragma: no cover - verdict never depends on alerting
        logger.exception("%s failed to queue publication audit alert", core.AUDIT_TAG)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = core.build_parser().parse_args(argv)
    report = run_market_publication_audit(
        market_date=args.market_date,
        canonical_keys=args.sets,
        phase=args.phase,
    )
    _queue_alerts(report, args)

    if args.as_json:
        print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    else:
        for line in core.format_report_lines(report):
            logger.info("%s", line)

    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
