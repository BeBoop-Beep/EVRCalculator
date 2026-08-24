"""Market-only publication gate.

Parallel to - never a replacement for - ``publication_gate.py``. The 167-set
batch gate keeps its authority over RIP/rankings/set-page/non-Market surfaces.
This gate answers one question: may the Market surface publish for a date,
judged solely on the canonical Market cohort?

``--force-publish`` is REJECTED here rather than ignored, so an operator can
never believe they deliberately bypassed Market quality when the flag did
nothing.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, Optional

from backend.db.services.market_date_quality import (
    ACCEPTED_STATUSES,
    STATUS_DEGRADED,
    STATUS_INCOMPLETE,
    STATUS_LEGACY_VERIFIED,
    STATUS_READY,
    evaluate_market_date_quality,
    persist_market_date_quality,
    resolve_latest_accepted_market_date,
    resolve_latest_market_source_date,
)

logger = logging.getLogger(__name__)

_GATE_TAG = "[market-quality-gate]"

MARKET_GATE_DEFERRED_EXIT_CODE = 3
DEFERRAL_MARKER = "PUBLICATION_DEFERRED"

MARKET_FORCE_PUBLISH_REJECTION = (
    "Market Date Quality cannot be overridden with --force-publish")

# Operating mode. DELIBERATELY a different variable from PUBLICATION_GATE_MODE:
# disabling the 167-set batch gate must never silently disable Market quality.
# Unset or invalid resolves to required (fail-closed); "disabled" is local/test
# only and must be chosen explicitly.
MARKET_GATE_MODE_ENV = "MARKET_PUBLICATION_GATE_MODE"
MODE_REQUIRED = "required"
MODE_DISABLED = "disabled"

REASON_DISABLED_EXPLICITLY = "market_disabled_explicitly"
REASON_BLOCKED_AUTHORITY_UNAVAILABLE = "market_blocked_authority_unavailable"
REASON_ALLOWED_READY = "market_allowed_ready"
REASON_ALLOWED_LEGACY_VERIFIED = "market_allowed_legacy_verified"
REASON_BLOCKED_INCOMPLETE = "market_blocked_incomplete"
REASON_BLOCKED_DEGRADED = "market_blocked_degraded"
REASON_BLOCKED_NO_EVIDENCE = "market_blocked_no_quality_evidence"

_REASON_BY_STATUS = {
    STATUS_READY: REASON_ALLOWED_READY,
    STATUS_LEGACY_VERIFIED: REASON_ALLOWED_LEGACY_VERIFIED,
    STATUS_INCOMPLETE: REASON_BLOCKED_INCOMPLETE,
    STATUS_DEGRADED: REASON_BLOCKED_DEGRADED,
}


class MarketForcePublishRejected(SystemExit):
    """Raised when --force-publish is aimed at a Market quality-gated command."""

    def __init__(self, message: str = MARKET_FORCE_PUBLISH_REJECTION):
        super().__init__(message)
        self.message = message

    def __str__(self) -> str:
        return self.message


@dataclass
class MarketGateDecision:
    allowed: bool
    status: str
    market_date: Optional[str]
    reason: str
    reason_code: str
    evaluation: Optional[dict] = None


@dataclass
class MarketGateEnforcement:
    decision: MarketGateDecision
    proceed: bool
    exit_code: int


def add_market_gate_args(parser: Any) -> None:
    """Register Market gate flags, tolerating a parser that already has them."""
    existing = {action.dest for action in getattr(parser, "_actions", [])}
    if "market_date" not in existing:
        parser.add_argument(
            "--market-date",
            help="America/Phoenix market date whose Market Date Quality gates publication")


def resolve_market_gate_mode(explicit: Optional[str] = None) -> str:
    """Resolve the operating mode. Unset/invalid => required (fail-closed)."""
    raw = explicit if explicit is not None else os.getenv(MARKET_GATE_MODE_ENV)
    text = str(raw or "").strip().lower()
    if text == MODE_DISABLED:
        return MODE_DISABLED
    if text in ("", MODE_REQUIRED):
        return MODE_REQUIRED
    logger.warning("%s invalid %s=%r; defaulting to required (fail-closed)",
                   _GATE_TAG, MARKET_GATE_MODE_ENV, raw)
    return MODE_REQUIRED


def resolve_market_publication_date(client: Any, requested: Optional[str]) -> Optional[str]:
    """Resolve the date a publication run should TARGET.

    Deliberately not ``resolve_latest_accepted_market_date``: that is the public
    READ authority (what the site serves today). Targeting it would republish
    yesterday forever and the pipeline could never advance - and on the very
    first day, when nothing is accepted yet, nothing could ever publish.

    The publication candidate is the newest date the Market actually has source
    data for. Quality then decides whether that candidate may be published.
    """
    if requested:
        return str(requested)[:10]
    candidate = resolve_latest_market_source_date(client)
    if candidate:
        return candidate
    # Nothing to advance to; fall back to the current public authority so a
    # re-run of an already-published day stays idempotent rather than crashing.
    return resolve_latest_accepted_market_date(client)


def _blocked_without_evaluation(
    reason: str,
    reason_code: str,
    *,
    commit: bool,
    entry_point: str,
    market_date: Optional[str],
) -> MarketGateEnforcement:
    """Block (or, in dry-run, report) when no quality verdict could be reached."""
    day = str(market_date)[:10] if market_date else None
    decision = MarketGateDecision(
        allowed=False, status="", market_date=day, reason=reason,
        reason_code=reason_code, evaluation=None)
    if not commit:
        print(f"{entry_point}: Market Date Quality (dry-run) [{reason_code}] "
              f"allowed=False: {reason}")
        return MarketGateEnforcement(decision=decision, proceed=True, exit_code=0)
    for line in (
        f"{entry_point}: Market publication gate CLOSED [{reason_code}]: {reason}",
        (f"{DEFERRAL_MARKER} entry_point={entry_point!r} market_date={day or 'unknown'} "
         f"market_quality_status=unknown reason_code={reason_code}"),
        "preserving previous good public Market authority; no promotion performed",
    ):
        print(line)
    return MarketGateEnforcement(
        decision=decision, proceed=False, exit_code=MARKET_GATE_DEFERRED_EXIT_CODE)


def enforce_market_publication_gate(
    client: Any,
    *,
    commit: bool,
    market_date: Optional[str] = None,
    force_publish: bool = False,
    entry_point: str = "Market publication",
    persist: bool = True,
    mode: Optional[str] = None,
) -> MarketGateEnforcement:
    """Evaluate Market Date Quality once per invocation and decide.

    Never consults ``pokemon_scrape_batches``: once Market quality has
    independently proven READY, the full 167-set batch is NOT an additional
    requirement.
    """
    if force_publish:
        logger.error("%s %s (entry_point=%s)", _GATE_TAG,
                     MARKET_FORCE_PUBLISH_REJECTION, entry_point)
        raise MarketForcePublishRejected()

    # Explicitly disabled - local/test only. Never touches the client, and is
    # never selected implicitly or as a consequence of a failed read.
    if resolve_market_gate_mode(mode) == MODE_DISABLED:
        logger.warning("%s gate DISABLED via %s=disabled; publishing ungated "
                       "(local/test only)", _GATE_TAG, MARKET_GATE_MODE_ENV)
        decision = MarketGateDecision(
            allowed=True, status="", market_date=(str(market_date)[:10] if market_date else None),
            reason="Market publication gate explicitly disabled (local/test only)",
            reason_code=REASON_DISABLED_EXPLICITLY, evaluation=None)
        return MarketGateEnforcement(decision=decision, proceed=True, exit_code=0)

    # No explicit date: fall back to the latest ACCEPTED Market date, which by
    # construction can never be a DEGRADED one. A failed read is NEVER a green
    # light - it blocks, exactly like the batch gate.
    try:
        target = resolve_market_publication_date(client, market_date)
    except Exception as exc:
        reason = (f"Market Date Quality authority unavailable ({exc}); "
                  "blocking publication (fail-closed)")
        logger.error("%s %s", _GATE_TAG, reason)
        return _blocked_without_evaluation(
            reason, REASON_BLOCKED_AUTHORITY_UNAVAILABLE,
            commit=commit, entry_point=entry_point, market_date=market_date)
    if not target:
        return _blocked_without_evaluation(
            "no accepted Market date exists and no --market-date was given; "
            "nothing may be promoted",
            REASON_BLOCKED_NO_EVIDENCE,
            commit=commit, entry_point=entry_point, market_date=None)

    try:
        evaluation = evaluate_market_date_quality(client, target)
    except Exception as exc:
        reason = (f"Market Date Quality could not be evaluated for {target} ({exc}); "
                  "blocking publication (fail-closed)")
        logger.error("%s %s", _GATE_TAG, reason)
        return _blocked_without_evaluation(
            reason, REASON_BLOCKED_AUTHORITY_UNAVAILABLE,
            commit=commit, entry_point=entry_point, market_date=target)
    status = str(evaluation.get("status") or "")
    reason_code = _REASON_BY_STATUS.get(status, REASON_BLOCKED_NO_EVIDENCE)
    allowed = status in ACCEPTED_STATUSES

    if allowed:
        reason = (f"Market cohort {evaluation['qualifyingSetCount']}/"
                  f"{evaluation['cohortSetCount']} qualifying for {target}; status={status}")
    else:
        reason = (f"Market cohort {evaluation['qualifyingSetCount']}/"
                  f"{evaluation['cohortSetCount']} qualifying for {target}; status={status}; "
                  f"missing={list(evaluation.get('missingSetIds') or [])[:10]}")

    decision = MarketGateDecision(allowed=allowed, status=status, market_date=target,
                                  reason=reason, reason_code=reason_code,
                                  evaluation=dict(evaluation))

    if not commit:
        # Dry-run: evaluate and REPORT only. No quality write, no artifact write.
        print(f"{entry_point}: Market Date Quality (dry-run) [{reason_code}] "
              f"status={status} allowed={allowed}: {reason}")
        return MarketGateEnforcement(decision=decision, proceed=True, exit_code=0)

    # Commit mode. Accepted quality is publication authority, so failure to
    # make it durable must fail closed before index/global artifacts advance.
    if persist:
        try:
            persist_market_date_quality(client, evaluation)
            print(f"[market-quality] persisted verdict date={target} status={status}")
        except Exception as exc:
            reason = f"Market Date Quality persistence failed for {target} ({exc})"
            logger.error("%s %s", _GATE_TAG, reason)
            return _blocked_without_evaluation(
                reason, REASON_BLOCKED_AUTHORITY_UNAVAILABLE,
                commit=commit, entry_point=entry_point, market_date=target)

    if allowed:
        logger.info("%s publication ALLOWED for %s (status=%s)", _GATE_TAG, target, status)
        print(f"{entry_point}: Market Date Quality [{reason_code}] status={status}: {reason}")
        return MarketGateEnforcement(decision=decision, proceed=True, exit_code=0)

    logger.warning("%s publication BLOCKED for %s (status=%s)", _GATE_TAG, target, status)
    for line in (
        f"{entry_point}: Market publication gate CLOSED [{reason_code}]: {reason}",
        (f"{DEFERRAL_MARKER} entry_point={entry_point!r} market_date={target} "
         f"market_quality_status={status} reason_code={reason_code}"),
        "preserving previous good public Market authority; no promotion performed",
    ):
        print(line)
    return MarketGateEnforcement(
        decision=decision, proceed=False, exit_code=MARKET_GATE_DEFERRED_EXIT_CODE)
