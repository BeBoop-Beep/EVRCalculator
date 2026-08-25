"""The Market Explorer card query engine.

ONE ENGINE, NOT A CATALOGUE OF INDICES. Every card market Explorer can draw --
"Global SIR All", "Scarlet & Violet SIR Top 10", "Ascended Heroes SIR Top 10"
-- is this one function called with a different normalized spec. There is no
per-market request model, no "SIR chase" code path distinct from an "IR chase"
one, and adding a rarity to the taxonomy adds markets without adding code.

THE FILTER ORDER IS THE PRODUCT. Enforced top to bottom in
`resolve_query_universe` and `run_market_explorer_query`:

    1. canonical market-eligible cards in tracked sets
    2. era filter
    3. set filter
    4. segment (rarity) filter
    5. valid-price eligibility, per date
    6. THEN, and only for chase mode, rank that day's survivors and take top N

Ranking is last. That is what makes "Scarlet & Violet Top 10 SIR" the ten best
SIRs inside Scarlet & Violet rather than the Scarlet & Violet members of a
global ten -- and it is why a $1,000 non-SIR cannot appear in a SIR chase
basket no matter how expensive it is.

NO SET QUOTA, ANYWHERE. Nothing reserves a basket slot for a set. Four cards
from one set is a correct Top 10 if those are the four most valuable eligible
cards. This directly reverses the older "top N per set, aggregated globally"
construction, which remains live and correct for its own purpose in
`pokemon_set_value_daily_history` (the 'top10' value scope) and is a
DIFFERENT MARKET -- see MARKET_EXPLORER_CHASE_VS_SET_AGGREGATED_NOTE.

MEMBERSHIP IS RECOMPUTED FOR EVERY DATE. The engine loads the full per-card
daily price panel for the filtered universe and hands it to
`build_query_observations`, which ranks each date independently. No code path
resolves "today's top ten" and then fetches its history; that shape is the
survivorship bug this design exists to prevent.

TRACKED VALUE vs MARKET INDEX, as everywhere else in this domain:
  Tracked Value -- literal dollars in the day's basket. It MOVES when a card
                   enters or leaves the basket, and that is correct.
  Market Index  -- chain-linked common-cohort performance, base 100. A roster
                   swap cannot move it: the day's return is computed only over
                   the cards common to that day and the previous one, so
                   Card A leaving and Card B entering contributes nothing.

DATA AUTHORITY. Prices come only from the canonical per-card constituent RPC
already validated for the Set Market (`load_card_constituent_rows`). Never from
frontend APIs, movers payloads, chase UI lists, or ad-hoc TCGplayer calls.
"""

from __future__ import annotations

import math
import time
from typing import Any, Iterable, Mapping, Sequence

from backend.db.services.pokemon_set_cards_market_analytics_service import (
    load_card_constituent_rows,
)
from backend.domain.pokemon.card_rarity_taxonomy import (
    CARD_RARITY_TAXONOMY_VERSION,
    RAW_CARD_SEGMENT_DEFINITIONS,
    segment_key_for_rarity,
    taxonomy_metadata,
)
from backend.domain.pokemon.market_explorer_query import (
    MODE_ALL,
    MODE_CHASE,
    MarketExplorerQueryError,
    build_query_observations,
    normalize_query_spec,
    query_fingerprint,
    query_key,
)
from backend.domain.pokemon.market_index import (
    build_chain_linked_history_with_segments,
    compute_strict_window_movements,
)

MARKET_EXPLORER_QUERY_SERVICE_VERSION = "pokemon-market-explorer-query-service-v1"

#: Stated in the payload so the distinction can never be lost in a handoff.
MARKET_EXPLORER_CHASE_VS_SET_AGGREGATED_NOTE = (
    "Explorer chase baskets are globally ranked AFTER filtering: the top N of the "
    "whole filtered universe, with no per-set representation. The separately "
    "published parent chase market is built the other way -- each tracked set's own "
    "top ten, aggregated across every set -- and therefore holds roughly ten cards "
    "per tracked set, not N cards in total. They are different markets and must not "
    "be presented as the same series."
)


class MarketExplorerQueryUnavailable(RuntimeError):
    """The requested query cannot be answered from canonical authority."""


