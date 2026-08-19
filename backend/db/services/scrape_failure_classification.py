"""Centralized classification of scrape failure codes.

A scrape job can fail for two fundamentally different reasons, and the correct
response to each is opposite:

* **Transient** — provider 5xx, HTTP 429, socket timeout, temporary database
  error. Trying again is exactly right; the queue's attempt budget exists for
  these.
* **Deterministic** — the deployed runtime cannot resolve the canonical key, the
  set row is gone, the config is invalid. Trying again cannot change the outcome.
  Retrying burns the attempt budget, delays the batch, and — worst of all —
  buries a configuration/deployment defect under what looks like flaky scraping.

On 2026-08-03 all 34 failures were deterministic (``invalid_set_key_filter``
caused by a stale VM checkout) and every one was attempted three times. This
module is the single place that decides which bucket a failure falls into; the
same code list is mirrored in SQL by
``public.scrape_error_code_is_retryable`` (migration 058) so cohort repair
enforces the policy even if a worker on an older runtime finalizes without a
code.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

# --- Deterministic (non-retryable) codes -------------------------------------
ERROR_INVALID_SET_KEY_FILTER = "invalid_set_key_filter"
ERROR_SET_NOT_FOUND = "set_not_found"
ERROR_MISSING_CANONICAL_KEY = "missing_canonical_key"
ERROR_INVALID_SCRAPE_CONFIG = "invalid_scrape_config"
ERROR_CATALOG_ONLY_NOT_DAILY_ELIGIBLE = "catalog_only_not_daily_eligible"

NON_RETRYABLE_ERROR_CODES: Tuple[str, ...] = (
    ERROR_INVALID_SET_KEY_FILTER,
    ERROR_SET_NOT_FOUND,
    ERROR_MISSING_CANONICAL_KEY,
    ERROR_INVALID_SCRAPE_CONFIG,
    ERROR_CATALOG_ONLY_NOT_DAILY_ELIGIBLE,
)

# Human-facing guidance, so an alert says what to DO rather than only what broke.
_REMEDIATION: Dict[str, str] = {
    ERROR_INVALID_SET_KEY_FILTER: (
        "The deployed runtime cannot resolve this canonical key. Deploy the approved "
        "commit to the scraper VM and re-run the runtime preflight."
    ),
    ERROR_SET_NOT_FOUND: "The set row referenced by this job no longer exists.",
    ERROR_MISSING_CANONICAL_KEY: "The set row has no canonical_key; fix set metadata.",
    ERROR_INVALID_SCRAPE_CONFIG: "The set config is missing required scrape fields.",
    ERROR_CATALOG_ONLY_NOT_DAILY_ELIGIBLE: (
        "This set is catalog_only and must not be in the daily cohort. Re-run the "
        "metadata sync so ready_for_daily_scrape is recomputed."
    ),
}

# A generic transient code used when the worker cannot attribute a failure more
# precisely. Anything not explicitly listed as deterministic stays retryable —
# unknown failures must keep their retries, never silently lose them.
ERROR_TRANSIENT_SCRAPE_FAILURE = "transient_scrape_failure"
ERROR_SOURCE_EMPTY = "source_empty"
ERROR_NO_VALID_MARKET_PRICES = "no_valid_market_prices"
ERROR_VARIANT_IDENTITY_AMBIGUITY = "variant_identity_ambiguity"
ERROR_MISSING_NEAR_MINT_VARIANT = "missing_near_mint_variant"
ERROR_INGESTION_FAILURE = "ingestion_failure"
ERROR_MISSING_CURRENT_DAY_NM = "missing_current_day_near_mint_observation"
ERROR_INCOMPLETE_VARIANT_PERSISTENCE = "incomplete_source_variant_persistence"


def is_retryable(error_code: Optional[str]) -> bool:
    """True unless the code is explicitly deterministic.

    Defaults to retryable on purpose: weakening retries for an unrecognised
    failure would trade a loud, self-healing problem for a silent one.
    """
    if not error_code:
        return True
    return str(error_code).strip() not in NON_RETRYABLE_ERROR_CODES


def is_deterministic(error_code: Optional[str]) -> bool:
    return not is_retryable(error_code)


def remediation_for(error_code: Optional[str]) -> Optional[str]:
    if not error_code:
        return None
    return _REMEDIATION.get(str(error_code).strip())


def classify_report_failure(report: Optional[Dict[str, Any]]) -> Optional[str]:
    """Derive a stable machine-readable error code from a scrape runner report.

    ``run_scraper`` already reports ``run_abort_reason='invalid_set_key_filter'``
    for the unresolved-key path; this maps the runner's vocabulary onto the
    canonical codes without the worker having to parse prose.
    """
    if not isinstance(report, dict):
        return None

    abort_reason = report.get("run_abort_reason")
    if abort_reason:
        code = str(abort_reason).strip()
        if code in NON_RETRYABLE_ERROR_CODES:
            return code
        return ERROR_TRANSIENT_SCRAPE_FAILURE

    error = " ".join(str(row.get("error") or "") for row in report.get("results") or []).lower()
    classifications = (
        (ERROR_INCOMPLETE_VARIANT_PERSISTENCE, ERROR_INCOMPLETE_VARIANT_PERSISTENCE),
        ("missing_current_day_near_mint", ERROR_MISSING_CURRENT_DAY_NM),
        ("database ingestion failed", ERROR_INGESTION_FAILURE),
        ("fatal card ingestion", ERROR_INGESTION_FAILURE),
        ("zero attempted price rows", ERROR_INGESTION_FAILURE),
        ("zero cards in payload", ERROR_NO_VALID_MARKET_PRICES),
        ("source_empty", ERROR_SOURCE_EMPTY),
        ("variant_identity_ambiguity", ERROR_VARIANT_IDENTITY_AMBIGUITY),
        ("missing_near_mint_variant", ERROR_MISSING_NEAR_MINT_VARIANT),
    )
    for marker, code in classifications:
        if marker in error:
            return code

    return None
