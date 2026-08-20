"""Market Date Quality - the Market surface's own publication authority.

Deliberately independent of ``public.pokemon_scrape_batches``. The 167-set
batch gate answers "is the whole scrape cohort complete"; this module answers
"is the canonical Market cohort trustworthy for this date". A Market date is
never held hostage by a failure outside the Market cohort.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, Sequence

from backend.db.services.market_run_evidence import qualifying_set_ids_for_date
from backend.db.services.pokemon_market_index_service import resolve_eligible_sets
from backend.domain.pokemon.market_index import deterministic_fingerprint

QUALITY_TABLE = "pokemon_market_date_quality"
SOURCE_TABLE = "pokemon_set_value_daily_history"
PAGE_SIZE = 1000
IN_CHUNK_SIZE = 100

MARKET_QUALITY_CONTRACT_VERSION = "pokemon-market-date-quality-v1"

# Frozen pre-enforcement cutoff. Dates strictly before this may be granted
# LEGACY_VERIFIED through the explicit allowlist below; dates on or after it
# never can, no matter how incomplete their telemetry is.
MARKET_QUALITY_ENFORCEMENT_START = "2026-08-18"

# Explicit historical verification path. Membership is a reviewed decision,
# never an automatic consequence of missing evidence.
LEGACY_VERIFIED_ALLOWLIST_ENV = "MARKET_QUALITY_LEGACY_ALLOWLIST"
DEFAULT_LEGACY_VERIFIED_ALLOWLIST = frozenset({"2026-08-17"})

STATUS_READY = "READY"
STATUS_INCOMPLETE = "INCOMPLETE"
STATUS_DEGRADED = "DEGRADED"
STATUS_LEGACY_VERIFIED = "LEGACY_VERIFIED"

# Statuses whose dates may participate in chain-link math and public authority.
ACCEPTED_STATUSES = frozenset({STATUS_READY, STATUS_LEGACY_VERIFIED})

REQUIRED_VALUE_SCOPES = ("standard", "top10")


def resolve_legacy_allowlist(explicit: Iterable[str] | None = None) -> frozenset[str]:
    if explicit is not None:
        return frozenset(str(day)[:10] for day in explicit)
    raw = os.getenv(LEGACY_VERIFIED_ALLOWLIST_ENV)
    if raw is None:
        return DEFAULT_LEGACY_VERIFIED_ALLOWLIST
    return frozenset(part.strip()[:10] for part in raw.split(",") if part.strip())


def classify_market_date(
    *,
    market_date: str,
    cohort_set_ids: Iterable[str],
    qualifying_set_ids: Iterable[str],
    valuation_set_ids: Mapping[str, Iterable[str]],
    has_later_accepted_date: bool,
    legacy_allowlist: Iterable[str],
) -> dict[str, Any]:
    """Classify one market date. Pure - no I/O, fully determined by its inputs."""
    day = str(market_date)[:10]
    cohort = {str(value) for value in cohort_set_ids}
    qualifying = {str(value) for value in qualifying_set_ids}
    allowlist = {str(value)[:10] for value in legacy_allowlist}

    missing_runs = sorted(cohort - qualifying)
    missing_valuation: dict[str, list[str]] = {}
    for scope in REQUIRED_VALUE_SCOPES:
        present = {str(value) for value in (valuation_set_ids.get(scope) or ())}
        absent = sorted(cohort - present)
        if absent:
            missing_valuation[scope] = absent

    cohort_satisfied = bool(cohort) and not missing_runs and not missing_valuation

    if cohort_satisfied:
        status = STATUS_READY
    elif (day < MARKET_QUALITY_ENFORCEMENT_START
          and day in allowlist
          and not missing_valuation
          and bool(cohort)):
        status = STATUS_LEGACY_VERIFIED
    elif has_later_accepted_date:
        status = STATUS_DEGRADED
    else:
        status = STATUS_INCOMPLETE

    return {
        "marketDate": day,
        "status": status,
        "contractVersion": MARKET_QUALITY_CONTRACT_VERSION,
        "cohortSetCount": len(cohort),
        "qualifyingSetCount": len(cohort & qualifying),
        "missingSetIds": missing_runs,
        "cohortFingerprint": deterministic_fingerprint(sorted(cohort)),
        "evidence": {
            "missingQualifyingRunSetIds": missing_runs,
            "missingValuationSetIds": missing_valuation,
            "enforcementStart": MARKET_QUALITY_ENFORCEMENT_START,
            "preEnforcement": day < MARKET_QUALITY_ENFORCEMENT_START,
            "legacyAllowlisted": day in allowlist,
            "hasLaterAcceptedDate": bool(has_later_accepted_date),
        },
    }


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


def cohort_set_ids_for_date(client: Any, market_date: str) -> list[str]:
    """Canonical Market cohort for a date - the SAME eligibility Market/index uses."""
    day = str(market_date)[:10]
    return sorted(
        str(row["id"]) for row in resolve_eligible_sets(client)
        if not row.get("release_date") or str(row["release_date"])[:10] <= day)


def valuation_set_ids_for_date(
    client: Any, market_date: str, set_ids: Sequence[str]
) -> dict[str, set[str]]:
    """Market valuation inputs present for the date, per required value scope."""
    day = str(market_date)[:10]
    present: dict[str, set[str]] = {scope: set() for scope in REQUIRED_VALUE_SCOPES}
    if not set_ids:
        return present
    ids = list(set_ids)
    for start in range(0, len(ids), IN_CHUNK_SIZE):
        chunk = ids[start:start + IN_CHUNK_SIZE]
        rows = _paged(lambda chunk=chunk: client.table(SOURCE_TABLE)
                      .select("set_id,snapshot_date,set_value,priced_card_count,value_scope")
                      .in_("set_id", chunk)
                      .in_("value_scope", list(REQUIRED_VALUE_SCOPES))
                      .eq("snapshot_date", day)
                      .order("set_id", desc=False))
        for row in rows:
            scope = str(row.get("value_scope") or "")
            if scope not in present:
                continue
            try:
                value = float(row.get("set_value") or 0)
                count = int(row.get("priced_card_count") or 0)
            except (TypeError, ValueError):
                continue
            if value > 0 and count > 0:
                present[scope].add(str(row.get("set_id")))
    return present


def evaluate_market_date_quality(
    client: Any,
    market_date: str,
    *,
    has_later_accepted_date: bool = False,
    legacy_allowlist: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Evaluate one market date from live evidence. Read-only."""
    day = str(market_date)[:10]
    cohort = cohort_set_ids_for_date(client, day)
    return classify_market_date(
        market_date=day,
        cohort_set_ids=cohort,
        qualifying_set_ids=qualifying_set_ids_for_date(client, day),
        valuation_set_ids=valuation_set_ids_for_date(client, day, cohort),
        has_later_accepted_date=has_later_accepted_date,
        legacy_allowlist=resolve_legacy_allowlist(legacy_allowlist),
    )


