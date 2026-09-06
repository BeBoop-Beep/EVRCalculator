"""THE one construction of the published ``marketOverview``.

The publisher and parity audit must resolve the same market cohort and build the
same payload. Historical-era rollout is intentionally independent of RIP/opening
eligibility: activated root sets join Sealed as roots, while Raw Card expands
those roots to every child subset that counts toward parent Set Value.
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
from backend.db.services.pokemon_market_rollout_cohort import (
    expand_raw_card_member_set_ids,
    resolve_market_root_cohort,
)

logger = logging.getLogger(__name__)


def resolve_canonical_overview_sets(client: Any, *, market_date: str) -> list[dict[str, Any]]:
    """Current public Market roots plus explicitly activated rollout-era roots."""
    return resolve_market_root_cohort(client, market_date=market_date)


def build_canonical_market_overview(
    client: Any,
    *,
    market_date: str,
    history: Sequence[Mapping[str, Any]],
    set_ids: Sequence[str],
) -> dict[str, Any]:
    """Build the complete published Market Overview for ``market_date``.

    ``set_ids`` are one-row-per-parent/root market constituents. Sealed products
    are owned by those roots. Raw cards expand the same roots through
    ``counts_toward_parent_set_value`` so Trainer Galleries, Shiny Vaults,
    Galarian Gallery and other configured subsets are present without becoming
    separate Set Market rows or separate Top-10 baskets.
    """
    root_ids = [str(value) for value in set_ids]

    sealed_rows = read_global_sealed_source_snapshots(client, root_ids)
    sealed_payloads = [dict(row.get("payload_json") or {}) for row in sealed_rows]
    sealed_market = build_global_sealed_market(sealed_payloads, market_date=market_date)
    sealed_segments = build_global_sealed_segments(
        sealed_payloads,
        market_date=market_date,
        total=sealed_market,
    )

    try:
        raw_history_start = min(
            (
                str(row.get("market_date"))[:10]
                for row in history
                if str(row.get("index_key")) == "raw"
            ),
            default=market_date,
        )
        raw_member_set_ids = expand_raw_card_member_set_ids(client, root_ids)
        rarity_by_card = read_canonical_card_rarities(client, raw_member_set_ids)
        constituent_rows = load_global_card_constituent_rows(
            client,
            raw_member_set_ids,
            start_date=raw_history_start,
            end_date=market_date,
        )
        raw_card_segments = build_global_card_segments(
            constituent_rows,
            rarity_by_card,
            market_date=market_date,
            parent_basket_value=None,
        )
        card_segments = build_card_segments_payload(raw_card_segments)
    except Exception as exc:  # noqa: BLE001 - additive analytics only
        logger.warning("card segments unavailable: %s", exc)
        card_segments = build_card_segments_payload(None)

    overview = build_market_overview(
        history,
        market_date=market_date,
        sealed_market=sealed_market,
        sealed_segments=sealed_segments,
        card_segments=card_segments,
    )
    if card_segments and isinstance(card_segments.get("raw"), dict):
        card_segments["raw"].setdefault("reconciliation", {})
        card_segments["raw"]["reconciliation"]["parentBasketValue"] = (
            overview.get("raw", {}).get("basketValue")
        )
    return overview
