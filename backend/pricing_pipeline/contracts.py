"""Frozen constants for the daily pipeline. Nothing here is a research decision."""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timedelta, timezone
from typing import Any

from backend.scripts.freeze_ebay_active_ask_v1 import VERSION as EBAY_ESTIMATOR_VERSION
from backend.scripts.pokemon_multi_source_card_price_v1 import POLICY_FINGERPRINT, POLICY_VERSION

PIPELINE_VERSION = "multi_source_daily_pipeline_p6_v1"  # historical V1 identity (1000/day self-imposed cap); frozen
PIPELINE_VERSION_V2 = "multi_source_daily_pipeline_p6_v2"  # provider-aware quota authority (ebay_api_budget_policy_v2)
NM_CONDITION_ID = "4f8d1181-670e-4aea-937c-4d98d2e531a6"
# Arizona observes no DST, so America/Phoenix is always UTC-7 (same helper as the Sentinel authorities).
PHOENIX = timezone(timedelta(hours=-7), "America/Phoenix")
DAILY_REQUEST_LIMIT = 1000
# Measured on P4/P5B: 195/30 and 836/120 Browse calls per target (adaptive search + getItem, stop at 5 sellers).
DEFAULT_REQUESTS_PER_TARGET = 7.0
PLANNING_FRACTION = 0.90
# V2 keeps 20% of the usable pool unplanned for retries, late hydration and operational/manual probes.
PLANNING_FRACTION_V2 = 0.80
V2_STANDARD_USABLE_CEILING = 4500  # 5000 provider limit - 500 reserve; the DB is authoritative, callers can only lower it
STOP_SELLERS = 5
DETAILS_PER_TARGET = 8
# Accepted collector partial policy: at least this share of manifest targets must be attempted and at most this
# share of requests may fail; otherwise the run stops before persistence.
MIN_ATTEMPTED_SHARE = 0.80
MAX_FAILED_REQUEST_SHARE = 0.05

STAGES = ("INIT", "TARGETS_BUILT", "COLLECTION_RUNNING", "COLLECTION_COMPLETE", "EVIDENCE_PERSISTED",
          "ESTIMATES_BUILT", "MULTI_SOURCE_BUILT", "VALIDATED", "COMPLETE")
STATUSES = ("RUNNING", "WAITING", "COMPLETE", "PARTIAL", "FAILED")

# Exit codes for the CLI/cron wrapper.
EXIT_OK, EXIT_FAILED, EXIT_WAITING, EXIT_PARTIAL = 0, 1, 75, 2


class PipelineError(RuntimeError):
    """A fail-closed stage gate. `code` is a stable machine-readable reason."""

    def __init__(self, code: str, detail: str = "", status: str = "FAILED") -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code, self.detail, self.status = code, detail, status


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                                     default=str).encode()).hexdigest()


def phoenix_day(now: datetime | None = None) -> date:
    return (now or datetime.now(timezone.utc)).astimezone(PHOENIX).date()


def assert_policy_contract() -> None:
    if POLICY_VERSION != "pokemon_multi_source_card_price_v1" or EBAY_ESTIMATOR_VERSION != "ebay_active_ask_lower3_seller_median_v1":
        raise PipelineError("POLICY_VERSION_DRIFT", f"{POLICY_VERSION} / {EBAY_ESTIMATOR_VERSION}")
    if POLICY_FINGERPRINT != "caf6acbf7e4b4e43b4491ef2b018122bb4cfcb8b254621f8b32c8bb8a70abdb6":
        raise PipelineError("POLICY_FINGERPRINT_DRIFT", POLICY_FINGERPRINT)
