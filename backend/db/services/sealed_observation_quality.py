"""Daily Sealed observation coverage diagnostics.

This is deliberately independent of Raw/Chase batch readiness. It detects a
Sealed-only outage, records whether the following 1D comparison may use the
single-day previous-close rule, and leaves canonical observations untouched.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any, Mapping

logger = logging.getLogger(__name__)

CURRENT = "CURRENT"
ONE_DAY_CARRY = "ONE_DAY_CARRY"
UNAVAILABLE = "UNAVAILABLE"
_PAGE_SIZE = 1000


def assess_sealed_observation_quality(
    *, market_date: str, expected_count: int, observed_count: int,
    previous_observed_count: int, two_days_prior_observed_count: int,
    last_observed_date: str | None,
) -> dict[str, Any]:
    day = date.fromisoformat(str(market_date)[:10])
    previous = (day - timedelta(days=1)).isoformat()
    two_days_prior = (day - timedelta(days=2)).isoformat()
    if observed_count <= 0:
        state = UNAVAILABLE
    elif previous_observed_count <= 0 and two_days_prior_observed_count > 0:
        state = ONE_DAY_CARRY
    else:
        state = CURRENT
    return {
        "marketDate": day.isoformat(),
        "expectedEligibleProductCount": int(expected_count),
        "observedProductCount": int(observed_count),
        "previousObservedProductCount": int(previous_observed_count),
        "twoDaysPriorObservedProductCount": int(two_days_prior_observed_count),
        "lastObservedDate": last_observed_date,
        "coverageRatio": (observed_count / expected_count) if expected_count > 0 else None,
        "state": state,
        "carryForwardEligible": bool(
            observed_count <= 0 and last_observed_date == previous
        ),
        "comparisonCarrySourceDate": (
            two_days_prior if state == ONE_DAY_CARRY else None
        ),
    }


def _distinct_observed_count(client: Any, day: str, expected_ids: set[str] | None = None) -> int:
    ids: set[str] = set()
    offset = 0
    while True:
        rows = list((client.table("sealed_product_price_observations")
            .select("sealed_product_id").eq("captured_date", day)
            .range(offset, offset + _PAGE_SIZE - 1).execute()).data or [])
        ids.update(str(row.get("sealed_product_id")) for row in rows if row.get("sealed_product_id"))
        if len(rows) < _PAGE_SIZE:
            return len(ids & expected_ids) if expected_ids else len(ids)
        offset += _PAGE_SIZE


def read_sealed_observation_quality(client: Any, market_date: str) -> dict[str, Any]:
    day = date.fromisoformat(str(market_date)[:10])
    previous = (day - timedelta(days=1)).isoformat()
    two_days_prior = (day - timedelta(days=2)).isoformat()
    # Prepared set snapshots contain the same overview-eligible product
    # universe consumed by the global Sealed Market builder. They may be from
    # the prior publication when this guard runs, which is exactly the expected
    # daily cohort against which today's raw observations should be checked.
    prepared_rows = list((client.table("pokemon_set_sealed_market_snapshot_latest")
        .select("payload_json").execute()).data or [])
    expected_ids = {
        str(product.get("sealedProductId"))
        for row in prepared_rows
        for product in ((row.get("payload_json") or {}).get("products") or [])
        if product.get("sealedProductId")
    }
    if expected_ids:
        expected_count = len(expected_ids)
    else:
        expected_result = client.table("sealed_products").select("id", count="exact").limit(1).execute()
        expected_count = int(expected_result.count or 0)
    latest_rows = list((client.table("sealed_product_price_observations")
        .select("captured_date").lt("captured_date", day.isoformat())
        .order("captured_date", desc=True).limit(1).execute()).data or [])
    return assess_sealed_observation_quality(
        market_date=day.isoformat(),
        expected_count=expected_count,
        observed_count=_distinct_observed_count(client, day.isoformat(), expected_ids),
        previous_observed_count=_distinct_observed_count(client, previous, expected_ids),
        two_days_prior_observed_count=_distinct_observed_count(client, two_days_prior, expected_ids),
        last_observed_date=str(latest_rows[0].get("captured_date"))[:10] if latest_rows else None,
    )


def evaluate_and_alert_sealed_observation_quality(
    client: Any, market_date: str
) -> Mapping[str, Any]:
    result = read_sealed_observation_quality(client, market_date)
    if (result["expectedEligibleProductCount"] > 0
            and result["observedProductCount"] == 0):
        logger.error(
            "SEALED MARKET OBSERVATION GAP market_date=%s eligible=%s observed=0 last=%s carry=%s",
            result["marketDate"], result["expectedEligibleProductCount"],
            result["lastObservedDate"], result["carryForwardEligible"],
        )
        from backend.alerts.scrape_alerts import alert_sealed_market_observation_gap
        alert_sealed_market_observation_gap(result)
    return result
