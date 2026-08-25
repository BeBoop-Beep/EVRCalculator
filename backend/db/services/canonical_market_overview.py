"""THE one construction of the published `marketOverview`.

WHY THIS EXISTS. The Market snapshot publisher
(``build_pokemon_explore_set_value_snapshot.py``) and the publication parity
audit (``audit_pokemon_market_index_publication.py``) both need to produce "the
overview this market date should have". They used to build it independently,
and they drifted: the publisher grew ``cardSegments`` while the audit kept
composing an overview without it, so the audit reported

    marketOverview keys mismatch (unexpected in actual: ['cardSegments'])

against a perfectly healthy snapshot — and because a keys mismatch stops the
recursive comparison at that level, the false failure also HID a real one (the
prepared ``currentConstituents`` summaries missing from a stale snapshot).

So the rule is: an additive Market contract is added HERE, once, and both the
publisher and the audit inherit it. Neither may enumerate contract keys of its
own, because a key one of them forgets is exactly the drift this module exists
to make impossible.

WHAT IS AND IS NOT DETERMINISTIC. Everything here is a pure function of
(``client`` reads at ``market_date``, ``history``, ``set_ids``). Two callers
passing the same inputs get byte-identical output, which is what lets the audit
compare its build against the published payload as strict equality.
"""

from __future__ import annotations

import logging
from typing import Any, Mapping, Sequence

from backend.db.services.pokemon_global_card_market_segments_service import (
    build_card_segments_payload,
    build_global_card_segments,
    load_global_card_constituent_rows,
    read_canonical_card_rarities,
)
from backend.db.services.pokemon_global_sealed_market_service import (
    build_global_sealed_market,
    build_global_sealed_segments,
    read_global_sealed_source_snapshots,
)
from backend.db.services.pokemon_market_index_service import build_market_overview
from backend.desirability.public_analytics_policy import is_public_analytics_eligible

logger = logging.getLogger(__name__)

#: Columns the Market cohort read needs. Kept here so the publisher and the
#: audit resolve the SAME set rows rather than two similar-looking queries.
_SET_COLUMNS = (
    "id,canonical_key,name,era_id,release_date,logo_image_url,symbol_image_url,"
    "supports_opening_simulation"
)


def resolve_canonical_overview_sets(client: Any, *, market_date: str) -> list[dict[str, Any]]:
    """The eligible Market cohort as of ``market_date``, with era names attached.

    A set qualifies when it supports opening simulation, is eligible for public
    analytics, and had actually been released by ``market_date`` — an unreleased
    set must not enter a point-in-time build for an earlier date.
    """
    rows = list(client.table("sets").select(_SET_COLUMNS).execute().data or [])
    eligible = [
        row
        for row in rows
        if row.get("supports_opening_simulation") is True
        and is_public_analytics_eligible(row)
        and (not row.get("release_date") or str(row["release_date"])[:10] <= market_date)
    ]
    era_ids = sorted({str(row.get("era_id")) for row in eligible if row.get("era_id")})
    eras: dict[str, Any] = {}
    if era_ids:
        eras = {
            str(row.get("id")): row.get("name")
            for row in (client.table("eras").select("id,name").in_("id", era_ids).execute().data or [])
        }
    return [{**row, "era": eras.get(str(row.get("era_id")))} for row in eligible]


def build_canonical_market_overview(
    client: Any,
    *,
    market_date: str,
    history: Sequence[Mapping[str, Any]],
    set_ids: Sequence[str],
) -> dict[str, Any]:
    """Build the complete published `marketOverview` for ``market_date``.

    ``history`` is the accepted index history (raw + top10) the overview is
    chain-linked from; ``set_ids`` is the cohort every submarket is built over,
    so parent and children are guaranteed to share one constituent universe.
    """
    ids = [str(value) for value in set_ids]

    sealed_rows = read_global_sealed_source_snapshots(client, ids)
    sealed_payloads = [dict(row.get("payload_json") or {}) for row in sealed_rows]
    sealed_market = build_global_sealed_market(sealed_payloads, market_date=market_date)
    # Sealed product-family submarkets, built from the SAME constituent
    # universe the parent used and republishing the parent verbatim.
    sealed_segments = build_global_sealed_segments(
        sealed_payloads, market_date=market_date, total=sealed_market
    )

    # Card-rarity submarkets of the Raw Card Market, built from canonical
    # per-card constituents over the window Raw itself already covers. A
    # failure here must not take the whole Market snapshot down: the
    # segments are additive, so they degrade to unavailable.
    try:
        raw_history_start = min(
            (
                str(row.get("market_date"))[:10]
                for row in history
                if str(row.get("index_key")) == "raw"
            ),
            default=market_date,
        )
        rarity_by_card = read_canonical_card_rarities(client, ids)
        constituent_rows = load_global_card_constituent_rows(
            client, ids, start_date=raw_history_start, end_date=market_date,
        )
        raw_card_segments = build_global_card_segments(
            constituent_rows, rarity_by_card, market_date=market_date,
            parent_basket_value=None,
        )
        card_segments = build_card_segments_payload(raw_card_segments)
    except Exception as exc:  # noqa: BLE001 - additive analytics only
        logger.warning("card segments unavailable: %s", exc)
        card_segments = build_card_segments_payload(None)

    overview = build_market_overview(
        history, market_date=market_date,
        sealed_market=sealed_market, sealed_segments=sealed_segments,
        card_segments=card_segments,
    )
    if card_segments and isinstance(card_segments.get("raw"), dict):
        # The parent's published basket value is the reconciliation anchor,
        # and it is read from the built overview rather than recomputed.
        card_segments["raw"].setdefault("reconciliation", {})
        card_segments["raw"]["reconciliation"]["parentBasketValue"] = (
            overview.get("raw", {}).get("basketValue")
        )
    return overview
