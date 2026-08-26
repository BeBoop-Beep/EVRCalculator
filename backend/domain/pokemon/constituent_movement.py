"""Per-constituent price movement for the Current Constituents table.

WHY THIS EXISTS. Current Constituents could answer "what is inside this market"
but not "how are those things moving". The aggregate market return cannot be
reused per row -- every row would print the same number and the table would be
worse than no movement column at all.

WHAT IT IS NOT. It is not a second price history and not a new query. Every
service that publishes constituents ALREADY holds the per-constituent daily
prices in memory (the card segments hold ``build_constituent_observations``
output, the sealed services hold each product's own ``history``, and both
dynamic query engines hold the same observation series). This module reads
those, so the movement contract costs no additional database round-trip and no
schema change.

WINDOW SEMANTICS ARE BORROWED, NOT REDEFINED. Baselines come from
``resolve_window_baselines`` -- the single definition of what "7D" means for
this codebase -- resolved over the MARKET'S OWN observed dates, so a
constituent's "30D" is the same span as the index's "30D".

PRESENCE IS PER CONSTITUENT. A window is only available when this constituent
was actually observed at BOTH boundary dates. A card that entered the market
nine days ago has no 30D movement, and this reports that rather than printing
0.00% or silently comparing against its first-ever price.

THE SHAPE IS SPLIT, AND THAT IS A SIZE DECISION WITH A CORRECTNESS BONUS. The
boundary DATES for a window are a property of the market, not of a card: they
come from resolving that window over the market's own observed dates, so they
are identical for every constituent in it. Publishing the full movement object
per row therefore repeated ~500 bytes of the same three dates on every card —
measured at +349% on a 25-card summary, which across every published segment is
several hundred kilobytes of duplication.

So the dates are published ONCE per market as ``movementWindows``, and each row
carries only its own percentage (``null`` where it has no comparable
observation). Beyond the size, this removes the possibility of two rows in one
market disagreeing about when "30D" started.
"""

from __future__ import annotations

import math
from typing import Any, Iterable, Mapping, Sequence

from backend.domain.pokemon.market_index import resolve_window_baselines

CONSTITUENT_MOVEMENT_CONTRACT_VERSION = "pokemon-constituent-movement-v1"

#: The compact windows the table offers. Deliberately four, not the full
#: ``WINDOWS`` tuple: the table shows ONE at a time behind a local selector, and
#: publishing 6M/1Y/SinceTracking as well would double the payload for controls
#: that do not exist.
CONSTITUENT_MOVEMENT_WINDOWS = ("1D", "7D", "30D", "3M")


def _price(value: Any) -> float | None:
    try:
        price = float(value)
    except (TypeError, ValueError):
        return None
    return price if math.isfinite(price) and price > 0 else None


