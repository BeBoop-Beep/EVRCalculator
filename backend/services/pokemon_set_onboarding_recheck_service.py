"""Bounded scheduled recheck of already-known Pokemon set onboarding identities.

Distinct from `pokemon_new_set_discovery_service`: discovery finds NEW provider
identities; this module re-observes availability for identities the queue already
knows about (via `list_pokemon_set_onboarding_rechecks_v2`) and reconciles fresh
provider evidence onto them through `reconcile_pokemon_set_onboarding_discovery_v2`
without ever touching workflow status/current_step for an existing job.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import requests

from backend.db.repositories import pokemon_set_onboarding_repository as jobs
from backend.services.tcgplayer_set_catalog_service import ThrottledRequester, build_priceguide_urls
from backend.Scraper.helpers.card_helper import classify_raw_card_row

SOURCE_SYSTEM = "tcgplayer"
DEFAULT_RECHECK_INTERVAL_HOURS = 24.0


@dataclass
class RecheckSummary:
    status: str = "ok"
    source_system: str = SOURCE_SYSTEM
    due_checked: int = 0
    reconciled: int = 0
    provider_errors: int = 0
    dry_run: bool = True
    error: Optional[str] = None


def _fetch_listing_count(requester: ThrottledRequester, url: str, label: str) -> Optional[int]:
    """Provider/network failure returns None (unknown), never 0."""
    response = requester.safe_request("GET", url, label)
    if response is None or response.status_code != 200:
        return None
    try:
        payload = response.json()
    except ValueError:
        return None
    result = payload.get("result")
    if not isinstance(result, list):
        return None
    return len(result)


def _fetch_listing_rows(
    requester: ThrottledRequester, url: str, label: str,
) -> Optional[List[Dict[str, Any]]]:
    """Fetch the raw provider row list. Provider/network/parse failure returns None
    (unknown), never an empty list standing in for genuine zero."""
    response = requester.safe_request("GET", url, label)
    if response is None or response.status_code != 200:
        return None
    try:
        payload = response.json()
    except ValueError:
        return None
    result = payload.get("result")
    if not isinstance(result, list):
        return None
    return result


# card_catalog_status values, in order of precedence.
_STATUS_UNKNOWN = "unknown"           # provider/network failure: rows themselves unavailable
_STATUS_EMPTY = "empty"               # provider genuinely lists zero raw card rows
_STATUS_CODE_CARDS_ONLY = "code_cards_only"        # every raw row is a code card
_STATUS_NO_PROCESSABLE_ROWS = "no_processable_rows"  # zero processable, not all code cards
_STATUS_MIXED = "mixed"               # some rows processable, some excluded
_STATUS_OK = "ok"                     # every raw row is processable


def _card_quality_evidence(rows: Optional[List[Dict[str, Any]]]) -> Dict[str, Any]:
    """Distinguish RAW provider card rows from PROCESSABLE card rows using the same
    shared scraper classification rule (classify_raw_card_row) the parser itself
    applies -- never a duplicated/parallel validity rule.

    rows=None means the provider fetch itself failed: every count here is None
    (unknown), not 0, and card_catalog_status is "unknown" -- distinct from a
    genuine empty/all-excluded catalog.
    """
    if rows is None:
        return {
            "raw_card_listing_count": None,
            "processable_card_listing_count": None,
            "excluded_code_card_count": None,
            "excluded_missing_required_count": None,
            "card_catalog_status": _STATUS_UNKNOWN,
        }

    raw_count = len(rows)
    reasons = Counter(classify_raw_card_row(row) for row in rows)
    processable = reasons.get("processable", 0)
    code_card = reasons.get("code_card", 0)
    missing_required = reasons.get("missing_required_field", 0)

    if raw_count == 0:
        status = _STATUS_EMPTY
    elif processable == raw_count:
        status = _STATUS_OK
    elif processable == 0 and code_card == raw_count:
        status = _STATUS_CODE_CARDS_ONLY
    elif processable == 0:
        status = _STATUS_NO_PROCESSABLE_ROWS
    else:
        status = _STATUS_MIXED

    return {
        "raw_card_listing_count": raw_count,
        "processable_card_listing_count": processable,
        "excluded_code_card_count": code_card,
        "excluded_missing_required_count": missing_required,
        "card_catalog_status": status,
    }


def _propose_disposition(row: Dict[str, Any], observed_at: datetime) -> str:
    """Client-side best guess at the reconcile RPC's disposition, for dry-run reporting
    only. list_rechecks_v2 only ever returns already-known identities, so the real
    dispositions in play are observed_existing (fresh evidence accepted) and
    stale_observation_ignored (this observation isn't newer than what's stored)."""
    last_checked = row.get("provider_last_checked_at")
    if not last_checked:
        return "observed_existing"
    try:
        last_checked_at = datetime.fromisoformat(str(last_checked).replace("Z", "+00:00"))
    except ValueError:
        return "observed_existing"
    return "stale_observation_ignored" if observed_at <= last_checked_at else "observed_existing"


def _listing_count_changed(previous: Any, current: Any) -> bool:
    """True only for a real observed availability change.

    Provider failure (current=None) is never a change. A previously unknown count
    becomes actionable only when the provider now exposes at least one row, so
    first observation of a genuine zero does not cause a needless catalog scrape.
    """
    if current is None:
        return False
    try:
        current_count = int(current)
    except (TypeError, ValueError):
        return False
    if previous is None:
        return current_count > 0
    try:
        return int(previous) != current_count
    except (TypeError, ValueError):
        return current_count > 0


def _availability_change_evidence(row: Dict[str, Any], checked: Dict[str, Any]) -> Dict[str, Any]:
    prior_discovery = row.get("provider_discovery_json")
    if not isinstance(prior_discovery, dict):
        prior_discovery = {}

    previous_card_count = row.get("provider_card_listing_count")
    previous_sealed_count = row.get("provider_sealed_listing_count")
    previous_processable = prior_discovery.get("processable_card_listing_count")
    current_processable = (checked.get("card_quality") or {}).get("processable_card_listing_count")

    processable_became_available = False
    if current_processable is not None:
        try:
            current_processable_int = int(current_processable)
            previous_processable_int = (
                int(previous_processable) if previous_processable is not None else None
            )
            processable_became_available = (
                current_processable_int > 0 and previous_processable_int == 0
            )
        except (TypeError, ValueError):
            processable_became_available = False

    card_count_changed = _listing_count_changed(
        previous_card_count, checked.get("card_listing_count")
    )
    sealed_count_changed = _listing_count_changed(
        previous_sealed_count, checked.get("sealed_listing_count")
    )
    return {
        "previous_card_listing_count": previous_card_count,
        "previous_sealed_listing_count": previous_sealed_count,
        "previous_processable_card_listing_count": previous_processable,
        "card_listing_count_changed": card_count_changed,
        "sealed_listing_count_changed": sealed_count_changed,
        "processable_cards_became_available": processable_became_available,
        "availability_changed": bool(
            card_count_changed or sealed_count_changed or processable_became_available
        ),
    }


def _check_one_identity(
    requester: ThrottledRequester, row: Dict[str, Any],
) -> Dict[str, Any]:
    source_set_id = str(row.get("source_set_id"))
    source_set_name = str(row.get("source_set_name") or source_set_id)
    try:
        set_id = int(source_set_id)
    except (TypeError, ValueError):
        set_id = None

    card_listing_count: Optional[int] = None
    sealed_listing_count: Optional[int] = None
    provider_error: Optional[str] = None
    card_quality = _card_quality_evidence(None)

    if set_id is None:
        provider_error = "unresolvable_identity"
    else:
        card_url, sealed_url = build_priceguide_urls(set_id)
        card_rows = _fetch_listing_rows(requester, card_url, f"recheck cards set {set_id}")
        # provider_card_listing_count is preserved unchanged: the RAW provider card
        # count (not the processable count) -- the same value this field has always
        # held. classify_raw_card_row only adds evidence alongside it.
        card_listing_count = len(card_rows) if card_rows is not None else None
        card_quality = _card_quality_evidence(card_rows)
        sealed_listing_count = _fetch_listing_count(requester, sealed_url, f"recheck sealed set {set_id}")
        if card_listing_count is None and sealed_listing_count is None:
            provider_error = "provider_unreachable"

    return {
        "source_set_id": source_set_id, "source_set_name": source_set_name,
        "card_listing_count": card_listing_count, "sealed_listing_count": sealed_listing_count,
        "provider_error": provider_error, "card_quality": card_quality,
        # reconcile_discovery_v2 only accepts 'detected' or 'manual_review' for
        # p_candidate_status (confirmed live: any other value raises P0001), and that
        # vocabulary is unrelated to the job's own workflow status ("completed",
        # "waiting", etc.) which must never be passed here. A recheck always concerns an
        # already-validated stable identity re-observed for availability, never a fresh
        # ambiguous candidate, so "detected" is the only correct value.
        "candidate_status": "detected",
    }


def run_recheck(
    *, commit: bool, source_system: str = SOURCE_SYSTEM, limit: int = 25,
    provider_timeout_seconds: float = 10.0,
    recheck_interval_hours: float = DEFAULT_RECHECK_INTERVAL_HOURS,
    max_provider_requests: Optional[int] = None,
    session: Optional[requests.Session] = None, as_of: Optional[str] = None,
    due_rows: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Query due identities and reconcile fresh provider evidence.

    Bounded by `limit` (the RPC's own p_limit, capping rows read) AND by
    `max_provider_requests` (defaults to 2x limit — one card + one sealed request per
    identity), an independent client-side ceiling on outbound provider calls so a
    pathological/misconfigured `limit` can't turn one invocation into an unbounded
    scrape.
    """
    limit = max(1, limit)
    summary = RecheckSummary(dry_run=not commit, source_system=source_system)
    if due_rows is None:
        try:
            due = jobs.list_rechecks_v2(source_system=source_system, limit=limit, as_of=as_of)
        except Exception as exc:
            return {**asdict(summary), "status": "retryable_database_error", "error": str(exc)}
    else:
        # The catalog refresh orchestrator may pre-filter due identities against
        # current set lifecycle state (for example, to remove identities that
        # graduated from catalog_only into the normal daily scrape cohort).
        # Preserve the same hard row bound even for caller-supplied rows.
        due = list(due_rows)[:limit]

    requester = ThrottledRequester(
        session or requests.Session(), timeout_seconds=max(0.1, provider_timeout_seconds)
    )
    request_budget = max_provider_requests if max_provider_requests is not None else 2 * limit
    now = datetime.now(timezone.utc)
    next_check_at = (now + timedelta(hours=max(0.1, recheck_interval_hours))).isoformat()

    items: list[Dict[str, Any]] = []
    requests_spent = 0
    for row in due:
        if requests_spent >= request_budget:
            break
        summary.due_checked += 1
        checked = _check_one_identity(requester, row)
        requests_spent += 2 if checked["source_set_id"].lstrip("-").isdigit() else 0
        if checked["provider_error"]:
            summary.provider_errors += 1

        change_evidence = _availability_change_evidence(row, checked)
        discovery_json = {
            "mode": "recheck",
            "provider_card_listing_count": checked["card_listing_count"],
            "provider_sealed_listing_count": checked["sealed_listing_count"],
            "provider_last_checked_at": now.isoformat(),
            "provider_next_check_at": next_check_at,
            "provider_error": checked["provider_error"],
            **checked["card_quality"],
            "availability_changed": change_evidence["availability_changed"],
            "card_listing_count_changed": change_evidence["card_listing_count_changed"],
            "sealed_listing_count_changed": change_evidence["sealed_listing_count_changed"],
            "processable_cards_became_available": change_evidence["processable_cards_became_available"],
        }

        disposition = _propose_disposition(row, now)
        if commit:
            reconciled = jobs.reconcile_discovery_v2(
                source_system=source_system, source_set_id=checked["source_set_id"],
                source_set_name=checked["source_set_name"],
                candidate_status=checked["candidate_status"], discovery_json=discovery_json,
                observed_at=now.isoformat(), next_check_at=next_check_at,
                card_listing_count=checked["card_listing_count"],
                sealed_listing_count=checked["sealed_listing_count"],
            )
            disposition = (reconciled or {}).get("disposition") or disposition
            summary.reconciled += 1

        items.append({
            "job_id": row.get("job_id") or row.get("id"),
            **checked,
            **change_evidence,
            "proposed_next_check_at": next_check_at,
            "proposed_reconcile_disposition": disposition,
            "discovery_json": discovery_json,
        })

    return {**asdict(summary), "identities": items}
