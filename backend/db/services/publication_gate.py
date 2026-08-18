"""Batch-cohort gate for downstream public-snapshot promotion (Phase 8).

Downstream read models — Cards, Market Dashboard, set pages, rankings, and
simulation-derived publication — must only promote when the day's scrape cohort
contract is satisfied. The authority is ``public.pokemon_scrape_batches``
(migrations 047–049): a batch stamps ``promoted_at`` and flips ``status`` to
``complete`` only when every expected set has a valid Near Mint observation for
the market date (see ``complete_scrape_batch_if_ready``).

Operating modes
---------------
The gate has explicit operating modes selected by the ``PUBLICATION_GATE_MODE``
environment variable:

* ``required`` (default; used for any commit-capable production command) — the
  gate **fails closed**. Publication is allowed only when a valid batch row
  satisfies the complete promotion contract. Every failure class blocks:
  query timeout, auth/permission failure, PostgREST/network failure, missing
  batch table, missing batch row, malformed response, an inconsistent batch,
  a pending/running/incomplete/failed batch, or any unclassified exception.
* ``disabled`` — ungated. Permitted **only** for explicitly configured
  local/test environments. It is never selected implicitly; a failed database
  operation never disables the gate.

An omitted or invalid mode resolves to ``required`` — the safe default. The
mode is never inferred from a failed database operation.

Manual override
---------------
An explicit ``override`` (wired to ``--force-publish``) promotes without a
satisfied cohort for manual recovery only. It cannot be activated implicitly,
is loudly logged, is represented in the returned decision (``override=True`` /
``reason_code == manual_override``), and is never used by the scheduled command.

Reason codes
------------
Every decision carries a structured ``reason_code`` (see the ``REASON_*``
constants) so callers branch on classification rather than free-form text.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, List, Optional, Tuple

logger = logging.getLogger(__name__)

_GATE_TAG = "[publication-gate]"

# Environment variable selecting the operating mode. Unset or invalid => required.
GATE_MODE_ENV = "PUBLICATION_GATE_MODE"
MODE_REQUIRED = "required"
MODE_DISABLED = "disabled"

# Structured decision classifications. Callers branch on these, not on prose.
REASON_ALLOWED_COMPLETE = "allowed_complete"
REASON_BLOCKED_INCOMPLETE = "blocked_incomplete"
REASON_BLOCKED_NO_BATCH = "blocked_no_batch"
REASON_BLOCKED_AUTHORITY_UNAVAILABLE = "blocked_authority_unavailable"
REASON_BLOCKED_INVALID_BATCH_CONTRACT = "blocked_invalid_batch_contract"
REASON_DISABLED_EXPLICITLY = "disabled_explicitly"
REASON_MANUAL_OVERRIDE = "manual_override"

# Process exit code a gate-aware CLI returns when publication is deferred by a
# closed gate (distinct from a genuine build failure, which exits 1).
GATE_DEFERRED_EXIT_CODE = 3

# Prefix of the single machine-readable deferral line the shell wrapper greps.
DEFERRAL_MARKER = "PUBLICATION_DEFERRED"

# Batch statuses permitted by the status CHECK constraint (migration 047).
_KNOWN_BATCH_STATUSES = frozenset(
    {"pending", "running", "incomplete", "complete", "failed"}
)
# Only an observation-complete cohort qualifies for promotion.
_PROMOTABLE_BATCH_STATUSES = frozenset({"complete"})


@dataclass
class PublicationGateDecision:
    """Outcome of a downstream-publication gate evaluation."""

    allowed: bool
    reason: str
    reason_code: str
    # True when a real batch verdict drove the decision (vs. override/disabled).
    gated: bool
    mode: str = MODE_REQUIRED
    override: bool = False
    market_date: Optional[str] = None
    batch_id: Optional[Any] = None
    batch_status: Optional[str] = None
    missing_set_count: Optional[int] = None
    expected_set_count: Optional[int] = None
    promoted_at: Optional[str] = None


def resolve_gate_mode(explicit: Optional[str] = None) -> str:
    """Resolve the operating mode. Unset/invalid => required (fail-closed).

    ``disabled`` must be chosen explicitly; it is never the fallback for a
    missing or malformed value.
    """
    raw = explicit if explicit is not None else os.getenv(GATE_MODE_ENV)
    text = str(raw or "").strip().lower()
    if text == MODE_DISABLED:
        return MODE_DISABLED
    if text in ("", MODE_REQUIRED):
        return MODE_REQUIRED
    logger.warning(
        "%s invalid %s=%r; defaulting to required (fail-closed)",
        _GATE_TAG,
        GATE_MODE_ENV,
        raw,
    )
    return MODE_REQUIRED


def _to_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _coerce_nonneg_int(value: Any, *, allow_none: bool) -> Tuple[Optional[int], Optional[str]]:
    """Return (int, None) on success or (None, error) on a contract violation."""
    if value is None:
        return (None, None) if allow_none else (None, "is missing")
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None, f"is not an integer ({value!r})"
    if parsed < 0:
        return None, f"is negative ({parsed})"
    return parsed, None


def _latest_batch_row(client: Any, market_date: Optional[str]) -> Optional[dict]:
    query = client.table("pokemon_scrape_batches").select(
        "id,market_date,status,promoted_at,missing_set_count,"
        "expected_set_count,succeeded_set_count,failed_set_count"
    )
    if market_date is not None:
        query = query.eq("market_date", market_date)
    result = query.order("market_date", desc=True).limit(1).execute()
    rows = list((result.data if result else []) or [])
    return rows[0] if rows else None


def _blocked(
    reason: str,
    reason_code: str,
    *,
    mode: str,
    market_date: Optional[str],
    **common: Any,
) -> PublicationGateDecision:
    return PublicationGateDecision(
        allowed=False,
        reason=reason,
        reason_code=reason_code,
        gated=True,
        mode=mode,
        market_date=market_date,
        **common,
    )


def evaluate_publication_gate(
    client: Any,
    *,
    market_date: Optional[str] = None,
    override: bool = False,
    mode: Optional[str] = None,
) -> PublicationGateDecision:
    """Decide whether downstream public snapshots may promote for a market date.

    Read-only: never mutates batch or queue state. Requeue/repair of missing
    sets is the scrape batch pipeline's responsibility
    (``requeue_missing_scrape_jobs_for_batch`` / ``run_batch_completion_and_repair``).

    In ``required`` mode (the production default) every failure class blocks —
    the gate never interprets an error, a missing table, or a missing row as
    permission to publish.
    """
    resolved_mode = resolve_gate_mode(mode)

    # Manual recovery override — explicit only, loudly logged, represented in the
    # decision, and never queries the batch authority.
    if override:
        logger.warning(
            "%s OVERRIDE ENABLED — promoting downstream snapshots WITHOUT a satisfied "
            "batch cohort contract (manual recovery only). market_date=%s",
            _GATE_TAG,
            market_date or "latest",
        )
        return PublicationGateDecision(
            allowed=True,
            reason="manual override: promoting without a satisfied cohort contract",
            reason_code=REASON_MANUAL_OVERRIDE,
            gated=False,
            mode=resolved_mode,
            override=True,
            market_date=market_date,
        )

    # Explicitly disabled — local/test only. Never touches the client.
    if resolved_mode == MODE_DISABLED:
        logger.warning(
            "%s gate DISABLED via %s=disabled; publishing ungated (local/test only)",
            _GATE_TAG,
            GATE_MODE_ENV,
        )
        return PublicationGateDecision(
            allowed=True,
            reason="publication gate explicitly disabled (local/test only)",
            reason_code=REASON_DISABLED_EXPLICITLY,
            gated=False,
            mode=resolved_mode,
            market_date=market_date,
        )

    # required mode — fail closed on every failure class.
    try:
        batch = _latest_batch_row(client, market_date)
    except Exception as exc:
        # Timeout, auth/permission failure, PostgREST/network error, missing
        # batch table, malformed response, or any unclassified exception. A
        # failed query is NEVER permission to publish, and NEVER selects disabled.
        logger.error(
            "%s batch cohort authority unavailable in required mode (%s); BLOCKING "
            "publication (fail-closed)",
            _GATE_TAG,
            exc,
        )
        return _blocked(
            f"batch cohort authority unavailable ({exc}); blocking publication (fail-closed)",
            REASON_BLOCKED_AUTHORITY_UNAVAILABLE,
            mode=resolved_mode,
            market_date=market_date,
        )

    if not batch:
        logger.warning(
            "%s no scrape batch found for market_date=%s in required mode; BLOCKING",
            _GATE_TAG,
            market_date or "latest",
        )
        return _blocked(
            "no scrape batch cohort found; blocking publication (fail-closed)",
            REASON_BLOCKED_NO_BATCH,
            mode=resolved_mode,
            market_date=market_date,
        )

    status = str(batch.get("status") or "").strip().lower()
    resolved_market_date = _to_text(batch.get("market_date"))
    batch_id = batch.get("id")
    missing_count, missing_err = _coerce_nonneg_int(batch.get("missing_set_count"), allow_none=True)
    expected_count, expected_err = _coerce_nonneg_int(batch.get("expected_set_count"), allow_none=True)
    promoted_at = _to_text(batch.get("promoted_at"))

    common = {
        "batch_id": batch_id,
        "batch_status": status,
        "missing_set_count": missing_count,
        "expected_set_count": expected_count,
        "promoted_at": promoted_at,
    }
    resolved_or_requested = resolved_market_date or market_date

    # ---- Structural integrity: the authority row itself must be trustworthy.
    structural: List[str] = []
    if batch_id is None or (isinstance(batch_id, str) and not batch_id.strip()):
        structural.append("batch row has no id")
    if not resolved_market_date:
        structural.append("batch row has no market_date")
    if market_date is not None and resolved_market_date and resolved_market_date != str(market_date):
        structural.append(
            f"requested market_date={market_date} does not match batch market_date={resolved_market_date}"
        )
    if status not in _KNOWN_BATCH_STATUSES:
        structural.append(f"unknown batch status={status or 'empty'!r}")
    if missing_err:
        structural.append(f"missing_set_count {missing_err}")
    if expected_err:
        structural.append(f"expected_set_count {expected_err}")
    if structural:
        detail = "; ".join(structural)
        logger.error(
            "%s promotion BLOCKED — invalid batch contract for market_date=%s: %s",
            _GATE_TAG,
            resolved_or_requested or "latest",
            detail,
        )
        return _blocked(
            f"invalid batch contract: {detail}",
            REASON_BLOCKED_INVALID_BATCH_CONTRACT,
            mode=resolved_mode,
            market_date=resolved_or_requested,
            **common,
        )

    # ---- Not observation-complete yet (pending/running/incomplete/failed).
    if status not in _PROMOTABLE_BATCH_STATUSES:
        logger.warning(
            "%s promotion BLOCKED — batch %s status=%s missing_sets=%s; preserving previous good snapshot",
            _GATE_TAG,
            resolved_market_date,
            status or "unknown",
            missing_count,
        )
        return _blocked(
            f"batch {resolved_market_date} status={status or 'unknown'} is not complete; "
            "preserving previous good public snapshot",
            REASON_BLOCKED_INCOMPLETE,
            mode=resolved_mode,
            market_date=resolved_or_requested,
            **common,
        )

    # ---- status == complete: enforce the full promotion contract. A row that
    # claims complete but contradicts the promotion invariants is blocked and
    # diagnosed, never trusted.
    contract: List[str] = []
    if not promoted_at:
        contract.append("promoted_at is null")
    # For a complete batch the counts must be present and consistent.
    complete_missing, complete_missing_err = _coerce_nonneg_int(
        batch.get("missing_set_count"), allow_none=False
    )
    complete_expected, complete_expected_err = _coerce_nonneg_int(
        batch.get("expected_set_count"), allow_none=False
    )
    if complete_missing_err:
        contract.append(f"missing_set_count {complete_missing_err}")
    elif complete_missing != 0:
        contract.append(f"missing_set_count is {complete_missing} (expected 0)")
    if complete_expected_err:
        contract.append(f"expected_set_count {complete_expected_err}")
    elif complete_expected <= 0:
        contract.append(f"expected_set_count is {complete_expected} (expected > 0)")

    if contract:
        detail = "; ".join(contract)
        logger.error(
            "%s promotion BLOCKED — contradictory complete batch %s: %s",
            _GATE_TAG,
            resolved_market_date,
            detail,
        )
        return _blocked(
            f"batch {resolved_market_date} claims complete but {detail}",
            REASON_BLOCKED_INVALID_BATCH_CONTRACT,
            mode=resolved_mode,
            market_date=resolved_or_requested,
            **common,
        )

    logger.info(
        "%s promotion ALLOWED — batch %s is complete (promoted_at=%s, expected=%s, missing=0)",
        _GATE_TAG,
        resolved_market_date,
        promoted_at,
        complete_expected,
    )
    return PublicationGateDecision(
        allowed=True,
        reason=f"batch {resolved_market_date} is complete; promotion allowed",
        reason_code=REASON_ALLOWED_COMPLETE,
        gated=True,
        mode=resolved_mode,
        market_date=resolved_or_requested,
        **common,
    )


# ---------------------------------------------------------------------------
# Shared CLI enforcement
# ---------------------------------------------------------------------------
# One evaluation per publication invocation, reused for every set. Every
# commit-capable public-snapshot entry point routes through this so the gate is
# enforced consistently and a developer cannot accidentally bypass cohort safety
# by calling a different publisher.


def _latest_complete_batch_row(client: Any) -> Optional[dict]:
    """Newest batch whose status is ``complete``, ignoring newer non-complete rows."""
    query = client.table("pokemon_scrape_batches").select(
        "id,market_date,status,promoted_at,missing_set_count,"
        "expected_set_count,succeeded_set_count,failed_set_count"
    ).eq("status", "complete")
    result = query.order("market_date", desc=True).limit(1).execute()
    rows = list((result.data if result else []) or [])
    return rows[0] if rows else None


def resolve_latest_promoted_market_date(client: Any) -> Tuple[Optional[str], Optional[str]]:
    """Resolve the newest market date that genuinely owns publication authority.

    Returns ``(market_date, None)`` on success or ``(None, error)`` fail-closed.

    A newer INCOMPLETE batch must not hide an older validly promoted one - that
    is the whole point (2026-08-18 incomplete must still resolve 2026-08-17).
    So the candidate is the newest ``status='complete'`` row.

    The candidate is then validated by the canonical
    :func:`evaluate_publication_gate` for that exact date in required mode.
    There is deliberately no second definition of "promoted" here: this helper
    only chooses the candidate; the gate remains the sole authority on whether
    it may publish.

    A contradictory newest-complete row (promoted_at null, missing sets, or a
    non-positive expected count) FAILS CLOSED. It is never skipped in favour of
    an older row - silently publishing an older date because the newest
    authority is corrupt would hide exactly the corruption worth surfacing.
    """
    try:
        candidate = _latest_complete_batch_row(client)
    except Exception as exc:  # network/auth/missing table - never a green light
        logger.error("%s could not read the batch authority: %s", _GATE_TAG, exc)
        return None, f"could not read the scrape batch authority ({exc})"

    if not candidate:
        logger.warning("%s no complete scrape batch exists; nothing is promoted", _GATE_TAG)
        return None, "no complete scrape batch cohort exists; nothing is promoted"

    candidate_date = _to_text(candidate.get("market_date"))
    if not candidate_date:
        return None, "newest complete scrape batch has no market_date"

    decision = evaluate_publication_gate(
        client, market_date=candidate_date, mode=MODE_REQUIRED
    )
    if not decision.allowed:
        logger.error(
            "%s newest complete batch %s failed the canonical promotion contract: %s",
            _GATE_TAG,
            candidate_date,
            decision.reason,
        )
        return None, (
            f"newest complete batch {candidate_date} is not promotable: "
            f"{decision.reason} (reason_code={decision.reason_code})"
        )
    return candidate_date, None


@dataclass
class GateEnforcement:
    """Result of applying the gate to one CLI invocation."""

    decision: PublicationGateDecision
    proceed: bool
    exit_code: int


def gate_decision_report(decision: PublicationGateDecision, *, entry_point: str) -> List[str]:
    """Human + machine readable lines describing a closed/deferred gate.

    Includes one stable ``PUBLICATION_DEFERRED`` line the shell wrapper greps to
    build its Slack warning (market date, batch status, missing-set count).
    """
    return [
        f"{entry_point}: publication gate CLOSED [{decision.reason_code}]: {decision.reason}",
        (
            f"{DEFERRAL_MARKER} entry_point={entry_point!r} "
            f"market_date={decision.market_date or 'unknown'} "
            f"batch_status={decision.batch_status or 'none'} "
            f"missing_set_count={decision.missing_set_count if decision.missing_set_count is not None else 'unknown'} "
            f"reason_code={decision.reason_code}"
        ),
        "preserving previous good public snapshots; no promotion performed",
    ]


def add_publication_gate_args(parser: Any) -> None:
    """Register the shared gate flags on a publishing CLI's argparse parser."""
    parser.add_argument(
        "--market-date",
        help="America/Phoenix market date whose scrape batch gates promotion (default: newest batch)",
    )
    parser.add_argument(
        "--force-publish",
        action="store_true",
        help="Manual-recovery override: promote even when the scrape batch cohort is incomplete (loudly logged)",
    )


