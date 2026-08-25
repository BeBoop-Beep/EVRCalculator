"""Global card-rarity submarkets for the Raw Card Market.

METHODOLOGY. Each rarity submarket is built from ITS OWN canonical card
constituents — the same per-card daily rows behind the set-level Cards Market
Index (``get_pokemon_set_daily_card_constituents``), unioned across every
eligible tracked set and then partitioned by canonical rarity. Each card is one
constituent, and each segment is chain-linked over its own common cohort via
the shared ``build_chain_linked_history_with_segments``.

WHAT IS DELIBERATELY NOT DONE:
  * no averaging of set-level Cards Market Index values,
  * no filtering of an already-aggregated index,
  * no deriving a segment from Tracked Value percentage change,
  * no reconstruction of Top Chase membership by re-ranking cards.

PARENT REGRESSION. The Raw Card Market itself is NOT rebuilt here. It continues
to come from ``pokemon_set_value_daily_history`` exactly as before; these
segments are additive child analytics that never touch it.

TRACKED VALUE vs MARKET INDEX, as everywhere else in this domain:
  Tracked Value  — literal dollars of that rarity's tracked basket. It moves
                   when a card enters or leaves the tracked universe, and that
                   is correct.
  Market Index   — chain-linked common-cohort price performance, base 100. A
                   card entering cannot move it: that day's return is computed
                   only over the cohort common to that day and the previous one.
"""

from __future__ import annotations

import math
from typing import Any, Iterable, Mapping, Sequence

from backend.db.services.pokemon_set_cards_market_analytics_service import (
    build_constituent_observations,
    load_card_constituent_rows,
)
from backend.domain.pokemon.card_rarity_taxonomy import (
    CARD_RARITY_TAXONOMY_VERSION,
    RAW_CARD_SEGMENT_DEFINITIONS,
    RESIDUAL_CARD_SEGMENT_KEY,
    RESIDUAL_CARD_SEGMENT_LABEL,
    meets_quality_gate,
    normalize_rarity,
    segment_key_for_rarity,
    taxonomy_metadata,
)
from backend.domain.pokemon.market_index import (
    build_chain_linked_history_with_segments,
    compute_strict_window_movements,
    deterministic_fingerprint,
)

CARD_SEGMENT_CONTRACT_VERSION = "pokemon-card-segments-v1"

#: Why Top Chase rarity submarkets are not published. Stated in the payload so
#: the gap is visible to consumers rather than looking like an omission.
TOP_CHASE_SEGMENTS_UNAVAILABLE_REASON = (
    "The canonical Top 10 Chase index is built from per-set aggregate rows "
    "(pokemon_set_value_daily_history, value_scope='top10') that do not publish which "
    "ten cards they contain. No per-date, per-card Top Chase membership authority "
    "covering the full tracked cohort exists, and re-ranking cards to reconstruct one "
    "would be a second, divergent definition of Top Chase."
)


class GlobalCardSegmentsUnavailable(RuntimeError):
    pass


def read_canonical_card_rarities(client: Any, set_ids: Sequence[str]) -> dict[str, dict[str, Any]]:
    """Canonical rarity for every card in the tracked sets, read in pages.

    One read of the canonical card catalogue; no per-card queries.
    """
    result: dict[str, dict[str, Any]] = {}
    for set_id in set_ids:
        start = 0
        while True:
            page = list((client.table("pokemon_canonical_cards")
                         .select("id,set_id,name,rarity")
                         .eq("set_id", str(set_id))
                         .range(start, start + 999).execute()).data or [])
            for row in page:
                card_id = str(row.get("id") or "").strip()
                if card_id:
                    result[card_id] = {
                        "canonicalCardId": card_id,
                        "setId": str(row.get("set_id") or ""),
                        "name": row.get("name"),
                        "rawRarity": row.get("rarity"),
                        "rarityKey": normalize_rarity(row.get("rarity")),
                    }
            if len(page) < 1000:
                break
            start += 1000
    return result


