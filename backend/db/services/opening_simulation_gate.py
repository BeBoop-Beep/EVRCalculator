"""Opening-analytics simulation freshness gate.

Context
-------
Market data and opening simulations advance on two different jobs. The daily
scrape batch promotes a market date, and the snapshot builders republish that
market date into ``pokemon_set_market_dashboard_snapshot_latest``. Those
builders do NOT run simulations — they only re-serialize whatever rows already
exist in ``calculation_history_trend`` / ``simulation_run_summary``. So when the
simulation batch stops running, market snapshots keep advancing and the Opening
Profit vs Cost history silently freezes on its last real day while every other
section looks current. That is exactly how production reached market date
2026-07-31 with an OPvC series ending 2026-07-27.

Nothing in the pipeline noticed, because no step ever asked the one question
that separates the two clocks: *does every supported opening set have a valid
simulation for the promoted market date?* This module is that question.

Contract
--------
``calculation_history_trend`` is a view over ``calculation_history_daily_latest``,
whose ``snapshot_date`` is ``calculation_runs.created_at::date`` — the day the
simulation actually ran. Two consequences shape this gate:

* A simulation's date cannot be back-dated. Aligning the simulation date with
  the promoted market date means running the batch on that day, after promotion.
* The view already collapses each (target_type, target_id, snapshot_date) to the
  latest run (``row_number() ... = 1``), so re-running a set on a day it already
  covered replaces its point instead of duplicating it. Reruns are therefore
  idempotent by construction; this module never needs to delete or dedupe rows.

The view LEFT JOINs ``simulation_run_summary``, so a run whose summary row is
missing surfaces as NULL ratios rather than as a missing row. A NULL required
metric is treated as INVALID, never as acceptable — a broken summary join must
not be able to masquerade as a published day.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

_GATE_TAG = "[opening-simulation-gate]"

# Per-set outcomes. Callers branch on these, not on prose.
STATUS_CURRENT = "current"
STATUS_STALE = "stale"
STATUS_MISSING = "missing"
STATUS_INVALID = "invalid"
STATUS_UNSUPPORTED = "unsupported"
STATUS_UNRESOLVED = "unresolved"

# A publishable Opening Profit vs Cost point needs both ratio series; they are
# what the chart draws. p95 is intentionally excluded — the trend view
# back-fills it from the previous day by design.
REQUIRED_OPVC_FIELDS: Tuple[str, ...] = (
    "simulated_mean_pack_value_vs_pack_cost",
    "simulated_median_pack_value_vs_pack_cost",
)


def supported_opening_set_keys() -> Tuple[str, ...]:
    """Canonical set keys eligible for opening analytics.

    Deliberately reuses the SAME definition the simulation batch itself uses
    (``USE_MONTE_CARLO_V2`` on the era set-config maps, see
    ``backend/scripts/run_all_v2_sets.py``) so the gate can never expect a set
    the batch would not run, or ignore one it would.
    """
    from backend.constants.tcg.pokemon.megaEvolutionEra.setMap import (
        SET_CONFIG_MAP as MEGA_EVOLUTION_SET_CONFIG_MAP,
    )
    from backend.constants.tcg.pokemon.scarletAndVioletEra.setMap import (
        SET_CONFIG_MAP as SCARLET_VIOLET_SET_CONFIG_MAP,
    )

    combined = {**SCARLET_VIOLET_SET_CONFIG_MAP, **MEGA_EVOLUTION_SET_CONFIG_MAP}
    keys: List[str] = []
    for set_key, config_cls in combined.items():
        try:
            config = config_cls()
        except Exception:  # pragma: no cover - a broken config must not hide the rest
            logger.warning("%s could not instantiate set config %s", _GATE_TAG, set_key, exc_info=True)
            continue
        if bool(getattr(config, "USE_MONTE_CARLO_V2", False)):
            keys.append(str(set_key))
    return tuple(sorted(keys))


@dataclass
class OpeningSetSimulationStatus:
    """One supported set's simulation freshness verdict for a market date."""

    canonical_key: Optional[str]
    set_id: Optional[str]
    set_name: Optional[str]
    status: str
    latest_simulation_date: Optional[str] = None
    calculation_run_id: Optional[str] = None
    reason: Optional[str] = None

    @property
    def ok(self) -> bool:
        # Explicitly-excepted sets do not block publication.
        return self.status in (STATUS_CURRENT, STATUS_UNSUPPORTED)


