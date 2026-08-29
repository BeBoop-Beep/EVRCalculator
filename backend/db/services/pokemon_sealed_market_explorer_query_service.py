"""The Market Explorer sealed-product query engine.

ONE ENGINE, NOT A CATALOGUE. Every sealed market Explorer can draw -- "Global
ETBs All", "Scarlet & Violet ETBs All", "Global Booster Boxes Top 10" -- is this
one function called with a different normalized spec. There is deliberately no
``build_sv_etb_market``/``build_booster_box_top10`` family of methods: adding a
product family to the published taxonomy adds markets without adding code.

THE FILTER ORDER IS THE PRODUCT, exactly as for cards:

    1. canonically eligible sealed SKUs in sets with prepared sealed snapshots
    2. era filter
    3. set filter
    4. product-family filter
    5. valid-price eligibility, per date
    6. THEN, and only for top mode, rank that day's survivors and take top N

Ranking is last. "Scarlet & Violet Booster Boxes Top 10" is therefore the ten
most valuable Booster Boxes INSIDE Scarlet & Violet, never the Scarlet & Violet
members of a globally-ranked ten -- and a $5,000 Pokemon Center ETB cannot enter
a standard ETB basket no matter how expensive it is, because the family filter
already removed it.

NO SET QUOTA. Nothing reserves a basket slot for a set. Four Booster Boxes from
one set is a correct Top 10 if those are the four most valuable eligible boxes,
and a set may contribute none.

MEMBERSHIP IS RECOMPUTED FOR EVERY DATE. The per-product daily panel is handed
to ``build_query_observations``, which ranks each date independently. No code
path resolves "today's ten most expensive products" and then fetches their
history; that shape is the survivorship bug this design exists to prevent.

DATA AUTHORITY -- THIS ENGINE HAS NONE OF ITS OWN. Products, eligibility,
normalized daily USD histories, freshness and family identity all come from the
prepared set-level sealed snapshots via ``read_global_sealed_source_snapshots``
and ``collect_global_sealed_products`` -- the SAME authority the published
Global Sealed Market and its product-family submarkets are built from. There is
no second sealed pricing model here, no re-classification, and no direct
product-price read. A dynamic "Global ETBs All" query and the published ETB
submarket are two views of one constituent universe.

WHY THERE IS NO COHORT RPC HERE. The card engine reads per-date aggregates from
the database because its panel is 29k-64k card-date rows. The sealed universe is
roughly three orders of magnitude smaller and its full normalized histories are
ALREADY MATERIALISED inside the prepared snapshots this engine reads, so the
panel is assembled in memory from data already in hand. Adding an RPC would mean
a second sealed price path to keep in agreement with the first.
"""

from __future__ import annotations

import time
from typing import Any, Iterable, Mapping, Sequence

from backend.db.services.pokemon_global_sealed_market_service import (
    GlobalSealedMarketUnavailable,
    collect_global_sealed_products,
    read_global_sealed_source_snapshots,
)
from backend.domain.pokemon.constituent_movement import (
    build_constituent_movements,
    prices_by_date_from_query_rows,
)
from backend.domain.pokemon.market_explorer_query import (
    ASSET_SEALED,
    MODE_ALL,
    MODE_CHASE,
    MarketExplorerQueryError,
    build_query_observations,
    filter_point_in_time_rows,
    normalize_query_spec,
    query_fingerprint,
    query_key,
    rank_constituents,
)
from backend.domain.pokemon.market_index import (
    build_chain_linked_history_with_segments,
    compute_strict_window_movements,
)
from backend.domain.pokemon.sealed_market_segments import (
    SEALED_SEGMENT_CONTRACT_VERSION,
    SEALED_SEGMENT_DEFINITIONS,
    segment_definition_metadata,
)

SEALED_EXPLORER_QUERY_SERVICE_VERSION = "pokemon-sealed-market-explorer-query-service-v1"

