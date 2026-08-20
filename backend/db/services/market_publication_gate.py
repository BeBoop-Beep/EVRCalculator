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
)

logger = logging.getLogger(__name__)

_GATE_TAG = "[market-quality-gate]"

MARKET_GATE_DEFERRED_EXIT_CODE = 3
DEFERRAL_MARKER = "PUBLICATION_DEFERRED"

MARKET_FORCE_PUBLISH_REJECTION = (
    "Market Date Quality cannot be overridden with --force-publish")

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


def resolve_market_publication_date(client: Any, requested: Optional[str]) -> Optional[str]:
    if requested:
        return str(requested)[:10]
    return resolve_latest_accepted_market_date(client)


def enforce_market_publication_gate(
    client: Any,
    *,
    commit: bool,
    market_date: Optional[str] = None,
    force_publish: bool = False,
    entry_point: str = "Market publication",
    persist: bool = True,
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

    target = str(market_date)[:10] if market_date else None
    if target is None:
        raise ValueError(
            f"{entry_point}: --market-date is required when no accepted Market date exists")

    evaluation = evaluate_market_date_quality(client, target)
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

    # Commit mode. The quality row is durable diagnostic STATE, explicitly not
    # Market artifact publication, so it is written even on a blocked date.
    if persist:
        try:
            persist_market_date_quality(client, evaluation)
        except Exception as exc:  # diagnostics must never gate publication
            logger.warning("%s could not persist quality state for %s: %s",
                           _GATE_TAG, target, exc)

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