def build_constituent_movements(
    prices_by_date: Mapping[str, Mapping[str, Any]],
    *,
    windows: Sequence[str] = CONSTITUENT_MOVEMENT_WINDOWS,
) -> dict[str, Any]:
    """Per-market window dates plus a percentage per constituent.

    ``prices_by_date`` maps an ISO market date to ``{constituent_id: price}``.
    That is the shape every calling service can produce from what it already
    holds, which is the point: this module never loads anything.

    Returns::

        {
          "windows": {"7D": {"startDate", "endDate", "targetStartDate",
                             "available"}, ...},
          "byConstituent": {"<id>": {"7D": 4.8, "30D": None, ...}},
        }

    ``None`` for a constituent's window means it was not observed at that
    window's start. It is NOT zero, and consumers must render it as such.
    """
    ordered_dates = sorted(str(key)[:10] for key in prices_by_date)
    if not ordered_dates:
        return {"windows": {}, "byConstituent": {}}
    baselines = resolve_window_baselines(ordered_dates)
    end_date = ordered_dates[-1]
    latest = {
        str(entity_id): price
        for entity_id, raw in (prices_by_date.get(end_date) or {}).items()
        if (price := _price(raw)) is not None
    }
    if not latest:
        return {"windows": {}, "byConstituent": {}}

    window_meta: dict[str, Any] = {}
    by_constituent: dict[str, dict[str, Any]] = {entity_id: {} for entity_id in latest}
    for window in windows:
        resolved = baselines.get(window) or {}
        start = resolved.get("startDate")
        window_meta[window] = {
            # The market as a whole cannot measure this window at all when it
            # has no baseline observation; individual rows may still be absent
            # from a window the market CAN measure.
            "available": bool(start),
            "startDate": start,
            "endDate": end_date,
            "targetStartDate": resolved.get("targetStartDate"),
        }
        start_prices = {
            str(entity_id): price
            for entity_id, raw in (prices_by_date.get(start) or {}).items()
            if start and (price := _price(raw)) is not None
        }
        for entity_id, end_price in latest.items():
            start_price = start_prices.get(entity_id)
            by_constituent[entity_id][window] = (
                None if start_price is None else (end_price / start_price - 1.0) * 100.0
            )
    return {"windows": window_meta, "byConstituent": by_constituent}


def prices_by_date_from_observations(
    observations: Iterable[Mapping[str, Any]],
) -> dict[str, dict[str, float]]:
    """``build_constituent_observations`` output -> the shape above.

    The shared index primitive names its constituent id ``setId`` and its value
    ``setValue`` regardless of what the constituent actually is; that naming is
    legacy to the domain contract and is deliberately not reinterpreted here.
    """
    result: dict[str, dict[str, float]] = {}
    for observation in observations:
        market_date = str(observation.get("marketDate") or "")[:10]
        if not market_date:
            continue
        bucket = result.setdefault(market_date, {})
        for row in observation.get("constituents") or ():
            entity_id = str(row.get("setId") or row.get("set_id") or "").strip()
            price = _price(row.get("setValue", row.get("set_value")))
            if entity_id and price is not None:
                bucket[entity_id] = price
    return {date_key: prices for date_key, prices in result.items() if prices}


def prices_by_date_from_query_rows(
    rows: Iterable[Mapping[str, Any]],
    *,
    id_field: str = "canonicalCardId",
) -> dict[str, dict[str, float]]:
    """The dynamic query engines' RAW daily rows -> the shape above.

    Deliberately the raw rows and NOT ``build_query_observations`` output: in
    Top-N mode those observations hold only that date's basket members, so a
    card ranked twelfth a month ago would report no 30D movement even though
    its price was observed every day. A constituent's own price history does
    not depend on whether it was in the basket, so movement is measured over
    the whole eligible universe.
    """
    snake_id_field = "".join(
        f"_{character.lower()}" if character.isupper() else character for character in id_field
    )
    result: dict[str, dict[str, float]] = {}
    for row in rows:
        market_date = str(row.get("marketDate") or row.get("market_date") or "")[:10]
        entity_id = str(row.get(id_field) or row.get(snake_id_field) or "").strip()
        price = _price(row.get("marketPrice", row.get("market_price")))
        if market_date and entity_id and price is not None:
            result.setdefault(market_date, {})[entity_id] = price
    return result


def prices_by_date_from_product_histories(
    products: Iterable[Mapping[str, Any]],
    *,
    id_field: str = "sealedProductId",
    history_field: str = "history",
    price_field: str = "marketPrice",
) -> dict[str, dict[str, float]]:
    """Sealed products, each carrying its own normalized daily USD history."""
    result: dict[str, dict[str, float]] = {}
    for product in products:
        entity_id = str(product.get(id_field) or "").strip()
        if not entity_id:
            continue
        for point in product.get(history_field) or ():
            market_date = str(point.get("date") or "")[:10]
            price = _price(point.get(price_field))
            if market_date and price is not None:
                result.setdefault(market_date, {})[entity_id] = price
    return result