def load_global_card_constituent_rows(
    client: Any, set_ids: Sequence[str], *, start_date: str, end_date: str,
) -> list[dict[str, Any]]:
    """Per-card daily rows across every tracked set, via the canonical RPC.

    The loader is the set-level one, called once per set. It already handles
    the PostgREST row cap by date-chunking; nothing here re-implements paging.
    """
    rows: list[dict[str, Any]] = []
    for set_id in set_ids:
        rows.extend(load_card_constituent_rows(
            str(set_id), str(start_date)[:10], str(end_date)[:10], client=client,
        ))
    return rows


def partition_constituent_rows(
    rows: Iterable[Mapping[str, Any]], rarity_by_card: Mapping[str, Mapping[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """Split per-card daily rows into published rarity segments plus residual.

    A row whose card is not in the canonical catalogue cannot be classified and
    goes to the residual — it still belongs to the parent market, so dropping
    it would break reconciliation.
    """
    grouped: dict[str, list[dict[str, Any]]] = {
        str(definition["key"]): [] for definition in RAW_CARD_SEGMENT_DEFINITIONS
    }
    grouped[RESIDUAL_CARD_SEGMENT_KEY] = []
    for row in rows:
        card_id = str(row.get("canonical_card_id") or row.get("canonicalCardId") or "").strip()
        if not card_id:
            continue
        card = rarity_by_card.get(card_id)
        key = segment_key_for_rarity(card.get("rawRarity")) if card else None
        grouped[key if key is not None else RESIDUAL_CARD_SEGMENT_KEY].append(dict(row))
    return grouped


def _numeric(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _segment_series(
    rows: Sequence[Mapping[str, Any]],
    rarity_by_card: Mapping[str, Mapping[str, Any]],
    *,
    market_date: str,
) -> dict[str, Any] | None:
    """Build ONE rarity submarket from its own per-card daily observations."""
    observations = build_constituent_observations(rows)
    if not observations:
        return None
    # The published market date must actually be observed; a segment that does
    # not reach it is reported unavailable rather than shown as of a stale day.
    latest = observations[-1]
    if str(latest["marketDate"])[:10] != str(market_date)[:10]:
        return None

    history = build_chain_linked_history_with_segments(observations)
    if not history:
        return None
    current_segment_id = history[-1]["chainSegmentId"]
    # WINDOW RETURNS MUST NOT CROSS A CHAIN BREAK: the two index levels either
    # side of one are not mathematically linked, so movements are computed over
    # the CURRENT segment only.
    current = [row for row in history if row["chainSegmentId"] == current_segment_id]
    if not current:
        return None

    index_points = [
        {"date": row["marketDate"], "value": row["normalizedIndexValue"]} for row in current
    ]
    basket_points = [
        {"date": row["marketDate"], "value": row["basketValue"]} for row in current
    ]

    today_cards = {
        str(entry["setId"]) for entry in latest["constituents"]
    }
    today_sets = {
        str((rarity_by_card.get(card_id) or {}).get("setId") or "") for card_id in today_cards
    }
    today_sets.discard("")

    return {
        "basketValue": round(float(current[-1]["basketValue"]), 2),
        "indexValue": float(current[-1]["normalizedIndexValue"]),
        "historyStartDate": str(current[0]["marketDate"])[:10],
        # The segment's OWN window movements, from its own tracking start.
        # build_market_overview later adds the shared-comparison `changes`;
        # these are never overwritten.
        "familyChanges": compute_strict_window_movements(index_points),
        # Tracked Value is a separate published series and deliberately DOES
        # move on constituent entry/exit.
        "basketChanges": compute_strict_window_movements(basket_points),
        "trend": [[row["marketDate"], row["normalizedIndexValue"]] for row in current],
        "trackedValueHistory": [
            {"date": row["marketDate"], "value": round(float(row["basketValue"]), 2)}
            for row in current
        ],
        "metadata": {
            "cardCount": len(today_cards),
            "setCount": len(today_sets),
            "historyPointCount": len(history),
            "currentSegmentId": current_segment_id,
            "trackingStart": str(current[0]["marketDate"])[:10],
            "observationCount": len(observations),
        },
    }


def build_global_card_segments(
    constituent_rows: Iterable[Mapping[str, Any]],
    rarity_by_card: Mapping[str, Mapping[str, Any]],
    *,
    market_date: str,
    parent_basket_value: float | None = None,
) -> dict[str, Any]:
    """Publish the Raw Card Market's rarity submarkets, plus the residual report.

    Segments that fail the quality gate are published as explicitly unavailable
    rather than omitted, so a consumer can tell "too thin to index" apart from
    "does not exist".
    """
    grouped = partition_constituent_rows(constituent_rows, rarity_by_card)

    segments: dict[str, Any] = {}
    # Baskets of segments that were BUILDABLE but did not clear the gate. Their
    # cards are real and still belong to the parent, so they must land in the
    # residual rather than vanishing from the reconciliation.
    ungated_basket = 0.0
    for definition in RAW_CARD_SEGMENT_DEFINITIONS:
        key = str(definition["key"])
        base = {
            "key": key,
            "label": definition["label"],
            "parentMarket": "raw",
            "isParent": False,
            "rarityKeys": list(definition["rarityKeys"]),
            "definition": definition["definition"],
            "taxonomyVersion": CARD_RARITY_TAXONOMY_VERSION,
        }
        series = _segment_series(grouped.get(key) or [], rarity_by_card, market_date=market_date)
        if series is None:
            segments[key] = {**base, "available": False,
                             "unavailableReason": "no eligible constituent history"}
            continue
        if not meets_quality_gate(card_count=series["metadata"]["cardCount"],
                                  set_count=series["metadata"]["setCount"]):
            ungated_basket += float(series["basketValue"] or 0.0)
            segments[key] = {
                **base, "available": False,
                "unavailableReason": "below the published segment quality gate",
                "metadata": series["metadata"],
            }
            continue
        segments[key] = {**base, **series, "available": True}

    residual_series = _segment_series(
        grouped.get(RESIDUAL_CARD_SEGMENT_KEY) or [], rarity_by_card, market_date=market_date
    )
    published_basket = sum(
        float(segments[str(definition["key"])].get("basketValue") or 0.0)
        for definition in RAW_CARD_SEGMENT_DEFINITIONS
        if segments[str(definition["key"])].get("available") is True
    )
    residual_basket = float((residual_series or {}).get("basketValue") or 0.0) + ungated_basket

    return {
        "contractVersion": CARD_SEGMENT_CONTRACT_VERSION,
        "segments": segments,
        "definitions": taxonomy_metadata(),
        "reconciliation": {
            "parentMarket": "raw",
            "parentBasketValue": _numeric(parent_basket_value),
            "publishedSegmentBasketValue": round(published_basket, 2),
            "residual": {
                "key": RESIDUAL_CARD_SEGMENT_KEY,
                "label": RESIDUAL_CARD_SEGMENT_LABEL,
                "basketValue": round(residual_basket, 2),
                "cardCount": len({
                    str(row.get("canonical_card_id") or row.get("canonicalCardId") or "")
                    for row in (grouped.get(RESIDUAL_CARD_SEGMENT_KEY) or [])
                    if str(row.get("market_date") or row.get("marketDate") or "")[:10] == str(market_date)[:10]
                }),
            },
        },
        "sourceGenerationFingerprint": deterministic_fingerprint([
            market_date,
            CARD_RARITY_TAXONOMY_VERSION,
            *sorted(f"{key}:{len(value)}" for key, value in grouped.items()),
        ]),
    }


def build_card_segments_payload(
    raw_segments: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """The published `cardSegments` collection.

    `topChase` is present and explicitly unavailable with a stated reason. It is
    deliberately NOT omitted: a missing key reads as "not built yet", while an
    unavailable one with a reason records exactly which authority is missing.
    """
    return {
        "contractVersion": CARD_SEGMENT_CONTRACT_VERSION,
        "raw": dict(raw_segments) if raw_segments is not None else {
            "segments": {}, "definitions": taxonomy_metadata(),
            "available": False, "unavailableReason": "no card constituent history",
        },
        "topChase": {
            "available": False,
            "segments": {},
            "unavailableReason": TOP_CHASE_SEGMENTS_UNAVAILABLE_REASON,
        },
    }
