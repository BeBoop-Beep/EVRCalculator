"""Set-level Cards market analytics: Cards Market Index and Market Breadth.

ONE CONSTITUENT AUTHORITY, THREE ANALYTICAL VIEWS
=================================================
Set Value, Cards Market Index and Market Breadth are three different questions
asked of the SAME canonical card market:

* Set Value      -- how large is the basket?           (how much is it worth)
* Market Index   -- how has the common market moved?   (performance)
* Market Breadth -- how broadly are cards moving?      (participation)

All three therefore read one authority: the ``get_pokemon_cards_daily_constituents``
RPC, whose per-card daily Near Mint values sum EXACTLY to the ``standard`` scope
of ``pokemon_set_value_daily_history`` for the same set and date. That RPC
carries its own ``TimeZone=America/Phoenix`` function configuration, so the
America/Phoenix market-date boundary that defines Set Value is reproduced here
regardless of session, pool, or process timezone -- callers must NOT set a
session timezone (see migration 20260822140000).

``assert_reconciles_to_set_value`` below exists to keep that promise honest over
time: it is the guard against this module's basket silently drifting away from
the authority it claims to be a view of.

WHAT THIS MODULE DELIBERATELY DOES NOT DO
-----------------------------------------
* It does not invent a second Cards Tracked Value. Tracked Value authority
  remains ``pokemon_set_value_daily_history`` (scope ``standard``). The index is
  an ADDITIONAL performance metric beside that value, not a replacement for it.
* It does not forward-fill or zero-fill constituents. The RPC already applies
  Set Value's own point-in-time latest-known-price rule; a card with no
  qualifying observation before a day's boundary simply has no row that day, and
  the chain link handles its absence by excluding it from that day's common
  cohort. Fabricating a zero would read as a total price collapse.
* It does not fork the index formula. Chain linking and chain-segment semantics
  come from ``backend.domain.pokemon.market_index``, the same primitives backing
  the global Raw Card Market / Top 10 Chase Market indexes and the Sealed index.
"""

from __future__ import annotations

import logging
import math
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

from backend.domain.pokemon.market_index import (
    MARKET_INDEX_BASE_VALUE,
    build_chain_linked_history_with_segments,
    compute_strict_window_movements,
    resolve_partial_window_coverage,
    resolve_window_baselines,
)

logger = logging.getLogger(__name__)

CARDS_MARKET_ANALYTICS_CONTRACT_VERSION = "pokemon-set-cards-market-v1"
CARDS_MARKET_METHODOLOGY_VERSION = "chain_linked_common_cohort_v1"
CARD_CONSTITUENT_RPC = "get_pokemon_cards_daily_constituents"

# PostgREST caps every response at db-max-rows (1000 on this project, a global
# server setting no role config can raise). A full-history read for one set is
# tens of thousands of rows, so the loader MUST split the read.
#
# IT SPLITS BY DATE RANGE, NOT BY ROW OFFSET. Offset paging looks like the
# obvious fix and is a trap: PostgREST wraps the RPC in a LIMIT/OFFSET
# subquery, and Postgres re-executes the ENTIRE set-returning function for
# every page. Measured on Destined Rivals, one full-history call is ~2.8s, so
# 33 offset pages would cost ~92s per set. Date chunks instead make each call
# genuinely smaller (~341ms fixed cost + ~18ms/day), bringing a full history
# down to roughly 12-15s.
_RPC_MAX_ROWS_PER_RESPONSE = 1000
# Leave headroom under the cap so a day that gains a card between the probe
# and the read cannot silently truncate a chunk.
_RPC_CHUNK_ROW_BUDGET = 900
_RPC_MIN_CHUNK_DAYS = 1
# Safety stop so a runaway loop cannot spin forever.
_RPC_MAX_ROWS = 1_000_000

# Prices are compared as exact cents. Card prices arrive as NUMERIC and would
# round-trip through binary floats otherwise, where 12.34 - 12.34 is not
# reliably 0 and an unchanged card can be misclassified as advancing.
_CENTS = Decimal("0.01")

