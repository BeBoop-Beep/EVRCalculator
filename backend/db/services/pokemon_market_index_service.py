from __future__ import annotations

import logging
import math
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, Sequence

from backend.desirability.public_analytics_policy import is_public_analytics_eligible
from backend.domain.pokemon.market_index import (
    CHASE_INDEX_KEY, INDEX_KEYS, MARKET_COMPARISON_WINDOW_CONTRACT_VERSION,
    MARKET_INDEX_CONTRACT_VERSION, MARKET_INDEX_METHODOLOGY_VERSION,
    MARKET_INDEX_TRACKING_START_DATE,
    RAW_INDEX_KEY, build_chain_linked_history, build_comparison_windows,
    compute_comparison_window_movements, compute_strict_window_movements, deterministic_fingerprint,
)

logger = logging.getLogger(__name__)
_INDEX_TAG = "[market-index]"

TABLE = "pokemon_market_index_daily_history"
SOURCE_TABLE = "pokemon_set_value_daily_history"
PAGE_SIZE = 1000


class PokemonMarketIndexUnavailable(RuntimeError):
    def __init__(self, message: str, diagnostics: Mapping[str, Any] | None = None):
        super().__init__(message)
        self.diagnostics = dict(diagnostics or {})


def resolve_eligible_sets(client: Any) -> list[dict[str, Any]]:
    rows = list(client.table("sets").select("id,canonical_key,name,era_id,release_date,supports_opening_simulation").execute().data or [])
    eligible = [dict(row) for row in rows if row.get("supports_opening_simulation") is True and is_public_analytics_eligible(row)]
    if not eligible:
        raise PokemonMarketIndexUnavailable("eligible Pokemon Market cohort is empty")
    return sorted(eligible, key=lambda row: str(row["id"]))