@dataclass
class OpeningSimulationFreshnessReport:
    """Aggregate verdict across every supported opening set."""

    market_date: Optional[str]
    statuses: List[OpeningSetSimulationStatus] = field(default_factory=list)
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        # An unreadable authority is a failure, never a pass (fail-closed).
        if self.error is not None:
            return False
        if not self.statuses:
            return False
        return all(status.ok for status in self.statuses)

    def _count(self, *wanted: str) -> int:
        return sum(1 for status in self.statuses if status.status in wanted)

    @property
    def eligible_count(self) -> int:
        return self._count(STATUS_CURRENT, STATUS_STALE, STATUS_MISSING, STATUS_INVALID, STATUS_UNRESOLVED)

    @property
    def current_count(self) -> int:
        return self._count(STATUS_CURRENT)

    @property
    def failed_count(self) -> int:
        return self._count(STATUS_STALE, STATUS_MISSING, STATUS_INVALID, STATUS_UNRESOLVED)

    @property
    def skipped_count(self) -> int:
        return self._count(STATUS_UNSUPPORTED)

    @property
    def failures(self) -> List[OpeningSetSimulationStatus]:
        return [status for status in self.statuses if not status.ok]

    def report_lines(self, *, entry_point: str) -> List[str]:
        """Structured, greppable summary for job logs and Slack."""
        lines = [
            f"{_GATE_TAG} entry_point={entry_point!r} market_date={self.market_date} "
            f"eligible={self.eligible_count} current={self.current_count} "
            f"failed={self.failed_count} skipped={self.skipped_count} ok={self.ok}"
        ]
        if self.error:
            lines.append(f"{_GATE_TAG} authority_error={self.error}")
        for status in sorted(self.statuses, key=lambda item: (item.status, item.canonical_key or "")):
            lines.append(
                f"{_GATE_TAG} set={status.canonical_key or status.set_id} "
                f"name={status.set_name!r} status={status.status} "
                f"latest_simulation_date={status.latest_simulation_date} "
                f"reason={status.reason or '-'}"
            )
        return lines


def _to_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _date_key(value: Any) -> Optional[str]:
    text = _to_text(value)
    return text[:10] if text else None


def resolve_supported_opening_sets(
    client: Any,
    *,
    canonical_keys: Optional[Sequence[str]] = None,
) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """Look up the DB rows for the supported opening-analysis set keys.

    Returns ``(rows, error)``. A key with no matching row is reported by the
    caller as UNRESOLVED rather than quietly dropped — a set that has fallen out
    of the ``sets`` table is a real problem, not an absence of one.
    """
    keys = list(canonical_keys) if canonical_keys is not None else list(supported_opening_set_keys())
    if not keys:
        return [], "no supported opening sets are configured"
    try:
        result = (
            client.table("sets")
            .select("id,name,canonical_key")
            .in_("canonical_key", keys)
            .execute()
        )
        return list((result.data if result else []) or []), None
    except Exception as exc:  # pragma: no cover - exercised via the error path test
        logger.warning("%s supported set lookup failed", _GATE_TAG, exc_info=True)
        return [], f"supported set lookup failed ({exc})"


# PostgREST caps an unpaged response (1000 rows by default) and returns the
# truncated page WITHOUT signalling truncation. The full set-level history is
# already larger than that, so an unpaged read makes whichever sets fall past
# the cap look like they have no simulation history at all — a false MISSING
# verdict, which is exactly the kind of silent data loss this gate exists to
# catch. Always page to exhaustion.
_PAGE_SIZE = 1000


def _load_simulation_rows(
    client: Any,
    set_ids: Sequence[str],
) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    if not set_ids:
        return [], None

    columns = "snapshot_date,target_id,calculation_run_id," + ",".join(REQUIRED_OPVC_FIELDS)
    rows: List[Dict[str, Any]] = []
    offset = 0
    try:
        while True:
            query = (
                client.table("calculation_history_trend")
                .select(columns)
                .eq("target_type", "set")
                .in_("target_id", list(set_ids))
            )
            # A stable sort is what makes the pages disjoint.
            query = query.order("snapshot_date", desc=False)
            page_query = getattr(query, "range", None)
            if page_query is None:
                # Client stub without range() support (unit fakes): one read.
                result = query.execute()
                return list((result.data if result else []) or []), None
            result = query.range(offset, offset + _PAGE_SIZE - 1).execute()
            page = list((result.data if result else []) or [])
            rows.extend(page)
            if len(page) < _PAGE_SIZE:
                return rows, None
            offset += _PAGE_SIZE
    except Exception as exc:
        logger.warning("%s simulation history read failed", _GATE_TAG, exc_info=True)
        return [], f"simulation history read failed ({exc})"


def _load_summary_run_ids(client: Any, run_ids: Sequence[str]) -> Tuple[set, Optional[str]]:
    if not run_ids:
        return set(), None
    try:
        result = (
            client.table("simulation_run_summary")
            .select("calculation_run_id")
            .in_("calculation_run_id", list(run_ids))
            .execute()
        )
        rows = list((result.data if result else []) or [])
        return {text for row in rows if (text := _to_text(row.get("calculation_run_id")))}, None
    except Exception as exc:
        logger.warning("%s simulation run summary read failed", _GATE_TAG, exc_info=True)
        return set(), f"simulation run summary read failed ({exc})"