# ---------------------------------------------------------------------------
# Universe resolution (filter steps 1-4)
# ---------------------------------------------------------------------------

def _page_all(query_factory: Any, *, page_size: int = 1000) -> list[dict[str, Any]]:
    """Read every row of a PostgREST query, defeating its row cap.

    PostgREST silently truncates at its configured maximum. Paging explicitly
    is the difference between "this era has 4,000 cards" and a universe quietly
    clipped to the first thousand -- which would not error, it would just
    produce a wrong market.
    """
    rows: list[dict[str, Any]] = []
    start = 0
    while True:
        page = list((query_factory().range(start, start + page_size - 1).execute()).data or [])
        rows.extend(page)
        if len(page) < page_size:
            return rows
        start += page_size


def resolve_tracked_set_ids(client: Any) -> list[str]:
    """Sets that actually have canonical market history.

    The catalogue contains sets the market does not track. Starting from the
    tracked set list rather than the catalogue keeps the engine from issuing
    constituent reads that can only return nothing.

    READ FROM THE COVERAGE ROLLUP, NOT THE HISTORY TABLE. Both answer this
    question with the identical 167-set universe (verified: zero divergence in
    either direction), but the history table holds ~21.8k 'standard' rows and
    PostgREST has no DISTINCT, so deriving the set list from it costs ~22 paged
    round trips on EVERY query before a single price is read. The coverage
    rollup is one row per set. This is the same fact, read from the authority
    that already stores it per set.
    """
    rows = _page_all(lambda: client.table("pokemon_set_value_daily_history_coverage")
                     .select("set_id,has_history").eq("has_history", True))
    return sorted({str(row.get("set_id") or "").strip() for row in rows} - {""})


def resolve_scope_set_ids(
    client: Any, *, era_ids: Sequence[str], set_ids: Sequence[str],
) -> list[str]:
    """Sets satisfying the era AND set filters, intersected with tracked sets.

    When BOTH era and set are populated the result must satisfy both -- a set
    outside the selected era is dropped even though it was named explicitly.
    Silently honouring the set and ignoring the era would make the chart
    disagree with the filter panel the user is looking at.
    """
    tracked = set(resolve_tracked_set_ids(client))
    if not tracked:
        raise MarketExplorerQueryUnavailable("no tracked sets have market history")

    scoped = tracked
    if era_ids:
        era_rows = _page_all(lambda: client.table("sets").select("id,era_id")
                             .in_("era_id", list(era_ids)))
        scoped &= {str(row.get("id") or "").strip() for row in era_rows}
    if set_ids:
        scoped &= {str(value).strip() for value in set_ids}
    return sorted(scoped - {""})


def resolve_segment_card_universe(
    client: Any, set_ids: Sequence[str], segment_ids: Sequence[str],
) -> dict[str, dict[str, Any]]:
    """Eligible canonical cards keyed by id, after the rarity filter.

    An EMPTY ``segment_ids`` means every rarity, including rarities that are not
    published as their own segment -- "All rarities" is the whole card universe,
    not the union of the published segments.
    """
    wanted = {str(value).strip() for value in segment_ids if str(value or "").strip()}
    known = {str(definition["key"]) for definition in RAW_CARD_SEGMENT_DEFINITIONS}
    unknown = wanted - known
    if unknown:
        raise MarketExplorerQueryError(f"unknown card segment(s): {sorted(unknown)}")

    universe: dict[str, dict[str, Any]] = {}
    for set_id in set_ids:
        rows = _page_all(lambda set_id=set_id: client.table("pokemon_canonical_cards")
                         .select("id,set_id,name,rarity,number,image_small_url")
                         .eq("set_id", str(set_id)))
        for row in rows:
            card_id = str(row.get("id") or "").strip()
            if not card_id:
                continue
            segment = segment_key_for_rarity(row.get("rarity"))
            if wanted and segment not in wanted:
                continue
            universe[card_id] = {
                "canonicalCardId": card_id,
                "setId": str(row.get("set_id") or ""),
                "cardName": row.get("name"),
                "cardNumber": row.get("number"),
                "rarity": row.get("rarity"),
                "segmentKey": segment,
                "imageUrl": row.get("image_small_url"),
            }
    return universe