def enforce_cli_publication_gate(
    client: Any,
    *,
    commit: bool,
    market_date: Optional[str] = None,
    override: bool = False,
    mode: Optional[str] = None,
    entry_point: str = "public snapshot publication",
) -> GateEnforcement:
    """Evaluate the gate once for a CLI invocation and decide whether to proceed.

    * dry-run (``commit`` False): always proceed read-only, but report what the
      gate decision *would* be.
    * commit + allowed: proceed (a manual override is announced).
    * commit + blocked: do not proceed; return the deferred exit code so the
      caller ``raise SystemExit(enforcement.exit_code)``.
    """
    decision = evaluate_publication_gate(
        client, market_date=market_date, override=override, mode=mode
    )

    if not commit:
        print(
            f"{entry_point}: publication gate decision (dry-run) "
            f"[{decision.reason_code}] allowed={decision.allowed}: {decision.reason}"
        )
        return GateEnforcement(decision=decision, proceed=True, exit_code=0)

    if decision.allowed:
        if decision.override:
            print(
                f"{entry_point}: publication gate OVERRIDDEN (manual recovery) "
                f"[{decision.reason_code}]: {decision.reason}"
            )
        return GateEnforcement(decision=decision, proceed=True, exit_code=0)

    for line in gate_decision_report(decision, entry_point=entry_point):
        print(line)
    return GateEnforcement(
        decision=decision, proceed=False, exit_code=GATE_DEFERRED_EXIT_CODE
    )