#: The constituent identifier for this asset. Named once so the spec layer, the
#: observation builder and the ranker cannot disagree about it.
SEALED_ID_FIELD = "sealedProductId"


class SealedMarketExplorerQueryUnavailable(RuntimeError):
    """The requested sealed query cannot be answered from canonical authority."""


# ---------------------------------------------------------------------------
# Universe resolution (filter steps 1-4)
# ---------------------------------------------------------------------------

def resolve_sealed_tracked_set_ids(client: Any, *, page_size: int = 1000) -> list[str]:
    """Sets that have a prepared sealed snapshot.

    This, not the set catalogue, is the sealed universe: a set with no prepared
    snapshot has no eligible sealed history, and asking for one raises rather
    than silently contributing nothing.
    """
    rows: list[dict[str, Any]] = []
    start = 0
    while True:
        page = list((client.table("pokemon_set_sealed_market_snapshot_latest")
                     .select("set_id")
                     .range(start, start + page_size - 1).execute()).data or [])
        rows.extend(page)
        if len(page) < page_size:
            break
        start += page_size
    return sorted({str(row.get("set_id") or "").strip() for row in rows} - {""})


def resolve_sealed_scope_set_ids(
    client: Any, *, era_ids: Sequence[str], set_ids: Sequence[str],
) -> list[str]:
    """Sets satisfying the era AND set filters, intersected with tracked sets.

    When BOTH era and set are populated the result must satisfy both. Silently
    honouring the set and ignoring the era would make the chart disagree with
    the filter panel the user is looking at.
    """
    tracked = set(resolve_sealed_tracked_set_ids(client))
    if not tracked:
        raise SealedMarketExplorerQueryUnavailable("no set has a prepared sealed snapshot")

    scoped = tracked
    if era_ids:
        era_rows = list((client.table("sets").select("id,era_id")
                         .in_("era_id", list(era_ids)).execute()).data or [])
        scoped &= {str(row.get("id") or "").strip() for row in era_rows}
    if set_ids:
        scoped &= {str(value).strip() for value in set_ids}
    return sorted(scoped - {""})


def families_for_segments(segment_ids: Sequence[str]) -> frozenset[str] | None:
    """Canonical classifier family keys for the requested published segments.

    ``None`` means "no family filter" -- every eligible product, which is what
    an empty segment selection means everywhere in this spec.

    THE UNION IS THE TAXONOMY'S, NOT THIS MODULE'S. Packs is a declared
    composite of loose and sleeved booster packs; Pokemon Center ETBs are their
    own segment and are never folded into standard ETBs; Half and Enhanced
    Booster Boxes belong to no published segment and therefore cannot be
    selected. All three facts are read from SEALED_SEGMENT_DEFINITIONS rather
    than restated here.
    """
    wanted = {str(value).strip() for value in segment_ids if str(value or "").strip()}
    if not wanted:
        return None
    by_key = {str(definition["key"]): definition for definition in SEALED_SEGMENT_DEFINITIONS}
    unknown = sorted(wanted - set(by_key))
    if unknown:
        raise MarketExplorerQueryError(f"unknown sealed product family segment(s): {unknown}")
    return frozenset(
        family for key in wanted for family in by_key[key]["productFamilies"]
    )


def filter_products_by_family(
    products: Iterable[Mapping[str, Any]], families: frozenset[str] | None,
) -> list[dict[str, Any]]:
    """Filter step 4. Family identity is read, never re-decided."""
    if families is None:
        return [dict(product) for product in products]
    return [
        dict(product) for product in products
        if str(product.get("productFamily") or "") in families
    ]


