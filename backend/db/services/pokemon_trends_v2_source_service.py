"""Exact-run, read-only authority for persisted Pokemon Trends V2 evidence."""
from __future__ import annotations

from typing import Any

SOURCE_NAME = "google_trends_pokemon_v2"
DIMENSION_KEY = "pokemon_search_interest_v2"
USABLE = {"SCORED", "scored_zero_high_confidence"}


def load_pokemon_trends_v2_run(source_run_id: str, *, client: Any) -> dict:
    runs = (client.table("pokemon_collector_source_runs")
            .select("id,source_name,capture_version,status,source_fingerprint,item_count,raw_payload_json,diagnostics_json")
            .eq("id", source_run_id).limit(1).execute().data or [])
    if not runs: raise RuntimeError(f"Collector source run {source_run_id} not found")
    run = runs[0]
    if run.get("source_name") != SOURCE_NAME or run.get("status") not in ("success", "partial_failure"):
        raise RuntimeError(f"Collector source run {source_run_id} is not a terminal Pokemon Trends V2 run")
    rows = []
    for start in range(0, 2000, 1000):
        page = (client.table("pokemon_collector_entity_observations")
                .select("source_run_id,collector_entity_id,external_entity_key,normalized_observation_score,raw_value,raw_row_json")
                .eq("source_run_id", source_run_id).eq("dimension_key", DIMENSION_KEY)
                .order("external_entity_key").range(start, start + 999).execute().data or [])
        rows.extend(page)
        if len(page) < 1000:
            break
    else:
        raise RuntimeError(f"Pokemon Trends V2 exact-run read exceeded safety limit for {source_run_id}")
    if len(rows) != run.get("item_count") or len(rows) != 1025:
        raise RuntimeError(f"Pokemon Trends V2 exact-run row count mismatch for {source_run_id}")
    result = []
    for row in rows:
        raw = row.get("raw_row_json") or {}; classification = raw.get("classification")
        score = row.get("normalized_observation_score")
        if classification not in USABLE and score is not None:
            raise RuntimeError("unavailable Trends evidence carried a numeric score")
        result.append({"sourceRunId": source_run_id, "collectorEntityId": row.get("collector_entity_id"),
                       "pokedexKey": row.get("external_entity_key"), "classification": classification,
                       "calibratedTrendsValue": raw.get("globalRelative") if classification in USABLE else None,
                       "provenance": raw})
    return {"sourceRun": run, "observations": result}