def _paged_source_rows(client: Any, set_ids: Sequence[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    offset = 0
    while True:
        page = list((client.table(SOURCE_TABLE)
            .select("set_id,snapshot_date,set_value,priced_card_count,total_card_count,value_scope,source,updated_at")
            .in_("set_id", list(set_ids)).in_("value_scope", ["standard", "top10"])
            .order("snapshot_date", desc=False).order("set_id", desc=False)
            .order("value_scope", desc=False).range(offset, offset + PAGE_SIZE - 1).execute()).data or [])
        rows.extend(dict(row) for row in page)
        if len(page) < PAGE_SIZE:
            return rows
        offset += PAGE_SIZE


def resolve_market_entry_dates(
    sets: Sequence[Mapping[str, Any]], source_rows: Iterable[Mapping[str, Any]],
) -> dict[str, str]:
    """Canonical tracked-market entry date for each jointly ready set.

    Raw and Top Chase deliberately share this cohort. A released set does not
    enter either index until both required valuation scopes have a valid first
    observation; chain linking then neutralizes the new constituent's entry.
    """
    first_valid: dict[tuple[str, str], str] = {}
    for row in source_rows:
        scope = str(row.get("value_scope") or "")
        if scope not in ("standard", "top10"):
            continue
        try:
            valid = float(row.get("set_value") or 0) > 0 and int(row.get("priced_card_count") or 0) > 0
        except (TypeError, ValueError):
            valid = False
        if not valid:
            continue
        identity = (str(row.get("set_id")), scope)
        day = str(row.get("snapshot_date"))[:10]
        if identity not in first_valid or day < first_valid[identity]:
            first_valid[identity] = day
    entries: dict[str, str] = {}
    for pokemon_set in sets:
        set_id = str(pokemon_set["id"])
        standard = first_valid.get((set_id, "standard"))
        top10 = first_valid.get((set_id, "top10"))
        if not standard or not top10:
            continue
        release = str(pokemon_set.get("release_date") or "0001-01-01")[:10]
        entries[set_id] = max(release, standard, top10)
    return entries


def resolve_market_entry_dates_for_client(
    client: Any, sets: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, str]:
    eligible = list(sets) if sets is not None else resolve_eligible_sets(client)
    return resolve_market_entry_dates(
        eligible, _paged_source_rows(client, [str(row["id"]) for row in eligible]))


def build_index_rows(sets: Sequence[Mapping[str, Any]], source_rows: Iterable[Mapping[str, Any]], *, through_date: str | None = None, accepted_dates: Iterable[str] | None = None, tracking_start_date: str | None = None) -> list[dict[str, Any]]:
    # BLOCKER 1: quality filtering happens HERE, before any observation is
    # assembled and therefore before build_chain_linked_history runs. A
    # DEGRADED date must contribute zero mathematical influence to later
    # dates; filtering persisted output afterwards would still have chained
    # Aug 19's daily return off Aug 18.
    accepted = None if accepted_dates is None else {str(day)[:10] for day in accepted_dates}
    source_rows = list(source_rows)
    market_entry_dates = resolve_market_entry_dates(sets, source_rows)
    by_scope_date_set: dict[tuple[str, str, str], Mapping[str, Any]] = {}
    all_dates: set[str] = set()
    for row in source_rows:
        scope, day, set_id = str(row.get("value_scope")), str(row.get("snapshot_date"))[:10], str(row.get("set_id"))
        if accepted is not None and day not in accepted:
            continue
        if (scope in ("standard", "top10")
                and (tracking_start_date is None or day >= tracking_start_date)
                and (through_date is None or day <= through_date)):
            by_scope_date_set[(scope, day, set_id)] = row
            all_dates.add(day)
    built: list[dict[str, Any]] = []
    for index_key in INDEX_KEYS:
        scope = "standard" if index_key == RAW_INDEX_KEY else "top10"
        observations = []
        for day in sorted(all_dates):
            active = [row for row in sets
                      if market_entry_dates.get(str(row["id"]), "9999-12-31") <= day]
            if not active:
                continue
            constituents = []
            complete = True
            for pokemon_set in active:
                source = by_scope_date_set.get((scope, day, str(pokemon_set["id"])))
                value = float(source.get("set_value") or 0) if source else 0
                count = int(source.get("priced_card_count") or 0) if source else 0
                if not source or value <= 0 or count <= 0:
                    complete = False
                    break
                constituents.append({"setId": str(pokemon_set["id"]), "canonicalKey": pokemon_set.get("canonical_key"),
                    "setValue": value, "includedCardCount": count, "sourceSnapshotDate": day,
                    "source": source.get("source"), "sourceUpdatedAt": source.get("updated_at")})
            if complete:
                observations.append({"marketDate": day, "indexKey": index_key, "constituents": constituents})
        history = build_chain_linked_history(observations)
        for row in history:
            constituents = row["constituents"]
            cohort_fp = deterministic_fingerprint([item["setId"] for item in constituents])
            source_fp = deterministic_fingerprint([{key: item.get(key) for key in ("setId", "setValue", "includedCardCount", "sourceSnapshotDate", "source", "sourceUpdatedAt")} for item in constituents])
            built.append({"tcg": "pokemon", "index_key": index_key, "market_date": row["marketDate"],
                "contract_version": MARKET_INDEX_CONTRACT_VERSION, "methodology_version": MARKET_INDEX_METHODOLOGY_VERSION,
                "basket_value": row["basketValue"], "normalized_index_value": row["normalizedIndexValue"],
                "daily_return": row["dailyReturn"], "previous_market_date": row["previousMarketDate"],
                "set_count": len(constituents), "card_count": sum(int(item["includedCardCount"]) for item in constituents),
                "cohort_fingerprint": cohort_fp, "source_generation_fingerprint": source_fp,
                "constituents_json": constituents, "diagnostics_json": {"commonSetIds": row["commonSetIds"]}})
    return sorted(built, key=lambda row: (row["market_date"], row["index_key"]))


def build_market_index_history(client: Any, *, through_date: str | None = None, accepted_dates: Iterable[str] | None = None) -> list[dict[str, Any]]:
    sets = resolve_eligible_sets(client)
    return build_index_rows(
        sets, _paged_source_rows(client, [str(row["id"]) for row in sets]),
        through_date=through_date, accepted_dates=accepted_dates,
        tracking_start_date=MARKET_INDEX_TRACKING_START_DATE)


def persist_index_rows(client: Any, rows: Sequence[Mapping[str, Any]]) -> int:
    if not rows:
        return 0
    client.table(TABLE).upsert([dict(row) for row in rows], on_conflict="tcg,index_key,market_date,methodology_version").execute()
    return len(rows)


def read_raw_index_history_for_audit(client: Any, *, through_date: str | None = None) -> list[dict[str, Any]]:
    """EVERY persisted index row, Market Date Quality notwithstanding.

    Diagnostics/audit only. A date that quality has since judged DEGRADED is
    still returned here on purpose: the row is retained as evidence and audit
    tooling must be able to see it. Public/normal reads must use
    :func:`read_index_history`, which serves only accepted dates.
    """
    query = (client.table(TABLE).select("*").eq("tcg", "pokemon")
             .eq("methodology_version", MARKET_INDEX_METHODOLOGY_VERSION)
             .order("market_date", desc=False).order("index_key", desc=False))
    if through_date:
        query = query.lte("market_date", through_date)
    rows, offset = [], 0
    while True:
        page = list(query.range(offset, offset + PAGE_SIZE - 1).execute().data or [])
        rows.extend(dict(row) for row in page)
        if len(page) < PAGE_SIZE:
            return rows
        offset += PAGE_SIZE


def resolve_accepted_market_dates(client: Any, *, through_date: str | None = None) -> set[str] | None:
    """Accepted Market dates, or None when quality enforcement is not yet active.

    ONE paginated read of the quality authority - never a lookup per history
    row. Acceptance reuses the canonical ``ACCEPTED_STATUSES`` predicate so the
    read path and the build path cannot drift apart.

    Returning None (rather than an empty set) when no quality row exists at all
    is deliberate. An environment that has never materialized Market Date
    Quality has not opted into enforcement, and treating "no authority" as
    "nothing is accepted" would blank the entire public chart - the read-side
    twin of the partial-materialization hazard the CLI guards against.
    """
    # Imported lazily: market_date_quality imports this module at import time,
    # so a module-level import here would be circular.
    from backend.db.services.market_date_quality import (
        is_market_index_quality_accepted, read_market_date_quality_history,
    )

    quality_rows = read_market_date_quality_history(client, through_date=through_date)
    if not quality_rows:
        logger.warning(
            "%s no Market Date Quality rows found; serving unfiltered index history "
            "(quality enforcement is not active in this environment)", _INDEX_TAG)
        return None
    return {
        str(row["market_date"])[:10] for row in quality_rows
        if is_market_index_quality_accepted(row)
    }


def read_index_history(
    client: Any,
    *,
    through_date: str | None = None,
    accepted_dates: Iterable[str] | None = None,
) -> list[dict[str, Any]]:
    """Accepted/public Market index history.

    Rows whose market date is not accepted by Market Date Quality (DEGRADED,
    INCOMPLETE, or unevaluated once enforcement is active) are withheld. The
    rows remain physically stored - this filters the view, never the table.

    ``accepted_dates`` may be supplied by a caller that already resolved the
    set, matching the convention ``build_index_rows`` established, and avoids a
    second read of the quality authority.
    """
    rows = read_raw_index_history_for_audit(client, through_date=through_date)
    accepted = (resolve_accepted_market_dates(client, through_date=through_date)
                if accepted_dates is None else {str(day)[:10] for day in accepted_dates})
    if accepted is None:
        return rows
    return [row for row in rows if str(row.get("market_date"))[:10] in accepted]


def build_market_overview(
    history: Sequence[Mapping[str, Any]], *, market_date: str,
    sealed_market: Mapping[str, Any] | None = None,
    sealed_segments: Mapping[str, Any] | None = None,
    card_segments: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the published Market Overview.

    THREE DISTINCT PERFORMANCE STATEMENTS, published separately and never
    conflated — they are frequently different numbers, which is the point:

      indexValue     - the chain-linked index LEVEL against this family's own
                       base of 100. 106.18 means this market sits 6.18% above
                       its own index base.
      familyChanges  - window movements measured from THIS family's own
                       canonical tracking start / current chain segment. This
                       is what "Since Tracking" means, and it is family-
                       specific by construction.
      changes        - window movements over the SHARED comparison domain: the
                       common calendar every compared family can actually be
                       measured across. Its longest window is the common
                       comparable start, NOT any one family's tracking start.

    An earlier revision computed the family-specific movements and then
    OVERWROTE them with the shared-comparison result under the same `changes`
    key, so a UI labelling that column "Since Tracking" was in fact reporting
    the shared comparable start. Both are now published, so a label can be
    honest about which one it means.
    """
    by_key = {key: sorted([dict(row) for row in history if row.get("index_key") == key and str(row.get("market_date"))[:10] <= market_date], key=lambda row: str(row["market_date"])) for key in INDEX_KEYS}
    if any(not rows or str(rows[-1]["market_date"])[:10] != market_date for rows in by_key.values()):
        raise PokemonMarketIndexUnavailable("both index families must reach the promoted market date")
    raw, chase = by_key[RAW_INDEX_KEY][-1], by_key[CHASE_INDEX_KEY][-1]
    if raw["cohort_fingerprint"] != chase["cohort_fingerprint"] or int(chase["card_count"]) != int(chase["set_count"]) * 10:
        raise PokemonMarketIndexUnavailable("current raw/top10 cohort or chase count disagrees")
    if float(chase["basket_value"]) > float(raw["basket_value"]):
        raise PokemonMarketIndexUnavailable("top10 basket exceeds raw basket")
    def family(rows):
        latest = rows[-1]
        value = float(latest["normalized_index_value"])
        if not math.isfinite(value) or value <= 0:
            raise PokemonMarketIndexUnavailable("current index is non-finite or non-positive")
        points = [{"date": str(row["market_date"])[:10], "value": float(row["normalized_index_value"])} for row in rows]
        # TWO dimensions over the SAME persisted history and the SAME strict
        # window convention, differing only in the value being measured:
        #   changes       -> normalized_index_value (chain-linked price
        #                    performance; cohort entry/exit is neutralized)
        #   basketChanges -> basket_value (literal tracked-basket dollars;
        #                    cohort entry/exit is deliberately INCLUDED)
        # A set joining the tracked universe therefore moves basketChanges and
        # leaves changes flat. Neither is derived from the other, and no new
        # persistence or second window convention is introduced.
        basket_points = [{"date": str(row["market_date"])[:10], "value": float(row["basket_value"])} for row in rows]
        strict = compute_strict_window_movements(points)
        return {"basketValue": float(latest["basket_value"]),
                "basketChanges": compute_strict_window_movements(basket_points),
                "indexValue": value,
                "historyStartDate": points[0]["date"],
                # Family-specific, from this family's own history. Survives the
                # shared-comparison pass below, which only rewrites `changes`.
                "familyChanges": strict,
                "changes": strict,
                "trend": [[row["date"], row["value"]] for row in points]}
    result = {"contractVersion": "pokemon-market-overview-v1", "marketDate": market_date,
        "coverage": {"eligibleSetCount": int(raw["set_count"]), "rawCardCount": int(raw["card_count"]),
            "chaseCardCount": int(chase["card_count"]), "cohortFingerprint": raw["cohort_fingerprint"]},
        "raw": family(by_key[RAW_INDEX_KEY]), "topChase": family(by_key[CHASE_INDEX_KEY]),
        "methodology": {"version": MARKET_INDEX_METHODOLOGY_VERSION,
            "basketDefinition": "sum of canonical Near Mint raw-card set baskets",
            "indexDefinition": "chain-linked return over consecutive common set cohorts",
            "basketChangeDefinition": "literal percentage change in the complete tracked basket value; includes cohort additions/removals",
            "pricePerformanceDefinition": "chain-linked common-cohort price performance; cohort entry/exit is neutralized at the transition",
            "notMarketCapitalization": True},
        "sourceGenerationFingerprint": deterministic_fingerprint([raw["source_generation_fingerprint"], chase["source_generation_fingerprint"]])}
    if sealed_market is not None:
        # Additive extension: Raw/Top10 are built byte-for-byte by the existing
        # path. Sealed is already prepared from underlying global SKUs.
        result["sealedMarket"] = dict(sealed_market)
        # Sealed publishes its own strict, current-segment movements as
        # `changes`; preserve them as the family-specific series before the
        # shared-comparison pass rewrites `changes` below.
        result["sealedMarket"].setdefault(
            "familyChanges", dict(result["sealedMarket"].get("changes") or {})
        )
        result["coverage"]["sealedProductCount"] = int(
            (sealed_market.get("metadata") or {}).get("eligibleProductCount") or 0
        )
        result["sourceGenerationFingerprint"] = deterministic_fingerprint([
            result["sourceGenerationFingerprint"],
            sealed_market.get("sourceGenerationFingerprint"),
        ])
    comparison_families = [result["raw"], result["topChase"]]
    if isinstance(result.get("sealedMarket"), dict):
        comparison_families.append(result["sealedMarket"])
    comparison_windows = build_comparison_windows(market_date, [
        [row[0] if isinstance(row, (list, tuple)) else row.get("date")
         for row in (family.get("trend") or [])]
        for family in comparison_families
    ])
    result["comparisonWindows"] = comparison_windows
    result["comparisonWindowContractVersion"] = MARKET_COMPARISON_WINDOW_CONTRACT_VERSION
    # Names the two window vocabularies so a consumer never has to guess which
    # one a given key belongs to, and so a label cannot drift from its meaning.
    result["windowSemantics"] = {
        "indexValue": "Chain-linked index level against this market's own base of 100.",
        "familyChanges": "Window movements from this market's own tracking start (current chain segment). 'SinceTracking' here means since THIS market began tracking.",
        "changes": "Window movements over the shared comparison domain common to the compared markets. 'SinceTracking' here means since the common comparable start.",
        "sharedComparisonLabel": "Since Comparable Start",
        "familySinceTrackingLabel": "Since Tracking",
    }
    for comparison_family in comparison_families:
        trend = comparison_family.get("trend") or []
        points = [
            {"date": row[0], "value": row[1]} if isinstance(row, (list, tuple))
            else {"date": row.get("date"), "value": row.get("value", row.get("indexValue"))}
            for row in trend
        ]
        comparison_family["changes"] = compute_comparison_window_movements(points, comparison_windows)
        one_day = comparison_family.get("oneDayComparison")
        one_day_window = comparison_windows.get("1D") or {}
        if (isinstance(one_day, dict)
                and one_day.get("targetStartDate") == one_day_window.get("displayStartDate")
                and one_day.get("endDate") == one_day_window.get("displayEndDate")):
            comparison_family["changes"]["1D"] = {
                key: value for key, value in one_day.items()
                if key != "comparisonTrend"
            }
    if sealed_segments is not None:
        # ADDITIVE AND NON-DISTURBING. Segments are attached AFTER the shared
        # comparison domain is fixed, and are deliberately NOT part of
        # `comparison_families`: adding them would change the common calendar
        # and therefore silently move Raw, Top Chase and Total Sealed returns.
        # Each segment is instead measured against the domain the parents
        # already established, so a submarket and its parent are directly
        # comparable, while `familyChanges` keeps each segment's own history.
        published = dict(sealed_segments.get("segments") or {})
        for segment in published.values():
            if not isinstance(segment, dict) or segment.get("available") is not True:
                continue
            segment.setdefault("familyChanges", dict(segment.get("changes") or {}))
            segment_points = [
                {"date": row[0], "value": row[1]} if isinstance(row, (list, tuple))
                else {"date": row.get("date"), "value": row.get("value")}
                for row in (segment.get("trend") or [])
            ]
            segment["changes"] = compute_comparison_window_movements(
                segment_points, comparison_windows
            )
        result["sealedSegments"] = {
            **{key: value for key, value in sealed_segments.items() if key != "segments"},
            "segments": published,
        }
        result["sourceGenerationFingerprint"] = deterministic_fingerprint([
            result["sourceGenerationFingerprint"],
            sealed_segments.get("sourceGenerationFingerprint"),
        ])
    if card_segments is not None:
        # Same additive, non-disturbing contract as sealed segments: attached
        # AFTER the shared comparison domain is fixed, and deliberately NOT part
        # of `comparison_families`, so adding card-rarity children cannot move
        # Raw, Top Chase or Sealed by a basis point. Each segment is measured
        # against the domain the parents already established, while
        # `familyChanges` keeps its own tracking-start history.
        published = dict(card_segments)
        for parent_key in ("raw", "topChase"):
            collection = published.get(parent_key)
            if not isinstance(collection, dict):
                continue
            for segment in (collection.get("segments") or {}).values():
                if not isinstance(segment, dict) or segment.get("available") is not True:
                    continue
                segment.setdefault("familyChanges", dict(segment.get("changes") or {}))
                segment_points = [
                    {"date": row[0], "value": row[1]} if isinstance(row, (list, tuple))
                    else {"date": row.get("date"), "value": row.get("value")}
                    for row in (segment.get("trend") or [])
                ]
                segment["changes"] = compute_comparison_window_movements(
                    segment_points, comparison_windows
                )
        result["cardSegments"] = published
        result["sourceGenerationFingerprint"] = deterministic_fingerprint([
            result["sourceGenerationFingerprint"],
            (published.get("raw") or {}).get("sourceGenerationFingerprint"),
        ])
    result["sourceGenerationFingerprint"] = deterministic_fingerprint([
        result["sourceGenerationFingerprint"], MARKET_COMPARISON_WINDOW_CONTRACT_VERSION,
    ])
    return result