def persist_market_date_quality(client: Any, evaluation: Mapping[str, Any]) -> int:
    """Upsert the durable diagnostic quality row.

    This is quality STATE, not Market artifact publication - the spec allows it
    even when the date is INCOMPLETE or DEGRADED.
    """
    row = {
        "tcg": "pokemon",
        "market_date": evaluation["marketDate"],
        "status": evaluation["status"],
        "contract_version": evaluation["contractVersion"],
        "cohort_set_count": int(evaluation["cohortSetCount"]),
        "qualifying_set_count": int(evaluation["qualifyingSetCount"]),
        "missing_set_ids": list(evaluation["missingSetIds"]),
        "cohort_fingerprint": evaluation["cohortFingerprint"],
        "evidence_json": dict(evaluation["evidence"]),
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
    }
    client.table(QUALITY_TABLE).upsert(
        [row], on_conflict="tcg,market_date,contract_version").execute()
    return 1


def read_market_date_quality_history(
    client: Any, *, through_date: str | None = None
) -> list[dict[str, Any]]:
    """Read persisted quality history with BOUNDED PAGINATION (Blocker 2).

    PostgREST caps rows per response. An unpaginated read silently truncates
    older dates, which would let a DEGRADED date reappear as unknown-and-
    therefore-accepted. Every page is requested explicitly via .range().
    """
    def query():
        built = (client.table(QUALITY_TABLE).select("*")
                 .eq("tcg", "pokemon")
                 .eq("contract_version", MARKET_QUALITY_CONTRACT_VERSION)
                 .order("market_date", desc=False))
        if through_date:
            built = built.lte("market_date", str(through_date)[:10])
        return built

    return _paged(query)


def accepted_market_dates(
    client: Any, *, through_date: str | None = None
) -> set[str]:
    """Dates whose persisted status permits chain math and public authority."""
    return {
        str(row["market_date"])[:10]
        for row in read_market_date_quality_history(client, through_date=through_date)
        if str(row.get("status") or "") in ACCEPTED_STATUSES
    }


def resolve_latest_accepted_market_date(
    client: Any, *, through_date: str | None = None
) -> str | None:
    """Latest accepted public Market date. A DEGRADED date can never win."""
    accepted = accepted_market_dates(client, through_date=through_date)
    return max(accepted) if accepted else None
