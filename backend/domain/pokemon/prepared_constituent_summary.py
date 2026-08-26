"""The prepared CURRENT-COMPOSITION summary published on each market segment.

WHY THIS EXISTS. A user looking at the SIR or ETB line should be able to see
what is inside it. Today that is only possible for a dynamically built market,
because the published quick segments carry analytics but no composition -- so
"what is in this index" can only be answered by running the query engine, which
is exactly the expensive path quick segments exist to avoid.

WHAT IT IS NOT. It is not a second history and not a re-derivation. It is the
CURRENT roster only: the constituents that make up the segment's latest basket,
with the price that basket used. No historical observation is published here.

WHY IT IS BOUNDED. A broad card segment can hold thousands of cards. Publishing
all of them would inflate every consumer's snapshot for a table nobody scrolls
to the end of, so card segments publish the top ``limit`` by current price and
state the true total alongside. The field is named ``topConstituents`` precisely
so a consumer cannot mistake a bounded preview for the whole universe, and
``isComplete`` says which it is. Sealed families are small enough that the
roster is usually complete; the same shape reports that honestly rather than
needing a second contract.

MOVEMENT (v2). The summary may carry ``movementWindows`` -- the 1D/7D/30D/3M
boundary dates for THIS market, published once -- and each row a ``changes`` map
of window to percentage. That split is deliberate: the dates are a property of
the market, identical for every constituent in it, and repeating them per row
measured at +349% on a 25-card summary. ``null`` for a row's window means it had
no comparable observation at that window's start; it is NOT zero.

The movement is computed by ``constituent_movement`` from the SAME in-memory
daily prices the caller already holds, so it costs no extra query and no schema
change, and only the four compact windows are published -- never a per-row
history array. A caller with no movement available omits it, and the fields are
absent rather than zero.
"""

from __future__ import annotations

import math
from typing import Any, Iterable, Mapping

PREPARED_CONSTITUENT_SUMMARY_VERSION = "pokemon-prepared-constituent-summary-v2"

#: Bound for broad card segments. Sized for a table a user actually reads, not
#: for completeness -- completeness is what the dynamic query engine is for.
DEFAULT_CARD_CONSTITUENT_LIMIT = 25

#: Sealed families are typically a handful to a few hundred products, so the
#: bound is generous enough to be complete in practice while still capping a
#: pathological set.
DEFAULT_SEALED_CONSTITUENT_LIMIT = 250


def _price(value: Any) -> float | None:
    try:
        price = float(value)
    except (TypeError, ValueError):
        return None
    return price if math.isfinite(price) and price > 0 else None


def build_prepared_constituent_summary(
    rows: Iterable[Mapping[str, Any]],
    *,
    as_of: str | None,
    id_field: str,
    limit: int,
    movements: Mapping[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Current composition for one segment, ordered by price descending.

    ``rows`` are already-identified constituents carrying at least ``id_field``
    and ``marketPrice``; every other key is published verbatim, which is what
    keeps this helper asset-neutral (a card row carries ``rarity``, a sealed row
    carries ``productFamily``, and neither grows a fake field to match the
    other).

    Ties break on the constituent id so the published preview is reproducible
    rather than dependent on the order rows were assembled in.

    Returns ``None`` when there is nothing to describe; callers omit the field
    rather than publishing an empty roster that reads as "this index is empty".
    """
    usable = []
    for row in rows:
        entity_id = str(row.get(id_field) or "").strip()
        price = _price(row.get("marketPrice"))
        if not entity_id or price is None:
            continue
        usable.append({**dict(row), id_field: entity_id, "marketPrice": round(price, 2)})
    if not usable:
        return None

    usable.sort(key=lambda row: (-row["marketPrice"], row[id_field]))
    bound = max(0, int(limit))
    selected = usable[:bound]
    for position, row in enumerate(selected, start=1):
        row["rank"] = position
        # Attached ONLY to the published preview: publishing movement for a
        # universe of thousands and then showing 25 rows would be wasted
        # payload.
        change = ((movements or {}).get("byConstituent") or {}).get(row[id_field])
        if change is not None:
            row["changes"] = dict(change)

    return {
        "contractVersion": PREPARED_CONSTITUENT_SUMMARY_VERSION,
        "asOf": str(as_of or "")[:10] or None,
        "totalCount": len(usable),
        "limit": bound,
        # Stated, not inferred: a consumer must never have to compare lengths to
        # find out whether it is holding the whole market.
        "isComplete": len(selected) == len(usable),
        "idField": id_field,
        # Stated so a consumer can tell "this publication predates movement"
        # apart from "these constituents genuinely have no comparable history".
        "hasMovement": any("changes" in row for row in selected),
        # The window boundary dates for THIS market, published once rather than
        # repeated on every row.
        "movementWindows": dict((movements or {}).get("windows") or {}),
        "topConstituents": selected,
    }


def summarize_card_segment_constituents(
    rows: Iterable[Mapping[str, Any]],
    *,
    as_of: str | None,
    limit: int = DEFAULT_CARD_CONSTITUENT_LIMIT,
    movements: Mapping[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Bounded current composition for one published card-rarity segment."""
    return build_prepared_constituent_summary(
        rows, as_of=as_of, id_field="canonicalCardId", limit=limit, movements=movements,
    )


def summarize_sealed_segment_constituents(
    rows: Iterable[Mapping[str, Any]],
    *,
    as_of: str | None,
    limit: int = DEFAULT_SEALED_CONSTITUENT_LIMIT,
    movements: Mapping[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Current composition for one published sealed product-family segment."""
    return build_prepared_constituent_summary(
        rows, as_of=as_of, id_field="sealedProductId", limit=limit, movements=movements,
    )