BREADTH_STATUS_AVAILABLE = "available"
BREADTH_STATUS_INSUFFICIENT_HISTORY = "insufficient_history"
BREADTH_STATUS_NO_COMMON_COHORT = "no_common_cohort"
BREADTH_STATUS_BASELINE_UNAVAILABLE = "baseline_unavailable"


class PokemonSetCardsMarketAnalyticsError(Exception):
    pass


# ---------------------------------------------------------------------------
# Constituent loading (IO)
# ---------------------------------------------------------------------------


def load_card_constituent_rows(
    set_id: str,
    start_date: str,
    end_date: str,
    *,
    client: Any,
) -> List[Dict[str, Any]]:
    """Read raw per-card daily constituent rows for one set over a date range.

    NO SESSION TIMEZONE IS SET HERE, AND NONE MAY BE. The RPC owns the
    America/Phoenix business-date boundary as function-level configuration. A
    caller that set a session timezone would not change the result (the
    function config wins) but would signal that the boundary is negotiable,
    which it is not.
    """
    first = date.fromisoformat(str(start_date)[:10])
    last = date.fromisoformat(str(end_date)[:10])
    if first > last:
        raise PokemonSetCardsMarketAnalyticsError(
            f"start_date {first} must not be after end_date {last}"
        )

    # Probe the newest single day to learn this set's cards-per-day, which sets
    # how many days fit in one capped response.
    probe = _call_constituent_rpc(client, set_id, last, last)
    cards_per_day = max(1, len(probe))
    chunk_days = max(_RPC_MIN_CHUNK_DAYS, _RPC_CHUNK_ROW_BUDGET // cards_per_day)

    rows: List[Dict[str, Any]] = list(probe)
    cursor = first
    while cursor < last:
        chunk_end = min(last - timedelta(days=1), cursor + timedelta(days=chunk_days - 1))
        page = _call_constituent_rpc(client, set_id, cursor, chunk_end)
        # A chunk that comes back exactly at the cap was almost certainly
        # truncated. Silently accepting it would drop cards from the tail day
        # and corrupt both the index and Set Value reconciliation, so narrow
        # the window and retry rather than trusting the count.
        while len(page) >= _RPC_MAX_ROWS_PER_RESPONSE and chunk_end > cursor:
            chunk_days = max(_RPC_MIN_CHUNK_DAYS, chunk_days // 2)
            chunk_end = min(chunk_end, cursor + timedelta(days=chunk_days - 1))
            page = _call_constituent_rpc(client, set_id, cursor, chunk_end)
        if len(page) >= _RPC_MAX_ROWS_PER_RESPONSE:
            raise PokemonSetCardsMarketAnalyticsError(
                f"{CARD_CONSTITUENT_RPC} hit the {_RPC_MAX_ROWS_PER_RESPONSE}-row response cap for "
                f"set {set_id} on the single day {cursor}; the per-day cohort exceeds one response"
            )
        rows.extend(page)
        if len(rows) > _RPC_MAX_ROWS:
            raise PokemonSetCardsMarketAnalyticsError(
                f"{CARD_CONSTITUENT_RPC} returned more than {_RPC_MAX_ROWS} rows for set {set_id}"
            )
        cursor = chunk_end + timedelta(days=1)
    return rows


def _call_constituent_rpc(client: Any, set_id: str, start: date, end: date) -> List[Dict[str, Any]]:
    result = client.rpc(
        CARD_CONSTITUENT_RPC,
        {
            "p_set_ids": [set_id],
            "p_start_date": start.isoformat(),
            "p_end_date": end.isoformat(),
            "p_card_ids": None,
        },
    ).execute()
    return list(getattr(result, "data", None) or [])


# ---------------------------------------------------------------------------
# Constituent shaping (pure)
# ---------------------------------------------------------------------------


def build_constituent_observations(rows: Iterable[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """Group raw RPC rows into one index observation per market date.

    The output uses the shared generic index contract's field names --
    ``setId`` / ``setValue`` -- because ``build_chain_linked_history`` is a
    domain abstraction that does not care what a constituent represents, only
    that it has a stable identifier and a positive value. HERE ``setId``
    CARRIES A CANONICAL CARD ID, NOT A POKEMON SET ID. That naming is legacy to
    the shared primitive (which was written for the global cross-set index) and
    is deliberately not reinterpreted locally; renaming it would be a global
    refactor of the domain contract and every existing consumer, which is out
    of scope for this change.

    Rows with a missing/non-positive price are dropped rather than zero-filled:
    the index's common-cohort rule already handles an absent card correctly,
    while a zero would read as a 100% price collapse.
    """
    by_date: Dict[str, Dict[str, float]] = {}
    for row in rows:
        market_date = str(row.get("market_date") or row.get("marketDate") or "")[:10]
        card_id = str(row.get("canonical_card_id") or row.get("canonicalCardId") or "").strip()
        raw_price = row.get("market_price", row.get("marketPrice"))
        if not market_date or not card_id or raw_price is None:
            continue
        try:
            price = float(raw_price)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(price) or price <= 0:
            continue
        # Defensive: the RPC returns one row per (card, date), but a duplicate
        # would make _constituent_map raise on a non-unique id and take the
        # whole history down. Last row wins, matching the RPC's own ordering.
        by_date.setdefault(market_date, {})[card_id] = price

    observations: List[Dict[str, Any]] = []
    for market_date in sorted(by_date):
        constituents = [
            {"setId": card_id, "setValue": price}
            for card_id, price in sorted(by_date[market_date].items())
        ]
        if constituents:
            observations.append({"marketDate": market_date, "constituents": constituents})
    return observations


# ---------------------------------------------------------------------------
# Cards Market Index (pure)
# ---------------------------------------------------------------------------


def build_cards_market_index(observations: Sequence[Mapping[str, Any]]) -> Optional[Dict[str, Any]]:
    """Chain-linked Cards Market Index over canonical card constituents.

    Mirrors the Sealed set-level index contract field for field so a single
    frontend component can render either lens. Window returns are confined to
    the CURRENT chain segment: the index levels either side of a zero-overlap
    break are not mathematically linked, and spanning one would manufacture a
    return (segment A's 119.40 read against segment B's fresh 100.00 baseline
    as a fake -16.25% move) that no price data supports. "All"/SinceTracking
    therefore means "since the current segment began".

    Returns None when there is nothing to index; callers omit the lens rather
    than publishing a fabricated 100.
    """
    if not observations:
        return None
    index_history = build_chain_linked_history_with_segments(observations)
    if not index_history:
        return None

    current_segment_id = index_history[-1]["chainSegmentId"]
    current_segment_points = [
        {"date": row["marketDate"], "value": row["normalizedIndexValue"]}
        for row in index_history
        if row["chainSegmentId"] == current_segment_id
    ]
    if not current_segment_points:
        return None
    movements = compute_strict_window_movements(current_segment_points)

    return {
        "currentValue": current_segment_points[-1]["value"],
        "baseValue": MARKET_INDEX_BASE_VALUE,
        # "Since this reading has been continuously comparable", not "since the
        # very first index point ever recorded".
        "trackingSince": current_segment_points[0]["date"],
        "currentSegmentId": current_segment_id,
        "segmentCount": index_history[-1]["chainSegmentId"] + 1,
        "pointCount": len(index_history),
        "asOf": index_history[-1]["marketDate"],
        # Full multi-segment history WITH tags on every row, so a chart can
        # render each segment as its own line with a visible gap rather than
        # drawing a continuous line through a break that has no market meaning.
        "history": [
            {
                "date": row["marketDate"],
                "indexValue": row["normalizedIndexValue"],
                "constituentCount": len(row["constituents"]),
                "chainSegmentId": row["chainSegmentId"],
                "segmentStartDate": row["segmentStartDate"],
                "isNewSegment": row["marketDate"] == row["segmentStartDate"],
            }
            for row in index_history
        ],
        "movements": movements,
    }


# ---------------------------------------------------------------------------
# Market Breadth (pure)
# ---------------------------------------------------------------------------


def _to_cents(value: Any) -> Optional[Decimal]:
    try:
        return Decimal(str(value)).quantize(_CENTS)
    except (InvalidOperation, TypeError, ValueError):
        return None


def _percentages(counts: Mapping[str, int], total: int) -> Dict[str, Optional[float]]:
    """One-decimal percentages that sum to exactly 100.0.

    Rounding each share independently lets the three buckets total 99.9 or
    100.1, which reads as a data error in a UI that shows all three. The drift
    is absorbed into the LARGEST bucket, where a 0.1 adjustment is
    proportionally smallest and cannot flip a bucket's rank.
    """
    if total <= 0:
        return {key: None for key in counts}
    rounded = {key: round(value * 100.0 / total, 1) for key, value in counts.items()}
    drift = round(100.0 - sum(rounded.values()), 1)
    if abs(drift) >= 0.05:
        target = max(rounded, key=lambda key: (counts[key], key))
        rounded[target] = round(rounded[target] + drift, 1)
    return rounded


def compute_market_breadth(
    observations: Sequence[Mapping[str, Any]],
    *,
    segment_dates: Optional[Sequence[str]] = None,
) -> Dict[str, Dict[str, Any]]:
    """Per-window advancing/declining/unchanged participation.

    ELIGIBLE UNIVERSE is the COMMON COMPARABLE COHORT: canonical cards with a
    valid authoritative price at BOTH the window's baseline date and its end
    date. Not every printed card, not only Top 10, not only cards the movers
    ticker happens to return, and never a card present at only one endpoint --
    a card with no baseline has no move to classify, and counting it anywhere
    (including "unchanged") would be a fabrication.

    ``segment_dates`` confines breadth to the Cards Index's CURRENT chain
    segment so the two stay semantically aligned: a window the index refuses to
    span because the history is disconnected is not a window breadth may
    quietly compare across either.

    Comparison is on exact cents. Float subtraction on NUMERIC-sourced prices
    makes "unchanged" unreliable, and an unchanged card misfiled as advancing
    biases the headline number.
    """
    by_date: Dict[str, Dict[str, Decimal]] = {}
    for observation in observations:
        market_date = str(observation.get("marketDate"))[:10]
        prices: Dict[str, Decimal] = {}
        for row in observation.get("constituents") or ():
            card_id = str(row.get("setId") or row.get("set_id") or "").strip()
            cents = _to_cents(row.get("setValue", row.get("set_value")))
            if card_id and cents is not None and cents > 0:
                prices[card_id] = cents
        if prices:
            by_date[market_date] = prices

    if not by_date:
        return {}

    available_dates = sorted(by_date)
    if segment_dates:
        allowed = set(segment_dates)
        available_dates = [value for value in available_dates if value in allowed]
    if not available_dates:
        return {}

    end_date = available_dates[-1]
    end_prices = by_date[end_date]
    baselines = resolve_window_baselines(available_dates)
    earliest_date = available_dates[0]

    result: Dict[str, Dict[str, Any]] = {}
    for key, resolved in baselines.items():
        # Long windows (6M/1Y) report the SAME partial-coverage fallback as the
        # Cards Market Index for this key, via the one shared resolver, so a
        # set younger than six months never shows breadth as "unavailable"
        # while its index reports a truthful partial return for the same span.
        start_date, coverage, is_since_first_available = resolve_partial_window_coverage(
            key,
            target=resolved["targetStartDate"],
            start=resolved["startDate"],
            earliest=earliest_date,
            latest=end_date,
        )
        base = {
            "startDate": start_date,
            "endDate": end_date,
            "targetStartDate": resolved["targetStartDate"],
            "coverage": coverage,
            "isSinceFirstAvailable": is_since_first_available,
            "eligibleCount": 0,
            "advancingCount": None,
            "decliningCount": None,
            "unchangedCount": None,
            "advancingPercent": None,
            "decliningPercent": None,
            "unchangedPercent": None,
        }
        if start_date is None:
            result[key] = {
                **base,
                "available": False,
                "status": BREADTH_STATUS_INSUFFICIENT_HISTORY,
            }
            continue
        if start_date == end_date:
            # Only one point in the segment: there is no prior observation to
            # measure participation against. Reporting 100% unchanged here
            # would assert a market fact that was never observed.
            result[key] = {
                **base,
                "available": False,
                "status": BREADTH_STATUS_BASELINE_UNAVAILABLE,
            }
            continue

        start_prices = by_date[start_date]
        common = start_prices.keys() & end_prices.keys()
        if not common:
            result[key] = {
                **base,
                "available": False,
                "status": BREADTH_STATUS_NO_COMMON_COHORT,
            }
            continue

        counts = {"advancingCount": 0, "decliningCount": 0, "unchangedCount": 0}
        for card_id in common:
            start_value = start_prices[card_id]
            end_value = end_prices[card_id]
            if end_value > start_value:
                counts["advancingCount"] += 1
            elif end_value < start_value:
                counts["decliningCount"] += 1
            else:
                counts["unchangedCount"] += 1

        eligible = len(common)
        percents = _percentages(counts, eligible)
        result[key] = {
            **base,
            "available": True,
            "status": BREADTH_STATUS_AVAILABLE,
            "eligibleCount": eligible,
            **counts,
            "advancingPercent": percents["advancingCount"],
            "decliningPercent": percents["decliningCount"],
            "unchangedPercent": percents["unchangedCount"],
        }
    return result


# ---------------------------------------------------------------------------
# Reconciliation guard
# ---------------------------------------------------------------------------


def reconcile_observations_to_set_value(
    observations: Sequence[Mapping[str, Any]],
    set_value_by_date: Mapping[str, Any],
    *,
    tolerance: float = 0.01,
) -> List[Dict[str, Any]]:
    """Compare each observation's basket sum to authoritative Set Value.

    This is the standing guard on the claim this whole module rests on: that
    the Cards Index and Set Value are views of ONE basket. A builder change
    that silently narrowed the constituent universe would still produce a
    plausible-looking index; only this check would notice. Returns one row per
    comparable date; rows with ``withinTolerance`` False are drift.
    """
    findings: List[Dict[str, Any]] = []
    for observation in observations:
        market_date = str(observation.get("marketDate"))[:10]
        if market_date not in set_value_by_date:
            continue
        expected = set_value_by_date[market_date]
        if expected is None:
            continue
        basket = round(
            sum(float(row.get("setValue", row.get("set_value"))) for row in observation.get("constituents") or ()),
            2,
        )
        difference = round(basket - float(expected), 2)
        findings.append(
            {
                "marketDate": market_date,
                "basketValue": basket,
                "setValue": round(float(expected), 2),
                "absoluteDifference": difference,
                "cardCount": len(observation.get("constituents") or ()),
                "withinTolerance": abs(difference) <= tolerance,
            }
        )
    return findings


def summarize_reconciliation(findings: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """Condense reconciliation findings into publishable metadata.

    Drift is REPORTED rather than hidden. Some legacy dates genuinely cannot
    reconcile: ``pokemon_market_date_quality`` marks a pre-enforcement window
    (2026-06-24..26 DEGRADED, 06-18..23 LEGACY_VERIFIED) where the stored
    aggregate was written under a market-day convention since repaired, and on
    those dates the stored ``set_value`` for day N matches this basket's day
    N-1. Hard-failing a build on immutable history would block the pipeline
    forever over data that is already known-bad and already tracked elsewhere,
    so the summary travels with the payload and the hard assertion is reserved
    for the CURRENT date (see ``build_cards_market_analytics``), which is what
    the published index and breadth actually describe.
    """
    drift = [row for row in findings if not row["withinTolerance"]]
    return {
        "datesCompared": len(findings),
        "datesWithinTolerance": len(findings) - len(drift),
        "driftDateCount": len(drift),
        "maxAbsoluteDifference": max((abs(row["absoluteDifference"]) for row in drift), default=0.0),
        "driftDates": [row["marketDate"] for row in drift],
    }


def assert_reconciles_to_set_value(
    observations: Sequence[Mapping[str, Any]],
    set_value_by_date: Mapping[str, Any],
    *,
    tolerance: float = 0.01,
) -> None:
    drift = [
        row
        for row in reconcile_observations_to_set_value(observations, set_value_by_date, tolerance=tolerance)
        if not row["withinTolerance"]
    ]
    if drift:
        sample = ", ".join(
            f"{row['marketDate']} basket={row['basketValue']} setValue={row['setValue']}" for row in drift[:5]
        )
        raise PokemonSetCardsMarketAnalyticsError(
            f"cards constituent basket diverged from Set Value on {len(drift)} date(s): {sample}"
        )


# ---------------------------------------------------------------------------
# Composed payload
# ---------------------------------------------------------------------------


def build_cards_market_analytics_from_observations(
    observations: Sequence[Mapping[str, Any]],
) -> Dict[str, Any]:
    """Compose the canonical Cards analytics payload from shaped observations."""
    market_index = build_cards_market_index(observations)
    segment_dates = (
        [
            row["date"]
            for row in market_index["history"]
            if row["chainSegmentId"] == market_index["currentSegmentId"]
        ]
        if market_index
        else None
    )
    breadth = compute_market_breadth(observations, segment_dates=segment_dates)
    return {
        "contractVersion": CARDS_MARKET_ANALYTICS_CONTRACT_VERSION,
        "methodologyVersion": CARDS_MARKET_METHODOLOGY_VERSION,
        "constituentSource": CARD_CONSTITUENT_RPC,
        "observationCount": len(observations),
        "marketIndex": market_index,
        "marketBreadth": breadth or None,
    }


def build_cards_market_analytics(
    set_id: str,
    start_date: str,
    end_date: str,
    *,
    client: Any,
    set_value_by_date: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Load canonical constituents for one set and prepare Cards analytics.

    Computed SERVER-SIDE, during snapshot build. The underlying RPC takes
    seconds over a long history and returns tens of thousands of rows; a
    browser must never fetch those to chain-link an index itself. What is
    published is the PREPARED index history and breadth, not the raw
    constituent rows.
    """
    rows = load_card_constituent_rows(set_id, start_date, end_date, client=client)
    observations = build_constituent_observations(rows)
    payload = build_cards_market_analytics_from_observations(observations)
    payload["constituentRowCount"] = len(rows)
    payload["requestedRange"] = {"startDate": start_date, "endDate": end_date}

    if set_value_by_date:
        findings = reconcile_observations_to_set_value(observations, set_value_by_date)
        payload["setValueReconciliation"] = summarize_reconciliation(findings)
        # STRICT ON THE CURRENT DATE. The latest observation is the one the
        # published index level and breadth endpoints actually describe; if THAT
        # basket does not equal Set Value, the two surfaces are describing
        # different markets today and the build must not proceed. Older drift is
        # reported above and left to the market-date-quality layer that already
        # owns it.
        if findings and not findings[-1]["withinTolerance"]:
            latest = findings[-1]
            raise PokemonSetCardsMarketAnalyticsError(
                f"cards constituent basket diverged from Set Value on the current date "
                f"{latest['marketDate']}: basket={latest['basketValue']} setValue={latest['setValue']}"
            )
    return payload