def build_sealed_price_panel(
    products: Iterable[Mapping[str, Any]], *, start_date: str, end_date: str,
) -> list[dict[str, Any]]:
    """The per-product daily price panel, flattened from prepared histories.

    Every point a product's prepared history carries within the window becomes
    one row. Price eligibility (filter step 5) is applied downstream by
    ``build_query_observations``, which drops non-positive prices rather than
    carrying a zero into the index as a total collapse.
    """
    first, last = str(start_date)[:10], str(end_date)[:10]
    rows: list[dict[str, Any]] = []
    for product in products:
        product_id = str(product.get(SEALED_ID_FIELD) or "").strip()
        if not product_id:
            continue
        for point in product.get("history") or []:
            point_date = str(point.get("date") or "")[:10]
            if not point_date or point_date < first or point_date > last:
                continue
            rows.append({
                "marketDate": point_date,
                SEALED_ID_FIELD: product_id,
                "marketPrice": point.get("marketPrice"),
                "setId": product.get("setId"),
            })
    return rows


# ---------------------------------------------------------------------------
# Series construction (filter step 6, then index math)
# ---------------------------------------------------------------------------

def build_sealed_query_series(
    panel_rows: Sequence[Mapping[str, Any]],
    product_metadata: Mapping[str, Mapping[str, Any]],
    *,
    mode: str,
    top_n: int | None,
) -> dict[str, Any] | None:
    """Index, tracked value and current constituents for one sealed query.

    The index is chain-linked over each day's COMMON cohort by the same shared
    primitive the card engine and the published sealed markets use, so a product
    entering or leaving the basket cannot by itself move the index. Tracked
    Value is the literal basket and is allowed to move on a roster change --
    that is the documented difference between the two measures.

    Window movements are confined to the CURRENT chain segment: index levels on
    either side of a cohort break are not mathematically linked, and spanning
    one would manufacture a return no price data supports.
    """
    observations = build_query_observations(
        panel_rows, mode=mode, top_n=top_n, id_field=SEALED_ID_FIELD,
    )
    if not observations:
        return None

    # CONSTITUENT MOVEMENT costs nothing here: this engine already holds the
    # whole product-date price panel in memory. Built off the raw panel rather
    # than the basket observations so a Top-N market still reports each
    # member's own real movement rather than only its in-basket days.
    constituent_movements = build_constituent_movements(
        prices_by_date_from_query_rows(panel_rows, id_field=SEALED_ID_FIELD)
    )

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

    constituents = []
    for entry in sorted(latest_observation["constituents"], key=lambda row: row["rank"]):
        product_id = str(entry["setId"])
        meta = dict(product_metadata.get(product_id) or {})
        constituents.append({
            "rank": entry["rank"],
            SEALED_ID_FIELD: product_id,
            "productName": meta.get("productName"),
            "variantLabel": meta.get("variantLabel"),
            "setId": meta.get("setId"),
            "setName": meta.get("setName"),
            "productFamily": meta.get("productFamily"),
            "productFamilyLabel": meta.get("productFamilyLabel"),
            "marketPrice": round(float(entry["setValue"]), 2),
            "imageUrl": meta.get("imageUrl"),
            "asOf": str(latest_observation["marketDate"])[:10],
            "queryMembershipReason": (
                f"rank {entry['rank']} by market price within the filtered universe"
                if mode == MODE_CHASE else "eligible product of the filtered universe"
            ),
            # The same compact contract prepared segments publish, so Current
            # Constituents renders prepared and dynamic markets identically.
            "changes": (constituent_movements.get("byConstituent") or {}).get(product_id) or {},
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
        # Window boundary dates for this market, published once.
        "movementWindows": constituent_movements.get("windows") or {},
        # Ids and ranks only, as on the card side: carrying full product
        # metadata for every date would multiply the payload by the history
        # length for a view that does not exist yet. Unlike the card cohort
        # path, the sealed panel is in memory, so this covers EVERY date and is
        # the direct evidence that membership was recomputed per date.
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
            # Fewer than N is a true statement about a small market, never an
            # error and never padded (section 12).
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
            "seriesPath": "preparedSealedSnapshots",
        },
    }


