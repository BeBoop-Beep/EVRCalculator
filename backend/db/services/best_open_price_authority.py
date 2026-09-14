"""Pure publication identity and numeric contracts shared by Best-Open readers/jobs.

No DB I/O. Snapshot UUID alone does not identify a mutable ranking publication.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Sequence

from backend.calculations.evr.budget_normalized_product_ranking import (
    ALLOCATION_METHOD_VERSION, BUDGET_NORMALIZED_RANKING_METHOD_VERSION,
    BUDGET_COMPARISON_SCOPE_VERSION,
)
from backend.db.services.budget_product_ranking_authority import (
    EXPECTED_FINANCIAL_RIP_VERSION, EXPECTED_OVERALL_RIP_V12_VERSION,
    EXPECTED_COLLECTOR_APPEAL_VERSION, EXPECTED_CHASE_ACCESSIBILITY_VERSION,
    EXPECTED_CHASE_ACCESSIBILITY_TRANSFORM_VERSION,
)

# Operational/checkpoint contract, not a change to Financial/V12 methodology.
EXECUTION_CONTRACT_VERSION = 'best_open_exact_publication_review_v2'
SOURCE_FIELDS = (
    'id', 'published_at', 'market_date', 'pinned_price_as_of',
    'cohort_fingerprint', 'full_market_budget', 'eligible_cohort_count',
    'ranking_method_version', 'allocation_method_version', 'comparison_scope_version',
    'financial_rip_version', 'overall_rip_version', 'overall_rip_v12_version',
    'collector_appeal_version', 'chase_accessibility_version',
    'chase_accessibility_transform_version', 'ranked_under_v12_authority',
)
SOURCE_VERSIONS = {
    'ranking_method_version': BUDGET_NORMALIZED_RANKING_METHOD_VERSION,
    'allocation_method_version': ALLOCATION_METHOD_VERSION,
    'comparison_scope_version': BUDGET_COMPARISON_SCOPE_VERSION,
    'financial_rip_version': EXPECTED_FINANCIAL_RIP_VERSION,
    'overall_rip_version': EXPECTED_OVERALL_RIP_V12_VERSION,
    'overall_rip_v12_version': EXPECTED_OVERALL_RIP_V12_VERSION,
    'collector_appeal_version': EXPECTED_COLLECTOR_APPEAL_VERSION,
    'chase_accessibility_version': EXPECTED_CHASE_ACCESSIBILITY_VERSION,
    'chase_accessibility_transform_version': EXPECTED_CHASE_ACCESSIBILITY_TRANSFORM_VERSION,
}
PREPARED_BINDING = {
    'id': 'source_budget_snapshot_id', 'published_at': 'source_budget_published_at',
    'market_date': 'source_market_date', 'cohort_fingerprint': 'source_cohort_fingerprint',
    'full_market_budget': 'source_full_market_budget',
    'eligible_cohort_count': 'source_eligible_cohort_count',
    **{name: name for name in SOURCE_VERSIONS if name != 'overall_rip_version'},
    'overall_rip_version': 'overall_rip_v12_version',
}


def finite_decimal(value: Any) -> Decimal:
    if value is None or isinstance(value, bool):
        raise ValueError('missing or invalid numeric value')
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError('invalid numeric value') from exc
    if not number.is_finite():
        raise ValueError('non-finite numeric value')
    return number


def cents(value: Any) -> int:
    number = finite_decimal(value) * 100
    if number != number.to_integral_value():
        raise ValueError('price is not exact-cent precision')
    return int(number)


def timestamp(value: Any) -> str:
    parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('publication timestamp must have a timezone')
    return parsed.astimezone(timezone.utc).isoformat()


def source_identity(source: Mapping[str, Any]) -> dict[str, Any]:
    result = {name: source.get(name) for name in SOURCE_FIELDS}
    if result['published_at'] is not None:
        result['published_at'] = timestamp(result['published_at'])
    for name in ('full_market_budget', 'eligible_cohort_count'):
        if result[name] is not None:
            result[name] = str(finite_decimal(result[name]).normalize())
    return result


def validate_source(source: Mapping[str, Any]) -> None:
    if source.get('ranked_under_v12_authority') is not True:
        raise ValueError('source is not explicitly V12-authoritative')
    for name, expected in SOURCE_VERSIONS.items():
        if source.get(name) != expected:
            raise ValueError(f'source {name} is incompatible with Best-Open V1')
    for name in ('id', 'published_at', 'market_date', 'pinned_price_as_of', 'cohort_fingerprint'):
        if not source.get(name):
            raise ValueError(f'missing source {name}')
    timestamp(source['published_at'])
    if cents(source.get('full_market_budget')) < 1:
        raise ValueError('source budget must be positive')
    count = finite_decimal(source.get('eligible_cohort_count'))
    if count < 2 or count != count.to_integral_value():
        raise ValueError('Best-Open requires at least two eligible products')


def source_binding_matches(source: Mapping[str, Any], prepared: Mapping[str, Any]) -> bool:
    try:
        validate_source(source)
        for source_field, stored_field in PREPARED_BINDING.items():
            a, b = source.get(source_field), prepared.get(stored_field)
            if a is None or b is None:
                return False
            if source_field == 'published_at':
                if timestamp(a) != timestamp(b):
                    return False
            elif source_field in ('full_market_budget', 'eligible_cohort_count'):
                if finite_decimal(a) != finite_decimal(b):
                    return False
            elif str(a) != str(b):
                return False
        return True
    except (ValueError, TypeError):
        return False


def source_content_fingerprint(source: Mapping[str, Any], rows: Sequence[Mapping[str, Any]]) -> str:
    """All Full Market source values, including comparator inputs, not just Chase.

    Hashes the actual rows so an input edit without a UUID/date change cannot
    resume or publish previously computed products. No threshold/timing fields.
    """
    value = {'source': source_identity(source), 'rows': sorted(
        [dict(row) for row in rows], key=lambda row: str(row.get('sealed_product_id', '')),
    )}
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), default=str, allow_nan=False).encode()).hexdigest()