def _classify(
    *,
    row: Optional[Dict[str, Any]],
    latest_date: Optional[str],
    market_date: str,
    summary_run_ids: set,
) -> Tuple[str, Optional[str], Optional[str]]:
    """Return (status, reason, calculation_run_id) for one set."""
    if row is None:
        if latest_date is None:
            return STATUS_MISSING, "no simulation history exists for this set", None
        return (
            STATUS_STALE,
            f"latest simulation is {latest_date}, behind the promoted market date {market_date}",
            None,
        )

    run_id = _to_text(row.get("calculation_run_id"))
    if not run_id:
        return STATUS_INVALID, "history point has no calculation_run_id", None
    if run_id not in summary_run_ids:
        return (
            STATUS_INVALID,
            f"calculation_run_id {run_id} has no simulation_run_summary row",
            run_id,
        )

    missing_fields = [field_name for field_name in REQUIRED_OPVC_FIELDS if row.get(field_name) is None]
    if missing_fields:
        return (
            STATUS_INVALID,
            "required Opening Profit vs Cost metrics are null: " + ", ".join(sorted(missing_fields)),
            run_id,
        )

    return STATUS_CURRENT, None, run_id


def evaluate_opening_simulation_freshness(
    client: Any,
    *,
    market_date: Any,
    canonical_keys: Optional[Sequence[str]] = None,
    unsupported_keys: Iterable[str] = (),
) -> OpeningSimulationFreshnessReport:
    """Verify every supported opening set has a valid simulation for ``market_date``.

    ``unsupported_keys`` is the explicit exception list for sets intentionally
    excluded from opening analytics; they are reported as skipped-with-reason
    and never block publication.
    """
    resolved_market_date = _date_key(market_date)
    excepted = {str(key) for key in unsupported_keys}

    if not resolved_market_date:
        return OpeningSimulationFreshnessReport(
            market_date=None,
            error="no promoted market date was resolved; refusing to evaluate freshness",
        )

    expected_keys = list(canonical_keys) if canonical_keys is not None else list(supported_opening_set_keys())
    set_rows, lookup_error = resolve_supported_opening_sets(client, canonical_keys=expected_keys)
    if lookup_error:
        return OpeningSimulationFreshnessReport(market_date=resolved_market_date, error=lookup_error)

    rows_by_key = {
        key: row
        for row in set_rows
        if (key := _to_text(row.get("canonical_key")))
    }

    set_ids = [text for row in set_rows if (text := _to_text(row.get("id")))]
    simulation_rows, history_error = _load_simulation_rows(client, set_ids)
    if history_error:
        return OpeningSimulationFreshnessReport(market_date=resolved_market_date, error=history_error)

    # Latest point per set, plus the point that lands exactly on the market date.
    latest_by_set: Dict[str, str] = {}
    on_date_by_set: Dict[str, Dict[str, Any]] = {}
    for row in simulation_rows:
        target_id = _to_text(row.get("target_id"))
        snapshot_date = _date_key(row.get("snapshot_date"))
        if not target_id or not snapshot_date:
            continue
        if snapshot_date > latest_by_set.get(target_id, ""):
            latest_by_set[target_id] = snapshot_date
        if snapshot_date == resolved_market_date:
            on_date_by_set[target_id] = row

    candidate_run_ids = [
        text for row in on_date_by_set.values() if (text := _to_text(row.get("calculation_run_id")))
    ]
    summary_run_ids, summary_error = _load_summary_run_ids(client, candidate_run_ids)
    if summary_error:
        return OpeningSimulationFreshnessReport(market_date=resolved_market_date, error=summary_error)

    statuses: List[OpeningSetSimulationStatus] = []
    for canonical_key in sorted(expected_keys):
        if canonical_key in excepted:
            statuses.append(
                OpeningSetSimulationStatus(
                    canonical_key=canonical_key,
                    set_id=_to_text((rows_by_key.get(canonical_key) or {}).get("id")),
                    set_name=_to_text((rows_by_key.get(canonical_key) or {}).get("name")),
                    status=STATUS_UNSUPPORTED,
                    reason="explicitly excepted from opening analytics",
                )
            )
            continue

        set_row = rows_by_key.get(canonical_key)
        if not set_row:
            statuses.append(
                OpeningSetSimulationStatus(
                    canonical_key=canonical_key,
                    set_id=None,
                    set_name=None,
                    status=STATUS_UNRESOLVED,
                    reason="no row in sets matches this canonical key",
                )
            )
            continue

        set_id = _to_text(set_row.get("id"))
        status_value, reason, run_id = _classify(
            row=on_date_by_set.get(set_id or ""),
            latest_date=latest_by_set.get(set_id or ""),
            market_date=resolved_market_date,
            summary_run_ids=summary_run_ids,
        )
        statuses.append(
            OpeningSetSimulationStatus(
                canonical_key=canonical_key,
                set_id=set_id,
                set_name=_to_text(set_row.get("name")),
                status=status_value,
                latest_simulation_date=latest_by_set.get(set_id or ""),
                calculation_run_id=run_id,
                reason=reason,
            )
        )

    return OpeningSimulationFreshnessReport(market_date=resolved_market_date, statuses=statuses)


def sets_needing_simulation(report: OpeningSimulationFreshnessReport) -> List[str]:
    """Canonical keys the orchestrator must (re)run for the market date.

    A set already CURRENT is skipped, which is what makes re-running the
    orchestrator for the same date cheap and side-effect free.
    """
    return [
        status.canonical_key
        for status in report.statuses
        if status.status in (STATUS_STALE, STATUS_MISSING, STATUS_INVALID) and status.canonical_key
    ]
