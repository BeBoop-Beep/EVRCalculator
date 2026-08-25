"""Canonical normalized query specification for Market Explorer card markets.

THE MODEL. Every card market this engine can produce is one point in a single
query space, not a hand-maintained list of named indices:

    ASSET -> SCOPE (eras, sets) -> SEGMENT (rarities) -> MARKET MODE (all|chase)

"Global Top 10 SIR", "Scarlet & Violet SIR All" and "Ascended Heroes SIR
Top 10" are three instances of that one spec, not three features.

FILTER FIRST, THEN RANK. This is the rule the whole module exists to enforce.
The eligible universe is narrowed by era, then set, then segment, then price
eligibility -- and ONLY THEN, if the mode is chase, is what remains ranked by
that date's canonical price. Ranking never happens before a filter, so
"Scarlet & Violet Top 10 SIR" is the ten best SIRs INSIDE Scarlet & Violet,
never the Scarlet & Violet members of a globally-ranked ten.

NO SET QUOTA. Nothing here reserves a slot for a set. One set may hold every
position in a Chase basket and another may hold none; membership is decided by
price alone. This is a deliberate reversal of an earlier direction that built
chase baskets as "top N per set, aggregated" -- a model that is still live in
pokemon_set_value_daily_history (the 'top10' value scope) and is a DIFFERENT
market from anything this module produces. The two must not be conflated.

MEMBERSHIP IS PER DATE. build_query_observations re-ranks the universe for
every single market date. Today's winners are never projected backward: a card
that entered the top ten last week was not in it a year ago, and this module
has no code path that could say otherwise. That property is what keeps the
resulting index free of survivorship bias.

WHAT THIS MODULE DOES NOT DO. It touches no database and performs no index
math. Filtering the card universe belongs to the service layer, and
chain-linking belongs to market_index; keeping this layer pure is what makes
the specification rules above cheap to test exhaustively.
"""

from __future__ import annotations

import math
from typing import Any, Iterable, Mapping, Sequence

from backend.domain.pokemon.market_index import (
    MARKET_INDEX_BASE_VALUE,
    deterministic_fingerprint,
)

MARKET_EXPLORER_QUERY_CONTRACT_VERSION = "pokemon-market-explorer-query-v1"

ASSET_CARDS = "cards"
SUPPORTED_ASSETS = (ASSET_CARDS,)

MODE_ALL = "all"
MODE_CHASE = "chase"
SUPPORTED_MODES = (MODE_ALL, MODE_CHASE)

#: The only cutoff exposed to users today. The engine is written against a
#: parameter rather than a constant so a future cutoff is a value change, but
#: publishing additional choices is a product decision, not a code one.
DEFAULT_CHASE_TOP_N = 10


class MarketExplorerQueryError(ValueError):
    """A query specification that cannot be normalized into a real market."""


def _clean_ids(values: Iterable[Any] | None) -> tuple[str, ...]:
    """Sorted, de-duplicated, blank-free identifiers.

    Sorting is what makes two equivalent user selections -- the same eras
    picked in a different order -- collapse to one fingerprint and therefore
    one cache entry.
    """
    if not values:
        return ()
    cleaned = {str(value).strip() for value in values if str(value or "").strip()}
    return tuple(sorted(cleaned))


def normalize_query_spec(
    *,
    mode: str,
    asset: str = ASSET_CARDS,
    era_ids: Iterable[Any] | None = None,
    set_ids: Iterable[Any] | None = None,
    segment_ids: Iterable[Any] | None = None,
    top_n: int | None = None,
) -> dict[str, Any]:
    """The canonical form of a Market Explorer query.

    An EMPTY collection always means "every eligible member of this dimension"
    -- no eras selected is all eras, no segments selected is all segments. It
    never means "an empty universe", so a freshly-opened filter panel describes
    the whole market rather than nothing.
    """
    asset_key = str(asset or "").strip()
    if asset_key not in SUPPORTED_ASSETS:
        raise MarketExplorerQueryError(f"unsupported asset: {asset!r}")

    mode_key = str(mode or "").strip()
    if mode_key not in SUPPORTED_MODES:
        raise MarketExplorerQueryError(f"unsupported market mode: {mode!r}")

    if mode_key == MODE_CHASE:
        resolved_top_n = DEFAULT_CHASE_TOP_N if top_n is None else int(top_n)
        if resolved_top_n <= 0:
            raise MarketExplorerQueryError("chase topN must be a positive integer")
    else:
        # topN is not part of an "all constituents" market's identity. Dropping
        # it here means mode=all queries that differ only by a stray topN
        # cannot fingerprint apart and split one cache entry into two.
        resolved_top_n = None

    return {
        "contractVersion": MARKET_EXPLORER_QUERY_CONTRACT_VERSION,
        "asset": asset_key,
        "eraIds": _clean_ids(era_ids),
        "setIds": _clean_ids(set_ids),
        "segmentIds": _clean_ids(segment_ids),
        "mode": mode_key,
        "topN": resolved_top_n,
    }


