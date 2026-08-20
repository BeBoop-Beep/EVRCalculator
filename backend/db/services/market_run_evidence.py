"""Qualifying exact-date reconciliation run evidence for the Market surface.

Mirrors the SQL predicate in
``20260819210000_add_successful_run_reconciliation_repair.sql`` so Python and
Postgres agree on what "qualifying" means.

Set identity authority order (Blocker 3):

1. ``queue_job_id`` -> ``scrape_jobs.set_id`` when the run carries a queue link.
   A run WITH a link that does not resolve is rejected outright - it is not
   downgraded to the weaker fallback.
2. otherwise the run's own explicit ``metadata.set_id``.

Identity is never inferred from names or fuzzy matching. In particular
``metadata.set_filter`` is an operator-supplied filter list, not a set
identity, and is deliberately NOT consulted.
"""

from __future__ import annotations

import math
from typing import Any, Mapping, Sequence

QUALIFYING_JOB_NAME = "pokemon_set_scrape"
QUALIFYING_SOURCE_SYSTEM = "tcgplayer"
QUALIFYING_JOB_TYPE = "price_scrape"
QUALIFYING_ENTITY_TYPE = "set"
QUALIFYING_STATUS = "success"

PAGE_SIZE = 1000
IN_CHUNK_SIZE = 100


def _number(value: Any) -> float | None:
    """Strict numeric coercion. Booleans and non-numeric text are not numbers."""
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _int(value: Any) -> int | None:
    number = _number(value)
    return None if number is None else int(number)


def run_metrics_qualify(run: Mapping[str, Any]) -> bool:
    """True when a run row satisfies the full qualifying-run contract."""
    if str(run.get("job_name") or "") != QUALIFYING_JOB_NAME:
        return False
    if str(run.get("source_system") or "") != QUALIFYING_SOURCE_SYSTEM:
        return False
    if str(run.get("job_type") or "") != QUALIFYING_JOB_TYPE:
        return False
    if str(run.get("entity_type") or "") != QUALIFYING_ENTITY_TYPE:
        return False
    if str(run.get("status") or "").strip().lower() != QUALIFYING_STATUS:
        return False

    succeeded = _int(run.get("items_succeeded"))
    failed = _int(run.get("items_failed"))
    if succeeded is None or succeeded < 1:
        return False
    if failed is None or failed != 0:
        return False

    metadata = run.get("metadata")
    if not isinstance(metadata, Mapping):
        return False
    coverage = _number(metadata.get("sourceCoverageRatio"))
    accepted = _number(metadata.get("acceptedVariantGroups"))
    positive = _number(metadata.get("positiveNmObservationCount"))
    if coverage is None or accepted is None or positive is None:
        return False
    return coverage == 1.0 and accepted > 0 and positive >= accepted


def resolve_run_set_id(
    run: Mapping[str, Any],
    queue_job_set_ids: Mapping[Any, str],
) -> str | None:
    """Resolve the exact set a run is authoritative for, or None."""
    queue_job_id = run.get("queue_job_id")
    if queue_job_id is not None:
        resolved = queue_job_set_ids.get(queue_job_id)
        return str(resolved) if resolved else None

    metadata = run.get("metadata")
    if not isinstance(metadata, Mapping):
        return None
    explicit = metadata.get("set_id")
    if explicit is None:
        return None
    text = str(explicit).strip()
    return text or None


def _paged(query_factory) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    offset = 0
    while True:
        page = list(
            (query_factory().range(offset, offset + PAGE_SIZE - 1).execute()).data or [])
        rows.extend(dict(row) for row in page)
        if len(page) < PAGE_SIZE:
            return rows
        offset += PAGE_SIZE


def _load_runs_for_date(client: Any, market_date: str) -> list[dict[str, Any]]:
    return _paged(lambda: client.table("scrape_job_runs")
                  .select("id,queue_job_id,market_date,job_name,source_system,job_type,"
                          "entity_type,status,items_succeeded,items_failed,metadata")
                  .eq("market_date", market_date)
                  .eq("job_name", QUALIFYING_JOB_NAME)
                  .eq("source_system", QUALIFYING_SOURCE_SYSTEM)
                  .eq("job_type", QUALIFYING_JOB_TYPE)
                  .eq("entity_type", QUALIFYING_ENTITY_TYPE)
                  .eq("status", QUALIFYING_STATUS)
                  .order("id", desc=False))


def _load_queue_job_set_ids(client: Any, job_ids: Sequence[Any]) -> dict[Any, str]:
    if not job_ids:
        return {}
    unique = list(dict.fromkeys(job_ids))
    resolved: dict[Any, str] = {}
    for start in range(0, len(unique), IN_CHUNK_SIZE):
        chunk = unique[start:start + IN_CHUNK_SIZE]
        rows = _paged(lambda chunk=chunk: client.table("scrape_jobs")
                      .select("id,set_id").in_("id", chunk).order("id", desc=False))
        for row in rows:
            if row.get("set_id"):
                resolved[row["id"]] = str(row["set_id"])
    return resolved


def qualifying_set_ids_for_date(client: Any, market_date: str) -> set[str]:
    """Set ids with a qualifying exact-date reconciliation run on market_date."""
    day = str(market_date)[:10]
    runs = [row for row in _load_runs_for_date(client, day)
            if str(row.get("market_date") or "")[:10] == day and run_metrics_qualify(row)]
    queue_job_set_ids = _load_queue_job_set_ids(
        client, [row.get("queue_job_id") for row in runs
                 if row.get("queue_job_id") is not None])
    resolved: set[str] = set()
    for row in runs:
        set_id = resolve_run_set_id(row, queue_job_set_ids)
        if set_id:
            resolved.add(set_id)
    return resolved
