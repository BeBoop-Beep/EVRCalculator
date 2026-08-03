"""Deterministic configuration failures must not consume retries.

On 2026-08-03 all 34 failures were deterministic and every one was attempted
three times. Retrying could not have fixed any of them.
"""

from __future__ import annotations

import pytest

from backend.db.services.scrape_failure_classification import (
    ERROR_CATALOG_ONLY_NOT_DAILY_ELIGIBLE,
    ERROR_INVALID_SCRAPE_CONFIG,
    ERROR_INVALID_SET_KEY_FILTER,
    ERROR_MISSING_CANONICAL_KEY,
    ERROR_SET_NOT_FOUND,
    ERROR_TRANSIENT_SCRAPE_FAILURE,
    NON_RETRYABLE_ERROR_CODES,
    classify_report_failure,
    is_deterministic,
    is_retryable,
    remediation_for,
)


@pytest.mark.parametrize(
    "code",
    [
        ERROR_INVALID_SET_KEY_FILTER,
        ERROR_SET_NOT_FOUND,
        ERROR_MISSING_CANONICAL_KEY,
        ERROR_INVALID_SCRAPE_CONFIG,
        ERROR_CATALOG_ONLY_NOT_DAILY_ELIGIBLE,
    ],
)
def test_deterministic_errors_are_not_retryable(code):
    assert is_retryable(code) is False
    assert is_deterministic(code) is True
    assert remediation_for(code)


@pytest.mark.parametrize(
    "code",
    [
        ERROR_TRANSIENT_SCRAPE_FAILURE,
        "http_429",
        "provider_500",
        "read_timeout",
        "temporary_db_error",
        None,
        "",
    ],
)
def test_transient_and_unknown_errors_remain_retryable(code):
    # Unknown codes stay retryable on purpose: weakening retries for an
    # unrecognised failure trades a loud problem for a silent one.
    assert is_retryable(code) is True
    assert is_deterministic(code) is False


def test_the_non_retryable_set_is_exactly_the_documented_five():
    assert set(NON_RETRYABLE_ERROR_CODES) == {
        "invalid_set_key_filter",
        "set_not_found",
        "missing_canonical_key",
        "invalid_scrape_config",
        "catalog_only_not_daily_eligible",
    }


def test_runner_report_with_invalid_set_key_filter_classifies_deterministically():
    """The exact shape run_scraper returns for an unresolved canonical key."""
    code = classify_report_failure({"run_abort_reason": "invalid_set_key_filter"})
    assert code == ERROR_INVALID_SET_KEY_FILTER
    assert is_retryable(code) is False


def test_runner_report_with_other_abort_reason_stays_retryable():
    code = classify_report_failure({"run_abort_reason": "http_read_timeout"})
    assert code == ERROR_TRANSIENT_SCRAPE_FAILURE
    assert is_retryable(code) is True


def test_report_without_abort_reason_has_no_specific_code():
    assert classify_report_failure({"sets_failed": 1}) is None
    assert classify_report_failure(None) is None