def _key_part(label: str, values: Sequence[str]) -> str:
    return f"{label}={'all' if not values else '+'.join(values)}"


def query_key(spec: Mapping[str, Any]) -> str:
    """Human-readable stable identity, e.g. cards|era=all|...|topN=10.

    This is for logs, cache keys a human has to recognise, and debugging. The
    opaque query_fingerprint is the machine identity.
    """
    return "|".join((
        str(spec["asset"]),
        _key_part("era", spec["eraIds"]),
        _key_part("set", spec["setIds"]),
        _key_part("segment", spec["segmentIds"]),
        f"mode={spec['mode']}",
        f"topN={spec['topN'] if spec['topN'] is not None else 'na'}",
    ))


def query_fingerprint(spec: Mapping[str, Any]) -> str:
    """Deterministic hash of the normalized spec, via the shared primitive."""
    return deterministic_fingerprint({
        "asset": spec["asset"],
        "eraIds": list(spec["eraIds"]),
        "setIds": list(spec["setIds"]),
        "segmentIds": list(spec["segmentIds"]),
        "mode": spec["mode"],
        "topN": spec["topN"],
        "contractVersion": spec["contractVersion"],
    })


def _price(value: Any) -> float | None:
    """A usable market price, or None.

    Zero and negative prices are NOT usable. They are dropped rather than kept,
    because a zero carried into the index reads as a total price collapse
    rather than as the missing observation it actually is.
    """
    if value is None:
        return None
    try:
        price = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(price) or price <= 0:
        return None
    return price


def rank_chase_constituents(
    constituents: Iterable[Mapping[str, Any]], top_n: int,
) -> list[dict[str, Any]]:
    """The top_n most valuable constituents, ranked and rank-stamped.

    Ties break on canonical card id. That tie-break is not cosmetic: without a
    total ordering the basket's membership could depend on database row order,
    and an index whose constituents change because a query planner changed is
    not reproducible.

    A universe smaller than top_n yields everything it has. Fewer than ten
    Chase cards is a true statement about a small filtered market, so it is
    reported rather than padded.
    """
    ordered = sorted(
        (dict(row) for row in constituents),
        key=lambda row: (-float(row["marketPrice"]), str(row["canonicalCardId"])),
    )
    selected = ordered[: max(0, int(top_n))]
    for position, row in enumerate(selected, start=1):
        row["rank"] = position
    return selected