def describe_sealed_query(
    spec: Mapping[str, Any],
    *,
    era_names: Mapping[str, str] | None = None,
    set_names: Mapping[str, str] | None = None,
) -> str:
    """Human display label, e.g. "Scarlet & Violet · ETBs · All".

    SCOPE PRECEDENCE matches the card engine: an explicit set selection is the
    most specific statement the user made, so it wins over the era it belongs to.
    """
    era_names = era_names or {}
    set_names = set_names or {}
    if spec["setIds"]:
        scope = ", ".join(set_names.get(value, value) for value in spec["setIds"])
    elif spec["eraIds"]:
        scope = ", ".join(era_names.get(value, value) for value in spec["eraIds"])
    else:
        scope = "Global"

    labels = {str(d["key"]): str(d["label"]) for d in SEALED_SEGMENT_DEFINITIONS}
    segment = ", ".join(labels.get(value, value) for value in spec["segmentIds"]) or "All Sealed Products"
    dimensions = [scope, segment]
    names = {"obtainable": "Obtainable", "intermediate": "Intermediate", "premium": "Premium",
             "new": "New", "recent": "Recent", "established": "Established", "legacy": "Legacy"}
    for field in ("priceSegmentIds", "releaseAgeCohortIds"):
        if spec[field]:
            dimensions.append(", ".join(names.get(value, value) for value in spec[field]))
    dimensions.append(f"Top {spec['topN']}" if spec["mode"] == MODE_CHASE else "All")
    return " · ".join(dimensions)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_sealed_market_explorer_query(
    client: Any,
    *,
    mode: str,
    era_ids: Sequence[str] = (),
    set_ids: Sequence[str] = (),
    segment_ids: Sequence[str] = (),
    pokemon_ids: Sequence[str] = (),
    price_segment_ids: Sequence[str] = (),
    release_age_cohort_ids: Sequence[str] = (),
    top_n: int | None = None,
    start_date: str,
    end_date: str,
) -> dict[str, Any]:
    """Resolve, compute and describe one Market Explorer sealed query.

    Read-only. Nothing here writes, and no snapshot is mutated as a side effect
    of a user running a query.
    """
    spec = normalize_query_spec(
        mode=mode, asset=ASSET_SEALED,
        era_ids=era_ids, set_ids=set_ids, segment_ids=segment_ids,
        pokemon_ids=pokemon_ids, price_segment_ids=price_segment_ids,
        release_age_cohort_ids=release_age_cohort_ids, top_n=top_n,
    )
    started = time.perf_counter()

    scope_set_ids = resolve_sealed_scope_set_ids(
        client, era_ids=spec["eraIds"], set_ids=spec["setIds"],
    )
    if not scope_set_ids:
        raise SealedMarketExplorerQueryUnavailable(
            "no set with a prepared sealed snapshot satisfies the selected scope"
        )

    try:
        snapshots = read_global_sealed_source_snapshots(client, scope_set_ids)
    except GlobalSealedMarketUnavailable as exc:
        raise SealedMarketExplorerQueryUnavailable(str(exc)) from exc

    # The market date every prepared snapshot is read through. Taking the
    # LATEST across scope rather than today's calendar date keeps a query
    # answerable on a day the publisher has not run yet.
    market_date = max(
        (str(row.get("market_date") or "")[:10] for row in snapshots), default="",
    )
    if not market_date:
        raise SealedMarketExplorerQueryUnavailable("prepared sealed snapshots carry no market date")

    payloads = [row.get("payload_json") or {} for row in snapshots]
    set_names = {
        str((row.get("payload_json") or {}).get("set", {}).get("id") or row.get("set_id")):
            str((row.get("payload_json") or {}).get("set", {}).get("name") or "")
        for row in snapshots
    }
    try:
        products, _ = collect_global_sealed_products(payloads, market_date=market_date)
    except GlobalSealedMarketUnavailable as exc:
        raise SealedMarketExplorerQueryUnavailable(str(exc)) from exc

    set_id_by_product = {}
    for row in snapshots:
        payload = row.get("payload_json") or {}
        owning_set_id = str(payload.get("set", {}).get("id") or row.get("set_id") or "")
        for product in payload.get("products") or []:
            set_id_by_product[str(product.get(SEALED_ID_FIELD) or "")] = owning_set_id

    families = families_for_segments(spec["segmentIds"])
    eligible = filter_products_by_family(products, families)
    if not eligible:
        raise SealedMarketExplorerQueryUnavailable(
            "no eligible sealed product satisfies the selected filters"
        )

    product_metadata = {}
    for product in eligible:
        product_id = str(product.get(SEALED_ID_FIELD) or "")
        owning_set_id = set_id_by_product.get(product_id, "")
        product_metadata[product_id] = {
            "productName": product.get("name"),
            "variantLabel": product.get("variantLabel"),
            "setId": owning_set_id,
            "setName": set_names.get(owning_set_id),
            "productFamily": product.get("productFamily"),
            "productFamilyLabel": product.get("productFamilyLabel"),
            "imageUrl": product.get("imageUrl"),
        }
        product["setId"] = owning_set_id

    effective_end = min(str(end_date)[:10], market_date)
    panel_rows = build_sealed_price_panel(
        eligible, start_date=str(start_date)[:10], end_date=effective_end,
    )
    release_rows = list((client.table("sets").select("id,release_date")
                         .in_("id", scope_set_ids).execute()).data or [])
    panel_rows = filter_point_in_time_rows(
        panel_rows, asset=ASSET_SEALED,
        price_segment_ids=spec["priceSegmentIds"],
        release_age_cohort_ids=spec["releaseAgeCohortIds"],
        release_date_by_set={str(row.get("id")): row.get("release_date") for row in release_rows},
    )
    if not panel_rows:
        raise SealedMarketExplorerQueryUnavailable("the filtered universe has no priced history")

    series = build_sealed_query_series(
        panel_rows, product_metadata, mode=spec["mode"], top_n=spec["topN"],
    )
    if series is None:
        raise SealedMarketExplorerQueryUnavailable("the filtered universe has no priced history")

    era_names = _load_era_names(client, spec["eraIds"])
    return {
        "serviceVersion": SEALED_EXPLORER_QUERY_SERVICE_VERSION,
        "spec": {**spec, "eraIds": list(spec["eraIds"]), "setIds": list(spec["setIds"]),
                 "segmentIds": list(spec["segmentIds"]), "pokemonIds": list(spec["pokemonIds"]),
                 "priceSegmentIds": list(spec["priceSegmentIds"]),
                 "releaseAgeCohortIds": list(spec["releaseAgeCohortIds"])},
        "queryKey": query_key(spec),
        "queryFingerprint": query_fingerprint(spec),
        "displayLabel": describe_sealed_query(spec, era_names=era_names, set_names=set_names),
        "taxonomyVersion": SEALED_SEGMENT_CONTRACT_VERSION,
        "scope": {
            "resolvedSetCount": len(scope_set_ids),
            "eligibleProductCount": len(eligible),
            "requestedStartDate": str(start_date)[:10],
            "requestedEndDate": str(end_date)[:10],
            "startDate": series["historyStartDate"],
            "endDate": effective_end,
            "marketDate": market_date,
        },
        "diagnostics": {
            "snapshotCount": len(snapshots),
            "panelRowCount": len(panel_rows),
            "elapsedSeconds": round(time.perf_counter() - started, 3),
        },
        **series,
    }


def _load_era_names(client: Any, era_ids: Sequence[str]) -> dict[str, str]:
    if not era_ids:
        return {}
    rows = list((client.table("eras").select("id,name").in_("id", list(era_ids)).execute()).data or [])
    return {str(row.get("id")): str(row.get("name") or "") for row in rows}


def published_sealed_family_options() -> dict[str, Any]:
    """Backend-published sealed family options. The frontend has no authority."""
    return segment_definition_metadata()
