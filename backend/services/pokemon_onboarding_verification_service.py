from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, Optional


def _first(rows: Any) -> Dict[str, Any]:
    values = list(rows or [])
    return values[0] if values and isinstance(values[0], dict) else {}


def _walk(value: Any) -> Iterable[Any]:
    yield value
    if isinstance(value, dict):
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _contains_identity(payload: Any, set_id: str, canonical_key: str) -> bool:
    targets = {set_id.lower(), canonical_key.lower()}
    return any(isinstance(value, str) and value.lower() in targets for value in _walk(payload))


def _find_mapping(payload: Any, key: str) -> Dict[str, Any]:
    for value in _walk(payload):
        if isinstance(value, dict) and isinstance(value.get(key), dict):
            return value[key]
    return {}


def collect_final_verification(
    client: Any, *, canonical_key: str, config_path: Path,
    min_image_coverage: float,
) -> Dict[str, Any]:
    sets = (
        client.table("sets").select("id,canonical_key,name,pokemon_api_set_id,ready_for_daily_scrape,source_config_path")
        .eq("canonical_key", canonical_key).limit(1).execute().data or []
    )
    set_row = _first(sets)
    set_id = str(set_row.get("id") or "")
    if not set_id:
        return {"source_config_registered": config_path.exists(), "public_set_correct": False,
                "missing": ["public_set_correct"]}

    cards = client.table("cards").select("id,image_small_url,image_large_url").eq("set_id", set_id).limit(1000).execute().data or []
    card_ids = [row["id"] for row in cards if row.get("id")]
    variants = []
    for start in range(0, len(card_ids), 250):
        variants.extend(
            client.table("card_variants").select("id,card_id,image_small_url,image_large_url")
            .in_("card_id", card_ids[start:start + 250]).execute().data or []
        )
    variant_ids = [row["id"] for row in variants if row.get("id")]
    prices = []
    for start in range(0, len(variant_ids), 250):
        prices.extend(
            client.table("card_variant_price_observations").select("captured_at,market_price")
            .in_("card_variant_id", variant_ids[start:start + 250]).gt("market_price", 0)
            .order("captured_at", desc=True).limit(1000).execute().data or []
        )
    card_by_id = {row.get("id"): row for row in cards}
    variants_with_images = sum(
        1 for row in variants
        if row.get("image_small_url") or row.get("image_large_url")
        or (card_by_id.get(row.get("card_id")) or {}).get("image_small_url")
        or (card_by_id.get(row.get("card_id")) or {}).get("image_large_url")
    )
    cards_with_images = sum(
        1 for row in cards if row.get("image_small_url") or row.get("image_large_url")
    )
    coverage = variants_with_images / len(variants) if variants else 0.0

    set_value = _first(
        client.table("pokemon_set_value_daily_history").select("snapshot_date,set_value")
        .eq("set_id", set_id).eq("value_scope", "standard").gt("set_value", 0)
        .order("snapshot_date", desc=True).limit(1).execute().data
    )
    run = _first(
        client.table("calculation_runs").select("id,target_id,created_at")
        .eq("target_type", "set").eq("target_id", set_id).order("created_at", desc=True)
        .limit(1).execute().data
    )
    run_id = str(run.get("id") or "")
    summary = _first(
        client.table("simulation_run_summary").select("calculation_run_id,simulation_count")
        .eq("calculation_run_id", run_id).limit(1).execute().data
    ) if run_id else {}
    inputs = (
        client.table("simulation_input_cards").select("calculation_run_id")
        .eq("calculation_run_id", run_id).limit(1000).execute().data or []
    ) if run_id else []
    derived = _first(
        client.table("simulation_derived_metrics").select("calculation_run_id")
        .eq("calculation_run_id", run_id).limit(1).execute().data
    ) if run_id else {}
    desirability = _first(
        client.table("pokemon_set_desirability_component_scores").select("*")
        .eq("set_id", set_id).order("built_at", desc=True).limit(1).execute().data
    )
    opvc = _first(
        client.table("calculation_history_trend")
        .select("snapshot_date,calculation_run_id,simulated_mean_pack_value_vs_pack_cost")
        .eq("target_type", "set").eq("target_id", set_id)
        .order("snapshot_date", desc=True).limit(1).execute().data
    )
    top_chase = _first(
        client.table("pokemon_set_top_chase_card_daily_history").select("snapshot_date,rank")
        .eq("set_id", set_id).order("snapshot_date", desc=True).limit(1).execute().data
    )
    market_snapshot = _first(
        client.table("pokemon_set_market_dashboard_snapshot_latest")
        .select("latest_market_date,updated_at").eq("set_id", set_id)
        .eq("window_key", "365d").limit(1).execute().data
    )
    explore = _first(
        client.table("pokemon_explore_rankings_snapshot_latest")
        .select("ranking_payload_json,updated_at").eq("tcg", "pokemon")
        .eq("scope", "rip-statistics").limit(1).execute().data
    )
    page = _first(
        client.table("pokemon_set_page_snapshot_latest")
        .select("payload_json,rip_summary_json,desirability_summary_json,as_of,updated_at")
        .eq("set_id", set_id).limit(1).execute().data
    )
    payload = page.get("payload_json") or {}
    collector = _find_mapping(payload, "collectorAppeal")
    rip = _find_mapping(payload, "rip")
    warnings = [
        str(value).lower() for value in _walk(payload)
        if isinstance(value, str) and ("warning" in value.lower() or "missing" in value.lower())
    ]
    market_date = str((market_snapshot or {}).get("latest_market_date") or set_value.get("snapshot_date") or "")
    source_dates = {
        "market_date": market_date or None,
        "set_value_date": set_value.get("snapshot_date"),
        "opvc_date": opvc.get("snapshot_date"),
        "top_chase_date": top_chase.get("snapshot_date"),
    }
    comparable = [str(value)[:10] for value in source_dates.values() if value]
    dates_align = bool(comparable) and len(set(comparable)) == 1
    approved_pull_model = '"approved"' in config_path.read_text(encoding="utf-8") if config_path.exists() else False

    evidence = {
        "set_id": set_id, "market_date": market_date or None, "calculation_run_id": run_id or None,
        "simulation_input_count": len(inputs), "simulation_detail_count": sum(bool(x) for x in (summary, derived)),
        "desirability_versions": {k: v for k, v in desirability.items() if "version" in k},
        "ca7_status": collector.get("status"), "ca7_reason": collector.get("reason") or collector.get("statusReason"),
        "overall_rip_status": rip.get("status"), "overall_rip_reason": rip.get("statusReason"),
        "set_value_date": set_value.get("snapshot_date"), "set_value": set_value.get("set_value"),
        "latest_opvc_date": opvc.get("snapshot_date"), "latest_top_chase_date": top_chase.get("snapshot_date"),
        "explore_rank_present": _contains_identity(explore.get("ranking_payload_json"), set_id, canonical_key),
        "set_page_snapshot_timestamp": page.get("updated_at"), "market_snapshot_timestamp": market_snapshot.get("updated_at"),
        "source_dates": source_dates, "date_mismatch_details": [] if dates_align else source_dates,
        "cards_with_images": cards_with_images, "variants_with_images": variants_with_images,
        "eligible_card_count": len(cards), "eligible_variant_count": len(variants),
        "image_coverage_ratio": coverage, "image_unmatched_count": max(len(variants) - variants_with_images, 0),
        "image_ambiguous_count": None,
        "source_config_registered": (
            config_path.exists()
            and str(set_row.get("source_config_path") or "").replace("\\", "/").endswith(f"/{canonical_key}.py")
        ),
        "public_set_correct": set_row.get("canonical_key") == canonical_key,
        "ready_for_daily_scrape": bool(set_row.get("ready_for_daily_scrape")),
        "cards_populated": bool(cards), "variants_populated": bool(variants),
        "market_prices_populated": bool(prices),
        "image_coverage_acceptable": coverage >= min_image_coverage,
        "positive_standard_set_value": bool(set_value),
        "approved_pull_model": approved_pull_model,
        "current_simulation": bool(run),
        "simulation_details": bool(summary and derived and inputs),
        "current_desirability_components": bool(desirability),
        "canonical_ca7": collector.get("score") is not None and collector.get("status") != "unavailable",
        "overall_rip": rip.get("score") is not None and rip.get("rankable") is not False,
        "current_opvc": bool(opvc.get("simulated_mean_pack_value_vs_pack_cost") is not None),
        "current_top_chase": bool(top_chase),
        "explore_contains_set": _contains_identity(explore.get("ranking_payload_json"), set_id, canonical_key),
        "set_page_snapshot": bool(page),
        "source_dates_align": dates_align,
        "no_mixed_generation_warning": not any("mixed" in warning for warning in warnings),
        "no_satisfiable_missing_input_warning": not any("missing" in warning for warning in warnings),
    }
    required = (
        "source_config_registered", "public_set_correct", "ready_for_daily_scrape", "cards_populated",
        "variants_populated", "market_prices_populated", "image_coverage_acceptable",
        "positive_standard_set_value", "approved_pull_model", "current_simulation",
        "simulation_details", "current_desirability_components", "canonical_ca7", "overall_rip",
        "current_opvc", "current_top_chase", "explore_contains_set", "set_page_snapshot",
        "source_dates_align", "no_mixed_generation_warning", "no_satisfiable_missing_input_warning",
    )
    evidence["missing"] = [field for field in required if not evidence[field]]
    evidence["complete"] = not evidence["missing"]
    return evidence
