from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, Sequence

from backend.desirability.public_analytics_policy import is_public_analytics_eligible
from backend.domain.pokemon.market_index import (
    CHASE_INDEX_KEY, INDEX_KEYS, MARKET_INDEX_CONTRACT_VERSION, MARKET_INDEX_METHODOLOGY_VERSION,
    RAW_INDEX_KEY, build_chain_linked_history, compute_strict_window_movements, deterministic_fingerprint,
)

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


def build_index_rows(sets: Sequence[Mapping[str, Any]], source_rows: Iterable[Mapping[str, Any]], *, through_date: str | None = None) -> list[dict[str, Any]]:
    by_scope_date_set: dict[tuple[str, str, str], Mapping[str, Any]] = {}
    all_dates: set[str] = set()
    for row in source_rows:
        scope, day, set_id = str(row.get("value_scope")), str(row.get("snapshot_date"))[:10], str(row.get("set_id"))
        if scope in ("standard", "top10") and (through_date is None or day <= through_date):
            by_scope_date_set[(scope, day, set_id)] = row
            all_dates.add(day)
    built: list[dict[str, Any]] = []
    for index_key in INDEX_KEYS:
        scope = "standard" if index_key == RAW_INDEX_KEY else "top10"
        observations = []
        for day in sorted(all_dates):
            active = [row for row in sets if not row.get("release_date") or str(row["release_date"])[:10] <= day]
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


def build_market_index_history(client: Any, *, through_date: str | None = None) -> list[dict[str, Any]]:
    sets = resolve_eligible_sets(client)
    return build_index_rows(sets, _paged_source_rows(client, [str(row["id"]) for row in sets]), through_date=through_date)


def persist_index_rows(client: Any, rows: Sequence[Mapping[str, Any]]) -> int:
    if not rows:
        return 0
    client.table(TABLE).upsert([dict(row) for row in rows], on_conflict="tcg,index_key,market_date,methodology_version").execute()
    return len(rows)


def read_index_history(client: Any, *, through_date: str | None = None) -> list[dict[str, Any]]:
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


def build_market_overview(history: Sequence[Mapping[str, Any]], *, market_date: str) -> dict[str, Any]:
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
        return {"basketValue": float(latest["basket_value"]), "indexValue": value,
                "historyStartDate": points[0]["date"], "changes": compute_strict_window_movements(points),
                "trend": [[row["date"], row["value"]] for row in points]}
    return {"contractVersion": "pokemon-market-overview-v1", "marketDate": market_date,
        "coverage": {"eligibleSetCount": int(raw["set_count"]), "rawCardCount": int(raw["card_count"]),
            "chaseCardCount": int(chase["card_count"]), "cohortFingerprint": raw["cohort_fingerprint"]},
        "raw": family(by_key[RAW_INDEX_KEY]), "topChase": family(by_key[CHASE_INDEX_KEY]),
        "methodology": {"version": MARKET_INDEX_METHODOLOGY_VERSION,
            "basketDefinition": "sum of canonical Near Mint raw-card set baskets",
            "indexDefinition": "chain-linked return over consecutive common set cohorts",
            "notMarketCapitalization": True},
        "sourceGenerationFingerprint": deterministic_fingerprint([raw["source_generation_fingerprint"], chase["source_generation_fingerprint"]])}