def load_scope_constituent_rows(
    client: Any,
    set_ids: Sequence[str],
    *,
    start_date: str,
    end_date: str,
    eligible_card_ids: Iterable[str] | None = None,
) -> list[dict[str, Any]]:
    """Per-card daily price rows for the filtered universe.

    The canonical RPC is scoped to one set per call, so a global query fans out
    across every tracked set. Rows are filtered to the eligible card set as
    they arrive rather than afterwards, which keeps a global "all rarities"
    query from materialising the entire panel twice.
    """
    allowed = None if eligible_card_ids is None else {str(value) for value in eligible_card_ids}
    rows: list[dict[str, Any]] = []
    for set_id in set_ids:
        for row in load_card_constituent_rows(
            str(set_id), str(start_date)[:10], str(end_date)[:10], client=client,
        ):
            card_id = str(row.get("canonical_card_id") or row.get("canonicalCardId") or "")
            if allowed is not None and card_id not in allowed:
                continue
            rows.append(dict(row))
    return rows


# ---------------------------------------------------------------------------
# Series construction (filter steps 5-6, then index math)
# ---------------------------------------------------------------------------

def _numeric(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def build_query_series(
    rows: Sequence[Mapping[str, Any]],
    card_metadata: Mapping[str, Mapping[str, Any]],
    *,
    mode: str,
    top_n: int | None,
) -> dict[str, Any] | None:
    """Index, tracked value and current constituents for one query.

    Window movements are confined to the CURRENT chain segment. The index
    levels either side of a cohort break are not mathematically linked, and
    spanning one would manufacture a return that no price data supports.
    """
    observations = build_query_observations(rows, mode=mode, top_n=top_n)
    if not observations:
        return None

    history = build_chain_linked_history_with_segments(observations)
    if not history:
        return None
    current_segment_id = history[-1]["chainSegmentId"]
    current = [row for row in history if row["chainSegmentId"] == current_segment_id]
    if not current:
        return None

    latest_observation = observations[-1]
    latest_row = current[-1]

    index_points = [{"date": row["marketDate"], "value": row["normalizedIndexValue"]}
                    for row in current]
    tracked_points = [{"date": row["marketDate"], "value": row["basketValue"]}
                      for row in current]

    # Section 24: every computed query publishes who is actually in it. For a
    # chase query this is the complete current basket -- there is no such thing
    # as a top ten a user cannot enumerate.
    constituents = []
    for entry in sorted(latest_observation["constituents"], key=lambda row: row["rank"]):
        card_id = str(entry["setId"])
        meta = dict(card_metadata.get(card_id) or {})
        constituents.append({
            "rank": entry["rank"],
            "canonicalCardId": card_id,
            "cardName": meta.get("cardName"),
            "cardNumber": meta.get("cardNumber"),
            "setId": meta.get("setId"),
            "setName": meta.get("setName"),
            "rarity": meta.get("rarity"),
            "segmentKey": meta.get("segmentKey"),
            "marketPrice": round(float(entry["setValue"]), 2),
            "imageUrl": meta.get("imageUrl"),
            "asOf": str(latest_observation["marketDate"])[:10],
            "queryMembershipReason": (
                f"rank {entry['rank']} by market price within the filtered universe"
                if mode == MODE_CHASE else "eligible constituent of the filtered universe"
            ),
        })

    represented_sets = {row["setId"] for row in constituents if row.get("setId")}

    return {
        "asOf": str(latest_row["marketDate"])[:10],
        "historyStartDate": str(current[0]["marketDate"])[:10],
        "indexValue": float(latest_row["normalizedIndexValue"]),
        "trackedValue": round(float(latest_row["basketValue"]), 2),
        "familyChanges": compute_strict_window_movements(index_points),
        "trackedValueChanges": compute_strict_window_movements(tracked_points),
        "trend": [[row["marketDate"], row["normalizedIndexValue"]] for row in current],
        "trackedValueHistory": [
            {"date": row["marketDate"], "value": round(float(row["basketValue"]), 2)}
            for row in current
        ],
        "currentConstituents": constituents,
        # Section 27: the information a future "entered / exited / previous
        # rank / days in chase" view needs is preserved here rather than
        # discarded after ranking. It is intentionally ids-and-ranks only --
        # carrying full card metadata for every date would multiply the payload
        # by the history length for a view that does not exist yet.
        "membershipByDate": [
            {
                "marketDate": observation["marketDate"],
                "constituentIds": [str(row["setId"]) for row in observation["constituents"]],
            }
            for observation in observations
        ],
        "reconciliation": {
            "requestedTopN": latest_observation.get("requestedTopN"),
            "actualConstituentCount": latest_observation["actualConstituentCount"],
            "eligibleUniverseCount": latest_observation["eligibleUniverseCount"],
            "currentBasketValue": round(float(latest_row["basketValue"]), 2),
            # Section 4: fewer than N is a true statement about a small market,
            # never an error and never padded.
            "belowRequestedTopN": bool(
                latest_observation.get("requestedTopN")
                and latest_observation["actualConstituentCount"] < latest_observation["requestedTopN"]
            ),
        },
        "metadata": {
            "constituentCount": latest_observation["actualConstituentCount"],
            "representedSetCount": len(represented_sets),
            "observationCount": len(observations),
            "historyPointCount": len(history),
            "currentSegmentId": current_segment_id,
            "chainSegmentCount": len({row["chainSegmentId"] for row in history}),
        },
    }


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def describe_query(spec: Mapping[str, Any], *, era_names: Mapping[str, str] | None = None,
                   set_names: Mapping[str, str] | None = None) -> str:
    """Human display label, e.g. "Scarlet & Violet - SIR - Top 10"."""
    era_names = era_names or {}
    set_names = set_names or {}
    if spec["setIds"]:
        scope = ", ".join(set_names.get(value, value) for value in spec["setIds"])
    elif spec["eraIds"]:
        scope = ", ".join(era_names.get(value, value) for value in spec["eraIds"])
    else:
        scope = "Global"

    labels = {str(d["key"]): str(d["label"]) for d in RAW_CARD_SEGMENT_DEFINITIONS}
    segment = ", ".join(labels.get(value, value) for value in spec["segmentIds"]) or "All rarities"
    market_mode = f"Top {spec['topN']}" if spec["mode"] == MODE_CHASE else "All"
    return f"{scope} · {segment} · {market_mode}"


def run_market_explorer_query(
    client: Any,
    *,
    mode: str,
    era_ids: Sequence[str] = (),
    set_ids: Sequence[str] = (),
    segment_ids: Sequence[str] = (),
    top_n: int | None = None,
    start_date: str,
    end_date: str,
) -> dict[str, Any]:
    """Resolve, compute and describe one Market Explorer card query.

    Read-only. Nothing here writes, and no snapshot is mutated as a side
    effect of a user running a query.
    """
    spec = normalize_query_spec(
        mode=mode, era_ids=era_ids, set_ids=set_ids, segment_ids=segment_ids, top_n=top_n,
    )
    started = time.perf_counter()

    scope_set_ids = resolve_scope_set_ids(
        client, era_ids=spec["eraIds"], set_ids=spec["setIds"],
    )
    if not scope_set_ids:
        raise MarketExplorerQueryUnavailable("no tracked set satisfies the selected scope")

    card_universe = resolve_segment_card_universe(client, scope_set_ids, spec["segmentIds"])
    if not card_universe:
        raise MarketExplorerQueryUnavailable("no eligible card satisfies the selected filters")

    # A set that contributes no eligible card after the segment filter cannot
    # contribute a constituent either, so its constituent read can only return
    # rows we would discard. Dropping it here is not an optimisation detail: the
    # per-set RPC is by far the dominant cost of a query, and a rarity that
    # exists in 22 of 167 tracked sets would otherwise pay for 145 pointless
    # round trips. This changes cost, never membership.
    contributing_set_ids = {meta["setId"] for meta in card_universe.values()}
    scope_set_ids = [set_id for set_id in scope_set_ids if set_id in contributing_set_ids]

    set_names = _load_set_names(client, scope_set_ids)
    era_names = _load_era_names(client, spec["eraIds"])
    for meta in card_universe.values():
        meta["setName"] = set_names.get(meta["setId"])

    rows = load_scope_constituent_rows(
        client, scope_set_ids, start_date=start_date, end_date=end_date,
        eligible_card_ids=card_universe.keys(),
    )
    series = build_query_series(
        rows, card_universe, mode=spec["mode"], top_n=spec["topN"],
    )
    if series is None:
        raise MarketExplorerQueryUnavailable("the filtered universe has no priced history")

    return {
        "serviceVersion": MARKET_EXPLORER_QUERY_SERVICE_VERSION,
        "spec": {**spec, "eraIds": list(spec["eraIds"]), "setIds": list(spec["setIds"]),
                 "segmentIds": list(spec["segmentIds"])},
        "queryKey": query_key(spec),
        "queryFingerprint": query_fingerprint(spec),
        "displayLabel": describe_query(spec, era_names=era_names, set_names=set_names),
        "taxonomyVersion": CARD_RARITY_TAXONOMY_VERSION,
        "chaseModelNote": MARKET_EXPLORER_CHASE_VS_SET_AGGREGATED_NOTE,
        "scope": {
            "resolvedSetCount": len(scope_set_ids),
            "eligibleCardCount": len(card_universe),
            "startDate": str(start_date)[:10],
            "endDate": str(end_date)[:10],
        },
        "diagnostics": {
            "constituentRowCount": len(rows),
            "elapsedSeconds": round(time.perf_counter() - started, 3),
        },
        **series,
    }


def _load_set_names(client: Any, set_ids: Sequence[str]) -> dict[str, str]:
    rows = _page_all(lambda: client.table("sets").select("id,name").in_("id", list(set_ids)))
    return {str(row.get("id")): str(row.get("name") or "") for row in rows}


def _load_era_names(client: Any, era_ids: Sequence[str]) -> dict[str, str]:
    if not era_ids:
        return {}
    rows = _page_all(lambda: client.table("eras").select("id,name").in_("id", list(era_ids)))
    return {str(row.get("id")): str(row.get("name") or "") for row in rows}


def published_segment_options() -> dict[str, Any]:
    """Backend-published segment options. The frontend has no rarity authority."""
    return taxonomy_metadata()


def build_market_explorer_filter_options(client: Any) -> dict[str, Any]:
    """Everything the filter panel is allowed to offer.

    THE PANEL HAS NO AUTHORITY OF ITS OWN. Eras, sets and segments all come
    from here, so a set the market does not track and a rarity the taxonomy
    does not publish cannot be selected in the first place -- rather than being
    selectable and then resolving to an empty market.

    Sets carry their era id so the panel can narrow the set list to the
    selected eras (section 33) without a second request.
    """
    tracked_set_ids = resolve_tracked_set_ids(client)
    if not tracked_set_ids:
        raise MarketExplorerQueryUnavailable("no tracked sets have market history")

    set_rows = _page_all(lambda: client.table("sets")
                         .select("id,name,era_id,release_date")
                         .in_("id", list(tracked_set_ids)))
    era_ids = sorted({str(row.get("era_id") or "") for row in set_rows} - {""})
    era_rows = _page_all(lambda: client.table("eras")
                         .select("id,name,sort_order").in_("id", era_ids)) if era_ids else []

    tracked_by_era: dict[str, int] = {}
    for row in set_rows:
        era_id = str(row.get("era_id") or "")
        if era_id:
            tracked_by_era[era_id] = tracked_by_era.get(era_id, 0) + 1

    return {
        "serviceVersion": MARKET_EXPLORER_QUERY_SERVICE_VERSION,
        "asset": {"id": "cards", "label": "Cards"},
        "eras": [
            {
                "id": str(row.get("id")),
                "label": str(row.get("name") or ""),
                "sortOrder": row.get("sort_order"),
                "trackedSetCount": tracked_by_era.get(str(row.get("id")), 0),
            }
            for row in sorted(era_rows, key=lambda row: (row.get("sort_order") or 0))
        ],
        "sets": [
            {
                "id": str(row.get("id")),
                "label": str(row.get("name") or ""),
                "eraId": str(row.get("era_id") or ""),
                "releaseDate": str(row.get("release_date") or "")[:10] or None,
            }
            for row in sorted(set_rows, key=lambda row: str(row.get("name") or ""))
        ],
        "segments": published_segment_options(),
        "marketModes": [
            {"id": MODE_ALL, "label": "All Constituents"},
            {"id": MODE_CHASE, "label": "Chase", "topNOptions": [10], "defaultTopN": 10},
        ],
        "chaseModelNote": MARKET_EXPLORER_CHASE_VS_SET_AGGREGATED_NOTE,
    }