def build_chain_linked_history_from_cohorts(
    rows: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Chain-link a series from PRE-AGGREGATED per-date cohort sums.

    WHY THIS EXISTS. `build_chain_linked_history_with_segments` needs the full
    per-card constituent list for every date to work out each day's common
    cohort. For one query that panel is 29k-64k card-date rows, which cannot
    cross the 1000-row response cap in fewer than dozens of round trips -- and
    those round trips, not the arithmetic, are essentially the entire cost of a
    query. The database can compute the common-cohort sums itself and return one
    row per DATE, so this function performs the identical chain-link arithmetic
    against sums it did not have to fetch the constituents to obtain.

    IDENTICAL MATH, NOT SIMILAR MATH. The daily return is
    ``commonCurrentValue / commonPreviousValue - 1`` over exactly the cards
    present on both days -- the same quantity the row-based function computes
    from `commonSetIds`. A roster change still cannot move the index, because a
    card present on only one of the two days is in neither sum. The two paths
    are held to byte-equality by a parity test rather than by inspection.

    COHORT BREAKS. A date sharing no constituent with the previous one starts a
    NEW chain segment at the base value, matching the row-based function: the
    index cannot describe a movement across a day with no shared constituent, so
    it declines to describe that one transition instead of fabricating it.
    """
    ordered = sorted((dict(row) for row in rows), key=lambda row: str(row["marketDate"])[:10])
    output: list[dict[str, Any]] = []
    previous_index = MARKET_INDEX_BASE_VALUE
    previous_date: str | None = None
    segment_id = 0
    segment_start: str | None = None
    seen: set[str] = set()

    for row in ordered:
        market_date = str(row["marketDate"])[:10]
        if market_date in seen:
            raise MarketExplorerQueryError(f"duplicate market date: {market_date}")
        seen.add(market_date)

        common_count = int(row.get("commonCount") or 0)
        common_previous = _price(row.get("commonPreviousValue"))
        common_current = _price(row.get("commonCurrentValue"))

        if previous_date is None:
            daily_return = None
            index_value = MARKET_INDEX_BASE_VALUE
            segment_start = market_date
        elif common_count <= 0 or common_previous is None or common_current is None:
            # No shared constituent with the previous day: start a fresh chain.
            daily_return = None
            index_value = MARKET_INDEX_BASE_VALUE
            segment_id += 1
            segment_start = market_date
        else:
            daily_return = common_current / common_previous - 1.0
            index_value = previous_index * (1.0 + daily_return)

        output.append({
            "marketDate": market_date,
            "basketValue": float(row.get("basketValue") or 0.0),
            "normalizedIndexValue": index_value,
            "dailyReturn": daily_return,
            "previousMarketDate": previous_date,
            "commonCount": common_count,
            "constituentCount": int(row.get("constituentCount") or 0),
            "eligibleUniverseCount": int(row.get("eligibleUniverseCount") or 0),
            "chainSegmentId": segment_id,
            "segmentStartDate": segment_start,
        })
        previous_index, previous_date = index_value, market_date

    return output


def build_query_observations(
    rows: Iterable[Mapping[str, Any]],
    *,
    mode: str,
    top_n: int | None,
) -> list[dict[str, Any]]:
    """One index observation per market date, with per-date chase membership.

    THE SURVIVORSHIP GUARANTEE LIVES HERE. Rows are bucketed by date and each
    bucket is ranked independently, so a Chase basket for 2026-01-01 is built
    only from prices observed on 2026-01-01. There is deliberately no
    "resolve the current top N, then look up its history" path anywhere in this
    module -- that shape is the bug this design exists to prevent.

    Output uses the shared index contract's setId/setValue field names. As in
    the set-level cards index, setId here carries a CANONICAL CARD ID; the
    naming is legacy to the generic primitive and is not reinterpreted locally.
    """
    if mode not in SUPPORTED_MODES:
        raise MarketExplorerQueryError(f"unsupported market mode: {mode!r}")

    by_date: dict[str, dict[str, dict[str, Any]]] = {}
    for row in rows:
        market_date = str(row.get("marketDate") or row.get("market_date") or "")[:10]
        card_id = str(row.get("canonicalCardId") or row.get("canonical_card_id") or "").strip()
        price = _price(row.get("marketPrice", row.get("market_price")))
        if not market_date or not card_id or price is None:
            continue
        by_date.setdefault(market_date, {})[card_id] = {
            "canonicalCardId": card_id,
            "marketPrice": price,
        }

    observations: list[dict[str, Any]] = []
    for market_date in sorted(by_date):
        universe = list(by_date[market_date].values())
        if mode == MODE_CHASE:
            selected = rank_chase_constituents(universe, int(top_n or DEFAULT_CHASE_TOP_N))
        else:
            selected = rank_chase_constituents(universe, len(universe))
        if not selected:
            continue
        observations.append({
            "marketDate": market_date,
            "requestedTopN": top_n if mode == MODE_CHASE else None,
            "eligibleUniverseCount": len(universe),
            "actualConstituentCount": len(selected),
            "constituents": [
                {
                    "setId": row["canonicalCardId"],
                    "setValue": row["marketPrice"],
                    "rank": row["rank"],
                }
                for row in selected
            ],
        })
    return observations
