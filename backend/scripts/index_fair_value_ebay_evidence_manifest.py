"""Fail-closed evidence-boundary guard for D3-v4 development.

Encodes, in code, the E2.1 scientific boundary: historical final-blind
partitions (and the fresh D3 blind partitions) may be used only for
historical failure reporting and post-freeze regression tests -- never to
derive rules, select thresholds, or certify a new matcher version. The
VALIDATION partition may be used for exactly one bounded pass, tracked here
so a second pass is refused.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.scripts.ebay_gold_access import OUT, load_partition

STATE_PATH = OUT / "ebay_d3_v4_validation_pass_state.json"

TUNING_ALLOWED_PARTITIONS = frozenset({"DEVELOPMENT"})
ONE_TIME_PASS_PARTITIONS = frozenset({"VALIDATION"})
HISTORICAL_ONLY_PARTITIONS = frozenset(
    {"FINAL_BLIND_TEST", "PRECISION_BLIND", "COVERAGE_BLIND", "D3_BLIND_REVIEW"}
)

TUNING_PURPOSES = frozenset({"matcher_development", "threshold_design", "rule_design"})


class EvidenceBoundaryViolation(RuntimeError):
    pass


class ValidationPassAlreadyConsumed(RuntimeError):
    pass


def load_development_for_tuning(purpose: str = "matcher_development") -> list[dict[str, Any]]:
    """The only partition this module will hand back for rule/threshold design."""
    if purpose not in TUNING_PURPOSES:
        raise EvidenceBoundaryViolation(f"purpose={purpose} is not a recognized tuning purpose")
    return load_partition("DEVELOPMENT", purpose="matcher_development")


def load_historical_blind_for_reporting_only(partition: str) -> list[dict[str, Any]]:
    """Explicitly for post-freeze regression / historical-failure-category reporting.

    Never returns rows for a tuning purpose -- ebay_gold_access.py itself
    already refuses that, this wraps it with an explicit, narrowly-named entry
    point so calling code cannot "accidentally" end up here from a tuning path.
    """
    if partition.upper() not in HISTORICAL_ONLY_PARTITIONS and partition.upper() != "FINAL_BLIND_TEST":
        raise EvidenceBoundaryViolation(f"{partition} is not a recognized historical-only partition")
    return load_partition(partition, purpose="human_review")


def _read_state() -> dict[str, Any]:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    return {"validation_pass_consumed": False, "consumed_by": None}


def _write_state(state: dict[str, Any]) -> None:
    STATE_PATH.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def load_validation_for_one_time_pass(consumer: str, allow_repeat_for_tests: bool = False) -> list[dict[str, Any]]:
    """Refuses a second call once a validation pass has been consumed.

    This is deliberately stateful (persisted to disk) so that even across
    separate process invocations, a second "one bounded pass" cannot happen
    without the caller explicitly acknowledging it is repeating a pass (tests
    only -- `allow_repeat_for_tests` must never be set by production code).
    """
    state = _read_state()
    if state["validation_pass_consumed"] and not allow_repeat_for_tests:
        raise ValidationPassAlreadyConsumed(
            f"validation was already consumed by {state['consumed_by']!r}; the validation partition "
            "has become development information and must not be used for another pass"
        )
    rows = load_partition("VALIDATION", purpose="threshold_validation")
    if not allow_repeat_for_tests:
        _write_state({"validation_pass_consumed": True, "consumed_by": consumer})
    return rows


def reset_validation_pass_state_for_tests() -> None:
    if STATE_PATH.exists():
        STATE_PATH.unlink()


def assert_not_used_for_tuning(partition: str, purpose: str) -> None:
    if partition.upper() in HISTORICAL_ONLY_PARTITIONS and purpose in TUNING_PURPOSES:
        raise EvidenceBoundaryViolation(f"refused: {partition} may never be used for purpose={purpose}")
    if partition.upper() == "VALIDATION" and purpose in TUNING_PURPOSES:
        raise EvidenceBoundaryViolation("refused: VALIDATION may only be used for a one-time verification pass, not tuning")
